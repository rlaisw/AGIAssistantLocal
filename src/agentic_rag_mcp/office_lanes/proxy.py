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
# COM apartment guard (2026-11-14): some RunPython workers execute scripts
# on a COM-uninitialized thread (-2147221008); failures here must not block
# a healthy apartment, a broken one still surfaces its real error
import pythoncom
try:
    pythoncom.CoInitialize()
except Exception:
    pass
# xls-saveas-method-failed (2026-11-14): attach to the RUNNING Word when
# one exists — a bare Dispatch can spawn a second instance that holds no
# documents while the user's Word locks the target file
try:
    word = win32com.client.GetActiveObject('Word.Application')
except Exception:
    word = win32com.client.Dispatch('Word.Application')
# xls-saveas-method-failed (live follow-up): a busy Word refuses COM calls
# until its pump timeout — name the situation honestly
try:
    word.Visible = True
except Exception as _e:
    raise RuntimeError(
        'blocked: Word is busy or showing a dialog and refused '
        'automation (press ESC in Word or close its dialog, then ask '
        'again) [%s]' % str(_e)[:150])
root = d['root']
os.makedirs(root, exist_ok=True)
path = os.path.join(root, d['name'])
# lock-free repeats WITHOUT hiding the result (faile-to-write-context-
# to-word, 2026-11-13): close ONLY an already-open doc at the SAME path
# (never the user's other documents), then write fresh and LEAVE THE NEW
# DOCUMENT OPEN AND VISIBLE — "open Word and type X" means the text is on
# screen, not just in the file.
# (xls-saveas-method-failed, 2026-11-14): the close is verified and honest
# — Word refuses SaveAs2 onto an open document, so retry once, record
# close failures, and refuse with the situation named instead of letting
# SaveAs2 surface the raw COM error
def _same_path(doc):
    try:
        return os.path.normcase(doc.FullName) == os.path.normcase(path)
    except Exception:
        return False
_close_errors = []
for _attempt in range(2):
    if not any(_same_path(doc) for doc in word.Documents):
        break
    for doc in list(word.Documents):
        if _same_path(doc):
            try:
                doc.Close(False)
            except Exception as _e:
                _close_errors.append(str(_e))
if any(_same_path(doc) for doc in word.Documents):
    raise RuntimeError(
        'blocked: the target file %s is open in Word and could not be '
        'closed automatically (%s); save it or close it in Word, or '
        'choose a different name, then ask again'
        % (d['name'], '; '.join(_close_errors)[:200] or 'close failed'))
existed = os.path.exists(path)
doc = word.Documents.Add()
doc.Content.Text = d['text']
doc.SaveAs2(path)
size = os.path.getsize(path)
ok = d['text'].strip() in doc.Content.Text.strip()
# owner request 2026-11-13: when the write completes, Word goes FULL-SCREEN
# and comes to the FRONT (the playwright lesson: the ALT tap clears the
# foreground lock the RDP client holds). Best-effort — never fails the write.
fronted = False
try:
    import time as _t
    import ctypes
    # THIS instance's own window handle (FindWindow can grab another Word
    # instance's window when several are running — probed live)
    hwnd = int(word.ActiveWindow.Hwnd)
    if hwnd:
        u32 = ctypes.windll.user32
        if u32.IsIconic(hwnd):
            u32.ShowWindow(hwnd, 9)
        u32.ShowWindow(hwnd, 3)
        u32.keybd_event(0x12, 0, 0, 0)
        u32.keybd_event(0x12, 0, 2, 0)
        u32.SetForegroundWindow(hwnd)
        _t.sleep(0.3)  # the foreground change lands asynchronously
        fronted = bool(u32.GetForegroundWindow() == hwnd)
except Exception:
    fronted = False
output = json.dumps({'path': path, 'size': size, 'existed': bool(existed),
                     'text_ok': bool(ok), 'open_docs': int(word.Documents.Count),
                     'fronted': bool(fronted)})
