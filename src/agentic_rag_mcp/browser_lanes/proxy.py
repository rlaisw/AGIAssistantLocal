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

    def navigate(self, url: str) -> dict:
        return self.call("browser_navigate", {"url": url})

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