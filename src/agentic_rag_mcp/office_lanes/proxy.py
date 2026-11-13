"""Office v2 (2026-11-13, slow-total-time-75-6-seconds): the single-hop
document proxy — the browser-v2 pattern applied to OfficeMCP.

The office lane (hermes_office_task) rides a full Hermes-agent turn: ~5
narrated steps × an LLM round each = 75.6 s measured for a trivial
document-write, while the COM calls are milliseconds. This proxy holds ONE
persistent legacy-SSE session to OfficeMCP and executes FIXED, tested
RunPython templates (the code is ours — deterministic, parameterized via
the tool's `data` argument, never agent-composed) with the verification
discipline moved INTO code (exists / size / content read-back), so a
simple document-write is one sidecar call.

The `output` variable is OfficeMCP's return channel (probed live); the
result arrives as a JSON string in the tool content."""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid

import httpx

_RECOVERY = ("recover: the OfficeMCP service runs as the officemcp-server "
             "Scheduled Task on the Windows host (sse :8888)")

_WRITE_TEMPLATE = """
import json, os
d = json.loads(data)
import win32com.client
word = win32com.client.Dispatch('Word.Application')
word.Visible = True
doc = word.Documents.Add()
doc.Content.Text = d['text']
root = d['root']
os.makedirs(root, exist_ok=True)
path = os.path.join(root, d['name'])
existed = os.path.exists(path)
doc.SaveAs2(path)
size = os.path.getsize(path)
ok = d['text'].strip() in doc.Content.Text.strip()
doc.Close()
output = json.dumps({'path': path, 'size': size, 'existed': bool(existed),
                     'text_ok': bool(ok)})
"""

_READ_TEMPLATE = """
import json, os
d = json.loads(data)
import win32com.client
word = win32com.client.Dispatch('Word.Application')
word.Visible = True
path = os.path.join(d['root'], d['name'])
if not os.path.exists(path):
    output = json.dumps({'missing': True})
else:
    doc = word.Documents.Open(path, ReadOnly=True)
    text = doc.Content.Text
    doc.Close(False)
    output = json.dumps({'missing': False, 'size': os.path.getsize(path),
                         'text': text[:4000]})
"""