"""

_READ_TEMPLATE = """
import json, os
d = json.loads(data)
import win32com.client
# COM apartment guard (2026-11-14): some RunPython workers execute scripts
# on a COM-uninitialized thread (-2147221008); failures here must not block
# a healthy apartment, a broken one still surfaces its real error
import pythoncom
try:
    pythoncom.CoInitialize()
except Exception:
    pass
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


_XLS_WRITE_TEMPLATE = """
import json, os
d = json.loads(data)
import win32com.client
# COM apartment guard (2026-11-14): see the Word template note
import pythoncom
try:
    pythoncom.CoInitialize()
except Exception:
    pass
# xls-saveas-method-failed (2026-11-14): attach to the RUNNING Excel when
# one exists (the v1 lane's proven pattern) — a bare Dispatch can spawn a
# second instance that holds no workbooks while the user's Excel locks
# the target file
try:
    xl = win32com.client.GetActiveObject('Excel.Application')
except Exception:
    xl = win32com.client.Dispatch('Excel.Application')
# xls-saveas-method-failed (live follow-up): a busy Excel (cell edit mode
# or a dialog) refuses COM calls until its ~180 s pump timeout — name the
# situation honestly instead of surfacing the raw property error
try:
    xl.Visible = True
except Exception as _e:
    raise RuntimeError(
        'blocked: Excel is busy or showing a dialog and refused '
        'automation (press ESC in Excel or close its dialog, then ask '
        'again) [%s]' % str(_e)[:150])
root = d['root']
os.makedirs(root, exist_ok=True)
path = os.path.join(root, d['name'])
# lock-free repeats (the Word lesson): close ONLY a same-path workbook —
# but honestly (xls-saveas-method-failed, 2026-11-14): Excel refuses
# SaveAs onto an open workbook, so verify the close worked, retry once,
# record close failures, and refuse with the situation named instead of
# surfacing the raw COM error from SaveAs
def _same_path(w):
    try:
        return os.path.normcase(w.FullName) == os.path.normcase(path)
    except Exception:
        return False
_close_errors = []
for _attempt in range(2):
    if not any(_same_path(w) for w in xl.Workbooks):
        break
    for w in list(xl.Workbooks):
        if _same_path(w):
            try:
                w.Close(False)
            except Exception as _e:
                _close_errors.append(str(_e))
if any(_same_path(w) for w in xl.Workbooks):
    raise RuntimeError(
        'blocked: the target file %s is open in Excel and could not be '
        'closed automatically (%s); save it or close it in Excel, or '
        'choose a different name, then ask again'
        % (d['name'], '; '.join(_close_errors)[:200] or 'close failed'))
existed = os.path.exists(path)
wb = xl.Workbooks.Add()
ok = True
for addr, val in d['cells'].items():
    col = 0; row = 0
    for ch in addr:
        if ch.isalpha():
            col = col * 26 + (ord(ch.upper()) - 64)
        else:
            row = int(ch)
    wb.ActiveSheet.Cells(row, col).Value = val
    # still-little-bit-slow (2026-11-13): verify the DISPLAYED literal
    # (.Text) — Excel coerces numeric strings to float ('12345' -> 12345.0)
    # and str(.Value) != '12345', but .Text returns the literal '12345'
    if str(wb.ActiveSheet.Cells(row, col).Text) != str(val):
        ok = False
# xls-saveas-method-failed round 2 (2026-11-14): Excel — alone of the
# three apps — asks "replace existing file?" via a dialog on SaveAs; in
# headless COM the dialog cannot be shown and the call dies with
# 0x800A03EC. DisplayAlerts=False makes the overwrite silent; it is
# scoped to this call and restored, so the user's Excel keeps its normal
# prompts.
xl.DisplayAlerts = False
try:
    wb.SaveAs(path)
except Exception as _e:
    raise RuntimeError(
        'blocked: saving %s failed (%s); the file may be open in Excel '
        'under a recovered or temporary name (close the recovered copies '
        'in Excel or choose a different name), then ask again'
        % (d['name'], str(_e)[:200]))
finally:
    xl.DisplayAlerts = True
size = os.path.getsize(path)
fronted = False
try:
    import ctypes
    u32 = ctypes.windll.user32
    hwnd = int(xl.ActiveWindow.Hwnd)
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, 9)
    u32.ShowWindow(hwnd, 3)
    u32.keybd_event(0x12, 0, 0, 0)
    u32.keybd_event(0x12, 0, 2, 0)
    u32.SetForegroundWindow(hwnd)
    import time as _t
    _t.sleep(0.3)
    fronted = bool(u32.GetForegroundWindow() == hwnd)
except Exception:
    fronted = False
output = json.dumps({'path': path, 'size': size, 'existed': bool(existed),
                     'text_ok': bool(ok), 'fronted': bool(fronted)})
"""

