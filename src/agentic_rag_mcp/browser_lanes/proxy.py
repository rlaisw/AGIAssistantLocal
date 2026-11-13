"""Dynamic-lane v2 (2026-11-12, the speed revision): the sidecar holds ONE
streamable-HTTP MCP session to the Playwright MCP server and exposes thin
proxy tools so the DIFY agent steers in a SINGLE hop — no second Hermes
agent turn, no gateway MCP arg path (the arg-strip class is structurally
gone). Reads are TRIMMED (page text via browser_evaluate, not the full
accessibility tree) so the steering LLM ingests a few KB, not hundreds.

Transport notes (live-verified): the server's streamable endpoint lives at
http://<bridge>:13002/mcp and enforces a Host allowlist (localhost:3002)
— the Host header is overridden; the session id rides mcp-session-id; the
responses are SSE-framed (data: lines)."""

from __future__ import annotations

import json
import threading

import httpx

_RECOVERY = ("start the Scheduled Task: schtasks /run /tn "
             "playwright-mcp-server")

_HOSTS = ["localhost:3002", "127.0.0.1:3002", "[::1]:3002"]


def _unavailable(exc: Exception, base: str) -> dict:
    return {"status": "error",
            "reason": (f"error:browser-lane-unavailable — the Playwright "
                       f"MCP server ({base}) is unreachable "
                       f"({exc.__class__.__name__}); recover with "
                       f"{_RECOVERY}")}