class OfficeProxy:
    """One persistent legacy-SSE MCP session to OfficeMCP (via the docker0
    bridge). A background reader thread feeds a queue; calls correlate by
    request id. A dropped stream re-opens once — never fail a turn over a
    stale session."""

    def __init__(self, base_url: str = "http://172.17.0.1:18888",
                 timeout_s: float = 180.0):
        self.base = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._lock = threading.Lock()
        self._start_session()

    # -- transport ---------------------------------------------------------

    def _start_session(self) -> None:
        self._events: queue.Queue[str] = __import__("queue").Queue()
        self._sse = httpx.stream(
            "GET", f"{self.base}/sse",
            headers={"Accept": "text/event-stream"}, timeout=self.timeout_s)
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()
        endpoint = self._events.get(timeout=10)
        if not endpoint.startswith("/"):
            raise ConnectionError("bad SSE endpoint from OfficeMCP")
        self._endpoint = endpoint
        self._post({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                    "params": {"protocolVersion": "2025-03-26",
                               "capabilities": {},
                               "clientInfo": {"name": "agentic-rag-office-v2",
                                              "version": "1"}}})
        self._next(events=False, want_id=0)
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _reader(self) -> None:
        try:
            with self._sse as r:
                for line in r.iter_lines():
                    if line.startswith("data:"):
                        self._events.put(line[5:].strip())
        except Exception:  # noqa: BLE001 — the stream died; _ensure re-opens
            self._endpoint = None

    def _post(self, obj: dict) -> None:
        r = httpx.post(f"{self.base}{self._endpoint}", json=obj,
                       timeout=self.timeout_s)
        r.raise_for_status()

    def _ensure(self) -> None:
        if getattr(self, "_endpoint", None):
            return
        with self._lock:
            if not getattr(self, "_endpoint", None):
                self._start_session()

    def _next(self, events: bool = True, want_id: int | None = None) -> dict:
        """Next JSON frame: from the queue (with the shared reader) or by
        draining the stream — this client uses a queue-fed reader."""
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            try:
                frame = self._events.get(timeout=max(0.1,
                                      deadline - time.monotonic()))
                obj = json.loads(frame)
                if want_id is not None and obj.get("id") != want_id:
                    continue  # a stale reply from a dead session — skip
                return obj
            except queue.Empty:
                pass  # loop until the deadline
            except (json.JSONDecodeError, TypeError):
                continue  # a torn frame from a dying stream — skip
        raise ConnectionError("OfficeMCP response timeout")

    # -- the call -----------------------------------------------------------

    def call(self, tool: str, arguments: dict) -> dict:
        """One tools/call. Returns {status, text}. Stale-session replies are
        skipped; a dead stream re-opens once."""
        for attempt in (1, 2):
            self._ensure()
            rid = uuid.uuid4().int % (2 ** 31)
            with self._lock:
                try:
                    self._post({"jsonrpc": "2.0", "id": rid,
                                "method": "tools/call",
                                "params": {"name": tool,
                                            "arguments": arguments}})
                except httpx.HTTPError:
                    if attempt == 1:
                        self._endpoint = None
                        continue
                    raise
            try:
                out = self._next(want_id=rid)
            except ConnectionError:
                if attempt == 1:
                    self._endpoint = None
                    continue
                raise
            if "error" in out:
                return {"status": "error",
                        "reason": str(out["error"])[:300]}
            content = (out.get("result") or {}).get("content") or []
            text = "\n".join(c.get("text", "") for c in content
                             if c.get("type") == "text")
            return {"status": "ok", "text": text}
        raise ConnectionError("OfficeMCP unreachable after retry")

    # -- the deterministic document primitives ------------------------------

    @staticmethod
    def _payload_json(tool_text: str) -> dict | None:
        """The tool text is {"success":..., "output":"<json string>"} — the
        payload rides the output field as a JSON STRING (probed live)."""
        try:
            envelope = json.loads(tool_text)
            payload = envelope.get("output")
            m = json.loads(payload) if isinstance(payload, str) else payload
            return m if isinstance(m, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None

    def write_doc(self, text: str, name: str, root: str) -> dict:
        """Create a Word document with the literal text, save as `name` in
        `root`, and verify IN CODE (exists, size, content). Overwrites are
        reported honestly (`existed`) — the spec-031 REPLACED discipline,
        detected server-side."""
        out = self.call("RunPython",
                        {"code": _WRITE_TEMPLATE,
                         "data": json.dumps({"text": text, "name": name,
                                             "root": root})})
        if out.get("status") != "ok":
            return out
        payload = self._payload_json(out["text"])
        if payload is None or "path" not in payload:
            return {"status": "error",
                    "reason": f"error:office-v2 malformed result — {out['text'][:200]}"}
        if not payload.get("text_ok"):
            return {"status": "error",
                    "reason": "error:office-v2 verification failed — the "
                              "saved document does not contain the literal text"}
        return {"status": "ok", **payload}

    def read_doc(self, name: str, root: str) -> dict:
        """Read a document's text back (read-only) — the verify/report half."""
        out = self.call("RunPython",
                        {"code": _READ_TEMPLATE,
                         "data": json.dumps({"name": name, "root": root})})
        if out.get("status") != "ok":
            return out
        payload = self._payload_json(out["text"])
        if payload is None:
            return {"status": "error",
                    "reason": f"error:office-v2 malformed result — {out['text'][:200]}"}
        if payload.get("missing"):
            return {"status": "error",
                    "reason": f"error:not-found — no document named {name!r}"}
        return {"status": "ok", **payload}

    def root_folder(self) -> str:
        out = self.call("RootFolder", {})
        return out.get("text", "").strip() if out.get("status") == "ok" else ""