_PPT_WRITE_TEMPLATE = """
import json, os
d = json.loads(data)
import win32com.client
# COM apartment guard (2026-11-14): see the Word template note
import pythoncom
try:
    pythoncom.CoInitialize()
except Exception:
    pass
# xls-saveas-method-failed (2026-11-14): attach to the RUNNING PowerPoint
# when one exists, and make the same-path pre-close verified and honest —
# PowerPoint refuses SaveAs onto an open presentation the same way Excel
# and Word do
try:
    ppt = win32com.client.GetActiveObject('Powerpoint.Application')
except Exception:
    ppt = win32com.client.Dispatch('Powerpoint.Application')
# xls-saveas-method-failed (live follow-up): a busy PowerPoint refuses COM
# calls until its pump timeout — name the situation honestly
try:
    ppt.Visible = True
except Exception as _e:
    raise RuntimeError(
        'blocked: PowerPoint is busy or showing a dialog and refused '
        'automation (press ESC in PowerPoint or close its dialog, then '
        'ask again) [%s]' % str(_e)[:150])
root = d['root']
os.makedirs(root, exist_ok=True)
path = os.path.join(root, d['name'])
def _same_path(p):
    try:
        return os.path.normcase(p.FullName) == os.path.normcase(path)
    except Exception:
        return False
_close_errors = []
for _attempt in range(2):
    if not any(_same_path(p) for p in ppt.Presentations):
        break
    for p in list(ppt.Presentations):
        if _same_path(p):
            try:
                p.Close()
            except Exception as _e:
                _close_errors.append(str(_e))
if any(_same_path(p) for p in ppt.Presentations):
    raise RuntimeError(
        'blocked: the target file %s is open in PowerPoint and '
        'could not be closed automatically (%s); save it or close it in '
        'PowerPoint, or choose a different name, then ask again'
        % (d['name'], '; '.join(_close_errors)[:200] or 'close failed'))
existed = os.path.exists(path)
pres = ppt.Presentations.Add()
slide = pres.Slides.Add(1, 2)  # ppLayoutText
slide.Shapes.Placeholders(1).TextFrame.TextRange.Text = d['title']
if d.get('text'):
    slide.Shapes.Placeholders(2).TextFrame.TextRange.Text = d['text']
pres.SaveAs(path)
size = os.path.getsize(path)
ok = (slide.Shapes.Placeholders(1).TextFrame.TextRange.Text == d['title'])
fronted = False
try:
    # PowerPoint quirk (probed 2026-11-13): ActiveWindow.HWND is not usable
    # via dynamic dispatch — the PPTFrameClass window is the reliable handle
    import win32gui, ctypes
    u32 = ctypes.windll.user32
    hwnd = win32gui.FindWindow('PPTFrameClass', None)
    if hwnd:
        if u32.IsIconic(hwnd):
            u32.ShowWindow(hwnd, 9)
        u32.ShowWindow(hwnd, 3)
        u32.keybd_event(0x12, 0, 0, 0)
        u32.keybd_event(0x12, 0, 2, 0)
        u32.SetForegroundWindow(hwnd)
        import time as _t
        _t.sleep(0.3)
        fronted = bool(u32.GetForegroundWindow() == hwnd)
except Exception:
    fronted = False
output = json.dumps({'path': path, 'size': size, 'existed': bool(existed),
                     'text_ok': bool(ok), 'fronted': bool(fronted)})
"""