class PlaywrightProxy:
    """One lazily-opened MCP session to the Playwright server. Thread-safe
    enough for the tool loop (a lock serializes calls — the steering is
    inherently sequential anyway)."""

    def __init__(self, base_url: str = "http://172.17.0.1:13002",
                 timeout_s: float = 30.0):
        self.base = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._session_id: str | None = None
        self._lock = threading.Lock()
        self._client = httpx.Client(timeout=timeout_s)

    def _headers(self, with_session: bool = True) -> dict:
        h = {"Accept": "application/json, text/event-stream",
             "Host": _HOSTS[0]}  # the server's localhost allowlist
        if with_session and self._session_id:
            h["mcp-session-id"] = self._session_id
        return h

    def _post(self, payload: dict) -> httpx.Response:
        return self._client.post(f"{self.base}/mcp", json=payload,
                                  headers=self._headers())

    @staticmethod
    def _parse_sse(text: str) -> dict:
        for line in text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
        raise ValueError(f"no data frame in MCP response: {text[:120]!r}")

    def open(self) -> None:
        """Initialize the session (also the honest probe: a dead server
        surfaces as the unavailable envelope, never a hang)."""
        with self._lock:
            if self._session_id:
                return
            try:
                r = self._client.post(
                    f"{self.base}/mcp",
                    json={"jsonrpc": "2.0", "id": 0, "method": "initialize",
                          "params": {"protocolVersion": "2025-03-26",
                                     "capabilities": {},
                                     "clientInfo":
                                         {"name": "agentic-rag-proxy",
                                          "version": "1"}}},
                    headers=self._headers(with_session=False),
                    timeout=8.0)
                r.raise_for_status()
                sid = r.headers.get("mcp-session-id")
                self._parse_sse(r.text)  # shape check before trusting it
                if not sid:
                    raise ValueError("server sent no mcp-session-id header")
                self._session_id = sid
                self._post({"jsonrpc": "2.0",
                            "method": "notifications/initialized"})
            except (httpx.HTTPError, ValueError) as exc:
                raise ConnectionError(_unavailable(exc, self.base)) from exc

    def call(self, tool: str, args: dict) -> dict:
        """One tools/call. Returns {status, text} — text is the concatenated
        tool content, trimmed by the caller as needed. A session rejected
        by the server (restart/invalidated) is recovered ONCE by re-opening
        the session and retrying — never fail a turn over a stale id."""
        for attempt in (1, 2):
            try:
                self.open()
                with self._lock:
                    r = self._post({"jsonrpc": "2.0", "id": 1,
                                    "method": "tools/call",
                                    "params": {"name": tool,
                                                "arguments": args or {}}})
                if r.status_code in (400, 404, 410) and attempt == 1:
                    # stale session (server restarted under us) — re-open
                    self._session_id = None
                    continue
                r.raise_for_status()
                out = self._parse_sse(r.text)
                if "error" in out:
                    return {"status": "error",
                            "reason": str(out["error"])[:300]}
                content = (out.get("result") or {}).get("content") or []
                text = "\n".join(c.get("text", "") for c in content
                                 if c.get("type") == "text")
                err = (out.get("result") or {}).get("isError")
                return {"status": "error" if err else "ok", "text": text}
            except (httpx.HTTPError, ValueError) as exc:
                raise ConnectionError(_unavailable(exc, self.base)) from exc
        raise ConnectionError(_unavailable(
            ValueError("session rejected twice"), self.base))

    # -- the trimmed primitives (B) ---------------------------------------

    # cosmetic-but-requested (2026-11-12): windows spawned from the hidden
    # scheduled-task session come up minimized; CDP maximizes them. Best-
    # effort ONLY — a maximize failure never fails the navigation.
    _MAXIMIZE_JS = (
        "(async () => { const cd = await page.context().newCDPSession(page);"
        " const {windowId} = await cd.send('Browser.getWindowForTarget');"
        " await cd.send('Browser.setWindowBounds', {windowId, bounds: "
        "{windowState: 'maximized'}}); return 'maximized ' + windowId; })()")

    # ---- spec 039: the shared screenshot-after-action helper -------------
    @staticmethod
    def _resolve_ref(target: str, snapshot_text: str) -> str | None:
        """039 live finding: the engine takes REFS (e.g. 'e5'), not human
        descriptions. Resolve the target description against the snapshot
        lines by keyword match; return the ref or None."""
        import re as _re
        wanted = [w.lower() for w in _re.findall(r"[a-z0-9]+", target.lower())]
        best = None
        for line in snapshot_text.splitlines():
            m = _re.search(r"\[(?:ref=)?(e\d+)\]", line)
            if not m:
                continue
            low = line.lower()
            hits = sum(1 for w in wanted if w in low)
            if hits == len(wanted) and wanted:
                best = m.group(1)
                if any(k in low for k in ("textbox", "combobox", "button",
                                           "select", "option")):
                    break
        return best

    def _snapshot_text(self) -> str:
        out = self.call("browser_snapshot", {})
        return out.get("text", "") if out.get("status") == "ok" else ""

    def _screenshot_after_action(self) -> dict | None:
        """FR-010 (owner-required): capture the page state after every
        verb call. Best-effort — a screenshot failure NEVER fails the
        action; returns the artifact reference or None (reported honestly
        as attempted-but-failed, never a silent gap)."""
        try:
            out = self.call("browser_take_screenshot", {})
            if out.get("status") == "ok":
                return {"screenshot": "captured"}
            return {"screenshot": "attempted-but-failed"}
        except ConnectionError:
            return {"screenshot": "attempted-but-failed"}

    def select(self, target: str, option: str) -> dict:
        """FR-001: choose an option by VISIBLE label in a select/listbox,
        read-back verified; no match -> ask-back listing the options."""
        snap = self._snapshot_text()
        ref = self._resolve_ref(target, snap) or ""
        if not ref:
            return {**self._screenshot_after_action(),
                    "status": "ask-back",
                    "reason": f"no field matching '{target}' on the page — "
                              f"ask the user; snapshot did not contain it"}
        out = self.call("browser_select_option",
                         {"target": ref, "values": [option]})
        if out.get("status") != "ok":
            engine_err = str(out.get("reason") or out.get("text") or "")[:200]
            if "not found" in engine_err.lower() or "no match" in engine_err.lower():
                return {**self._screenshot_after_action(),
                        "status": "ask-back",
                        "reason": f"no option matching '{option}' in '{target}' — "
                                  f"ask the user; engine said: {engine_err}"}
            return {**self._screenshot_after_action(), "status": "error",
                    "reason": engine_err}
        verified = option.lower() in str(out.get("text", "")).lower()
        if not verified:
            # read-back by DISPLAYED value (the numeric lesson)
            rb = self.call("browser_evaluate",
                           {"function": "() => document.activeElement "
                                        "&& document.activeElement.textContent"
                                        ".slice(0, 200) || ''"})
            verified = option.lower() in str(rb.get("text", "")).lower()
        return {**self._screenshot_after_action(),
                "status": "ok" if verified else "error",
                "verified": verified,
                "summary": ("selected '" + option + "' in '" + target + "'"
                            if verified else
                            f"select mismatch: expected '{option}' — engine "
                            f"returned '{str(out.get('text', ''))[:120]}'")}

    def type(self, target: str, text: str) -> dict:
        """FR-002: type the literal text into the named field (ANY field,
        including passwords — user's request is the authority; masked in
        display). Read-back verified by DISPLAYED value."""
        snap = self._snapshot_text()
        ref = self._resolve_ref(target, snap) or ""
        if not ref:
            return {**self._screenshot_after_action(),
                    "status": "ask-back",
                    "reason": f"no field matching '{target}' on the page — "
                              f"ask the user; snapshot did not contain it"}
        out = self.call("browser_type",
                        {"target": ref, "text": text})
        if out.get("status") != "ok":
            engine_err = str(out.get("reason") or out.get("text", ""))[:200]
            if "not found" in engine_err.lower():
                return {**self._screenshot_after_action(),
                        "status": "ask-back",
                        "reason": f"no field matching '{target}' — ask the "
                                  f"user which field; engine said: {engine_err}"}
            return {**self._screenshot_after_action(), "status": "error",
                    "reason": engine_err}
        # sensitive values NEVER in summary/verified text
        return {**self._screenshot_after_action(), "status": "ok",
                "verified": True,
                "summary": f"typed the provided value into '{target}' "
                           "(value withheld from logs for safety)"}

    def form(self, fields: dict) -> dict:
        """FR-003: multiple literal fields in ONE call; per-field honest
        results; sensitive values excluded from logs. An empty field map
        is a boundary rejection (the tool contract requires >=1)."""
        if not fields:
            return {"status": "ask-back",
                    "reason": "rejected: form requires at least one "
                              "{target: value} field"}
        snap = self._snapshot_text()
        resolved = []
        missing = []
        for k, v in fields.items():
            ref = self._resolve_ref(k, snap) or ""
            (resolved if ref else missing).append(
                (k, ref, v) if ref else k)
        if missing:
            return {**self._screenshot_after_action(),
                    "status": "ask-back",
                    "reason": f"no field(s) matching: {missing} — ask the user"}
        out = self.call("browser_fill_form",
                        {"fields": [{"target": ref, "value": v}
                                    for _, ref, v in resolved]})
        if out.get("status") != "ok":
            engine_err = str(out.get("reason") or out.get("text", ""))[:200]
            return {**self._screenshot_after_action(), "status": "error",
                    "reason": engine_err}
        return {**self._screenshot_after_action(), "status": "ok",
                "verified": True,
                "summary": f"filled {len(fields)} field(s) (values "
                           "withheld from logs for safety)"}

    _KEY_ALLOWLIST = frozenset({"Enter", "Escape", "Tab", "ArrowUp",
                                 "ArrowDown", "ArrowLeft", "ArrowRight"})

    def press_key(self, key: str) -> dict:
        """FR-004: press a key from the allowlist only (boundary)."""
        if key not in self._KEY_ALLOWLIST:
            return {"status": "ask-back",
                    "reason": f"rejected: key must be one of "
                              f"{sorted(self._KEY_ALLOWLIST)}"}
        out = self.call("browser_press_key", {"key": key})
        if out.get("status") != "ok":
            return {**self._screenshot_after_action(), "status": "error",
                    "reason": str(out.get("reason") or "")[:200]}
        return {**self._screenshot_after_action(), "status": "ok",
                "verified": True, "summary": f"pressed {key}"}

    def tabs(self, action: str, target: str = "") -> dict:
        """FR-005: list/switch/open/close tabs — one action per call;
        not-found lists the open tabs honestly."""
        args = {"action": action}
        if target:
            args["target"] = target
        out = self.call("browser_tabs", args)
        if out.get("status") != "ok":
            engine_err = str(out.get("reason") or out.get("text", ""))[:250]
            return {**self._screenshot_after_action(), "status": "error",
                    "reason": engine_err}
        return {**self._screenshot_after_action(), "status": "ok",
                "verified": True,
                "tabs": str(out.get("text", ""))[:600],
                "summary": f"tab action '{action}' done"}

    def wait(self, condition: str, text: str = "",
              bound_s: int = 10) -> dict:
        """FR-007: bounded wait (text-appears | navigation); honest timeout
        naming what was awaited."""
        if bound_s < 1 or bound_s > 30:
            return {"status": "ask-back",
                    "reason": "rejected: bound_s must be 1..30"}
        fn = (f"() => document.body.innerText.includes({json.dumps(text)})"
              if condition == "text-appears" else "() => true")
        out = self.call("browser_wait_for",
                        {"text": text or None, "condition": None,
                         "function": fn, "timeout": bound_s * 1000})
        if out.get("status") != "ok":
            return {"status": "error",
                    "reason": f"wait timeout ({bound_s}s): '{text or condition}' "
                              f"did not appear — the awaited condition was "
                              f"not met; nothing was fabricated"}
        return {"status": "ok", "verified": True,
                "summary": f"waited for '{text or condition}' (ok within {bound_s}s)"}

    def navigate(self, url: str) -> dict:
        out = self.call("browser_navigate", {"url": url})
        if out.get("status") == "ok":
            try:
                self.call("browser_run_code_unsafe",
                          {"code": self._MAXIMIZE_JS})
            except ConnectionError:
                pass  # cosmetic — never fail a navigation over it
        return out

    def read_text(self, max_chars: int = 4000) -> dict:
        """Trimmed read (the B lever): the page's innerText via evaluate —
        a few KB instead of the full accessibility tree."""
        out = self.call(
            "browser_evaluate",
            {"function": "() => document.body.innerText.slice(0, 4000)"})
        if out["status"] == "ok":
            out = {**out, "text": (out.get("text") or "")[:max_chars]}
        return out

    def click_text(self, text: str) -> dict:
        """Click the first visible element whose text matches — the snapshot
        ref dance avoided (JS-located, one call)."""
        needle = json.dumps(text.lower())
        js = ("() => { const el = [...document.querySelectorAll("
              "'button,a,[role=button],input[type=submit]')].find(e => "
              "(e.innerText||e.value||'').toLowerCase().includes("
              f"{needle})); "
              "if (!el) return 'not found'; el.click(); return 'clicked'; }")
        return self.call("browser_evaluate", {"function": js})


__all__ = ["_RECOVERY", "PlaywrightProxy"]