_WORD_PRINT_TEMPLATE = """
import ctypes
import json
import subprocess
import time
import pythoncom
import win32com.client

_initialized = False
_stage = 'com-initialize'
try:
    pythoncom.CoInitialize()
    _initialized = True
    _stage = 'attach'
    try:
        word = win32com.client.GetActiveObject('Word.Application')
    except Exception as _attach_exc:
        _processes = subprocess.check_output(
            ['tasklist', '/FI', 'IMAGENAME eq WINWORD.EXE',
             '/FO', 'CSV', '/NH'], text=True, timeout=5)
        winword_running = 'WINWORD.EXE' in _processes.upper()
        if winword_running:
            _attach_message = str(_attach_exc).lower()
            if any(marker in _attach_message for marker in
                   ('busy', 'modal', '0x8001010a', '-2147417846',
                    'retry later', 'call was rejected by callee', 'servercall')):
                raise RuntimeError('word-busy-modal')
            raise RuntimeError('word-running-com-unregistered')
        if not winword_running:
            word = win32com.client.Dispatch('Word.Application')
    _stage = 'snapshot-before'
    before_count = int(word.Documents.Count)
    before_saved = [
        bool(word.Documents.Item(index).Saved)
        for index in range(1, before_count + 1)
    ]
    blank_created = False
    if before_count == 0:
        doc = word.Documents.Add()
        blank_created = True
    else:
        doc = word.ActiveDocument
    _stage = 'visible'
    word.Visible = True
    _stage = 'preview'
    doc.PrintPreview()
    _stage = 'verify'
    preview_ok = (bool(word.PrintPreview)
                  and int(word.ActiveWindow.View.Type) == 4)
    view_type = int(word.ActiveWindow.View.Type)
    hwnd = int(word.ActiveWindow.Hwnd)
    u32 = ctypes.windll.user32
    visible = bool(word.Visible) and bool(u32.IsWindowVisible(hwnd))
    foreground = False
    try:
        if u32.IsIconic(hwnd):
            u32.ShowWindow(hwnd, 9)
        u32.keybd_event(0x12, 0, 0, 0)
        u32.keybd_event(0x12, 0, 2, 0)
        u32.SetForegroundWindow(hwnd)
        time.sleep(0.3)
        foreground = bool(u32.GetForegroundWindow() == hwnd)
    except Exception:
        foreground = False
    _stage = 'snapshot-after'
    after_count = int(word.Documents.Count)
    after_saved = [
        bool(word.Documents.Item(index).Saved)
        for index in range(1, after_count + 1)
    ]
    count_ok = after_count == before_count + int(blank_created)
    saved_ok = before_saved == after_saved[:before_count]
    documents_preserved = count_ok and saved_ok
    output = json.dumps({
        'preview_ok': bool(preview_ok),
        'view_type': view_type,
        'visible': bool(visible),
        'foreground': bool(foreground),
        'blank_created': bool(blank_created),
        'document_count': after_count,
        'count_ok': bool(count_ok),
        'saved_ok': bool(saved_ok),
        'documents_preserved': bool(documents_preserved),
    })
except Exception as _exc:
    _message = str(_exc).lower()
    if 'word-running-com-unregistered' in _message:
        _kind = 'running-unregistered'
    elif (isinstance(_exc, subprocess.TimeoutExpired)
          or 'timeout' in _message or 'timed out' in _message):
        _kind = 'timeout'
    elif (_stage == 'preview' and any(
            marker in _message for marker in
            ('unsupported', 'not implemented', '0x80004001'))):
        _kind = 'unsupported'
    elif (any(marker in _message for marker in
              ('busy', 'modal', '0x8001010a', '-2147417846',
               'retry later', 'call was rejected by callee', 'servercall'))
          or _stage in ('visible', 'snapshot-before', 'snapshot-after')):
        _kind = 'busy-modal'
    else:
        _kind = 'com-error'
    output = json.dumps({'error_kind': _kind, 'stage': _stage,
                         'error_type': type(_exc).__name__})
finally:
    if _initialized:
        pythoncom.CoUninitialize()
"""

_WORD_PRINT_TIMEOUT_S = 30.0
_WORD_PRINT_ERRORS = {
    "busy-modal": (
        "error:word-print-busy-modal — Word is busy or has a modal dialog; "
        "no Backstage fallback was attempted"),
    "timeout": (
        "error:word-print-timeout — the bounded Word preview request timed "
        "out; no retry or Backstage fallback was attempted"),
    "unsupported": (
        "error:word-print-unsupported-preview — legacy Document.PrintPreview "
        "is unsupported; no Backstage fallback was attempted"),
    "running-unregistered": (
        "error:word-print-running-unregistered — Word is running but its COM "
        "server is not registered; no second instance was started"),
    "transport": (
        "error:word-print-transport — the bounded OfficeMCP request failed; "
        "no retry or Backstage fallback was attempted"),
    "malformed": (
        "error:word-print-malformed — OfficeMCP returned no verifiable "
        "preview result"),
    "com-error": (
        "error:word-print-com — Word automation failed safely; no Backstage "
        "fallback was attempted"),
}


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

    def _post(self, obj: dict, timeout_s: float | None = None) -> None:
        r = httpx.post(
            f"{self.base}{self._endpoint}", json=obj,
            timeout=self.timeout_s if timeout_s is None else timeout_s)
        r.raise_for_status()

    def _ensure(self) -> None:
        if getattr(self, "_endpoint", None):
            return
        with self._lock:
            if not getattr(self, "_endpoint", None):
                self._start_session()

    def _next(self, events: bool = True, want_id: int | None = None,
              timeout_s: float | None = None) -> dict:
        """Next JSON frame: from the queue (with the shared reader) or by
        draining the stream — this client uses a queue-fed reader."""
        deadline = time.monotonic() + (
            self.timeout_s if timeout_s is None else timeout_s)
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

    def _call_once(self, tool: str, arguments: dict,
                   timeout_s: float) -> dict:
        """One bounded attempt for operations whose outcome must not repeat."""
        self._ensure()
        rid = uuid.uuid4().int % (2 ** 31)
        with self._lock:
            self._post({"jsonrpc": "2.0", "id": rid,
                        "method": "tools/call",
                        "params": {"name": tool, "arguments": arguments}},
                       timeout_s=timeout_s)
        out = self._next(want_id=rid, timeout_s=timeout_s)
        if "error" in out:
            return {"status": "error", "reason": str(out["error"])[:300]}
        content = (out.get("result") or {}).get("content") or []
        text = "\n".join(c.get("text", "") for c in content
                         if c.get("type") == "text")
        return {"status": "ok", "text": text}

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

    def show_word_print(self) -> dict:
        """Show and verify Word Print Preview without repeating the action."""
        try:
            out = self._call_once("RunPython",
                                  {"code": _WORD_PRINT_TEMPLATE},
                                  _WORD_PRINT_TIMEOUT_S)
        except (httpx.HTTPError, ConnectionError) as exc:
            message = str(exc).lower()
            kind = ("timeout" if isinstance(exc, httpx.TimeoutException)
                    or "timeout" in message or "timed out" in message
                    else "transport")
            return {"status": "error", "reason": _WORD_PRINT_ERRORS[kind]}
        if out.get("status") != "ok":
            message = str(out.get("reason", "")).lower()
            if "timeout" in message or "timed out" in message:
                kind = "timeout"
            elif "busy" in message or "modal" in message:
                kind = "busy-modal"
            elif "unsupported" in message or "not implemented" in message:
                kind = "unsupported"
            else:
                kind = "transport"
            return {"status": "error", "reason": _WORD_PRINT_ERRORS[kind]}
        payload = self._payload_json(out.get("text", ""))
        if payload is None:
            return {"status": "error", "reason": _WORD_PRINT_ERRORS["malformed"]}
        if payload.get("error_kind"):
            kind = str(payload["error_kind"])[:40]
            if kind not in _WORD_PRINT_ERRORS:
                kind = "com-error"
            return {"status": "error", "reason": _WORD_PRINT_ERRORS[kind],
                    "stage": str(payload.get("stage", "unknown"))[:40]}
        required = ("preview_ok", "view_type", "visible", "foreground",
                    "blank_created", "document_count", "count_ok", "saved_ok",
                    "documents_preserved")
        if any(key not in payload for key in required):
            return {"status": "error", "reason": _WORD_PRINT_ERRORS["malformed"]}
        boolean_keys = ("preview_ok", "visible", "foreground", "blank_created",
                        "count_ok", "saved_ok", "documents_preserved")
        if (any(type(payload[key]) is not bool for key in boolean_keys)
                or type(payload["view_type"]) is not int
                or type(payload["document_count"]) is not int
                or payload["document_count"] < 0):
            return {"status": "error", "reason": _WORD_PRINT_ERRORS["malformed"]}
        payload = {key: payload[key] for key in required}
        preserved = all(payload.get(key) is True for key in
                        ("count_ok", "saved_ok", "documents_preserved"))
        if not preserved:
            return {"status": "error", **payload,
                    "reason": "error:word-print-preservation — document count "
                              "or Saved flags changed unexpectedly"}
        failures = []
        if payload.get("preview_ok") is not True or payload.get("view_type") != 4:
            failures.append("PrintPreview/View.Type unverified")
        if payload.get("visible") is not True:
            failures.append("window visibility unverified")
        if payload.get("foreground") is not True:
            failures.append("foreground HWND mismatch")
        if failures:
            return {"status": "partial", **payload,
                    "reason": "partial:word-print-display — " + "; ".join(failures)}
        return {"status": "ok", **payload}

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

    def write_xls(self, cells: dict, name: str, root: str) -> dict:
        """Create a workbook, write the literal cell map {addr: text},
        save, verify in code, leave open + fronted (the doc_write_v2
        discipline, extended per this bug)."""
        out = self.call("RunPython",
                        {"code": _XLS_WRITE_TEMPLATE,
                         "data": json.dumps({"cells": cells, "name": name,
                                             "root": root})})
        if out.get("status") != "ok":
            return out
        payload = self._payload_json(out["text"])
        if payload is None or "path" not in payload:
            return {"status": "error",
                    "reason": f"error:office-v2 malformed result — {out['text'][:200]}"}
        if not payload.get("text_ok"):
            return {"status": "error",
                    "reason": "error:office-v2 verification failed — a cell "
                              "did not read back the literal value"}
        return {"status": "ok", **payload}

    def write_ppt(self, title: str, text: str, name: str, root: str) -> dict:
        """Create a one-slide presentation (title + optional body text),
        save, verify, leave open + fronted."""
        out = self.call("RunPython",
                        {"code": _PPT_WRITE_TEMPLATE,
                         "data": json.dumps({"title": title, "text": text,
                                             "name": name, "root": root})})
        if out.get("status") != "ok":
            return out
        payload = self._payload_json(out["text"])
        if payload is None or "path" not in payload:
            return {"status": "error",
                    "reason": f"error:office-v2 malformed result — {out['text'][:200]}"}
        if not payload.get("text_ok"):
            return {"status": "error",
                    "reason": "error:office-v2 verification failed — the "
                              "slide title did not read back the literal text"}
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
