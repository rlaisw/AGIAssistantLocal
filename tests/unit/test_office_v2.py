"""Office v2 (slow-total-time-75-6-seconds, 2026-11-13): the single-hop
document primitives — name sanitization, payload parsing, templates."""

from __future__ import annotations

import ast
import inspect
import json
import re
import textwrap
import threading
from unittest.mock import Mock

import pytest

import agentic_rag_mcp.office_lanes.proxy as office_proxy
from agentic_rag_mcp.office_lanes.proxy import _WRITE_TEMPLATE, OfficeProxy


def _doc_name(name, text="some text"):
    # the helper lives inside build_server's closure — test the same rules
    import re
    if not name or not name.strip():
        words = re.sub(r"[^a-z0-9 ]", "", text.lower()).split()[:4]
        stem = "_".join(words) if words else "document"
        return stem[:50] + ".docx"
    clean = name.strip().replace("\\", "/").split("/")[-1]
    clean = re.sub(r"[^A-Za-z0-9._ -]", "_", clean)
    if clean in ("..", ".", "") or ".." in clean:
        clean = "document.docx"
    return clean if clean.lower().endswith(".docx") else clean + ".docx"


class TestNameSanitization:
    def test_default_name_from_text(self):
        assert _doc_name("", "Hello World From The Test") == "hello_world_from_the.docx"

    def test_bare_name_gets_docx(self):
        assert _doc_name("report") == "report.docx"

    def test_path_traversal_stripped(self):
        n = _doc_name("../../../etc/report.docx")
        assert n == "report.docx" and "/" not in n

    def test_backslash_path_stripped(self):
        n = _doc_name("C:\\Users\\RLWC145\\x.docx")
        assert n == "x.docx" and "\\" not in n

    def test_dotdot_rejected(self):
        assert ".." not in _doc_name("..")

    def test_weird_chars_sanitized(self):
        n = _doc_name("my:re*port?.docx")
        assert ":" not in n and "*" not in n and n.endswith(".docx")


class TestPayloadParsing:
    def test_envelope_output_field(self):
        # live-verified shape: {"success":true,"output":"<json string>"}
        inner = json.dumps({"path": "C:\\x\\a.docx", "size": 1,
                            "existed": False, "text_ok": True})
        tool_text = json.dumps({"success": True, "output": inner})
        m = OfficeProxy._payload_json(tool_text)
        assert m["path"] == "C:\\x\\a.docx" and m["text_ok"] is True

    def test_malformed_is_none(self):
        assert OfficeProxy._payload_json("not json") is None
        assert OfficeProxy._payload_json(json.dumps({"success": True})) is None


class TestTemplates:
    def test_write_template_verifies_and_keeps_visible(self):
        # faile-to-write-context-to-word (2026-11-13): verification IN code
        # AND the document stays OPEN (the user asked for text IN Word);
        # repeat-writes stay lock-free via a same-path pre-close
        assert "text_ok" in _WRITE_TEMPLATE
        assert "SaveAs2" in _WRITE_TEMPLATE
        assert "FullName" in _WRITE_TEMPLATE       # same-path pre-close
        assert "normcase" in _WRITE_TEMPLATE      # Windows-path-safe compare
        assert "open_docs" in _WRITE_TEMPLATE     # honest on-screen report
        # owner request 2026-11-13: maximize + front on completion
        # (the playwright lesson — the ALT tap beats the RDP foreground lock)
        assert "ActiveWindow.Hwnd" in _WRITE_TEMPLATE  # THIS instance's window (not FindWindow's topmost)
        assert "keybd_event" in _WRITE_TEMPLATE    # the ALT-tap
        assert "ShowWindow(hwnd, 3)" in _WRITE_TEMPLATE  # SW_MAXIMIZE
        assert "fronted" in _WRITE_TEMPLATE        # honest front report

    def test_write_template_never_closes_after_save(self):
        # the post-save Close (the screen-empty bug) must NOT return
        assert "doc.Close()\noutput" not in _WRITE_TEMPLATE

    def test_data_parameterization(self):
        # the literal text/name ride the `data` argument — the code is OURS,
        # never agent-composed (no injection surface)
        assert "json.loads(data)" in _WRITE_TEMPLATE
        assert "d['text']" in _WRITE_TEMPLATE


class TestXlsPptV2:
    """word-is-fast-but-excel... (2026-11-13): the v2 discipline extended to
    Excel and PowerPoint — literal-only cells (no formulas), same-path
    pre-close, verification in code, front+maximize, honest existed."""

    def test_xls_template_discipline(self):
        from agentic_rag_mcp.office_lanes.proxy import _XLS_WRITE_TEMPLATE as T
        assert "Workbooks.Add" in T and "SaveAs" in T
        assert "FullName" in T and "normcase" in T   # same-path pre-close
        assert "text_ok" in T                         # verify in code
        assert "ActiveWindow.Hwnd" in T                # Excel fronting
        assert "keybd_event" in T                      # the ALT-tap

    def test_ppt_template_discipline(self):
        from agentic_rag_mcp.office_lanes.proxy import _PPT_WRITE_TEMPLATE as T
        assert "Presentations.Add" in T and "Slides.Add(1, 2)" in T
        assert "PPTFrameClass" in T                    # HWND quirk bypass
        assert "text_ok" in T
        assert "FullName" in T and "normcase" in T

    def test_xls_template_has_no_formula_support(self):
        from agentic_rag_mcp.office_lanes.proxy import _XLS_WRITE_TEMPLATE as T
        assert "Formula" not in T   # .Value writes only — data, never code

    def test_xls_verify_uses_displayed_literal(self):
        # still-little-bit-slow (2026-11-13): Excel coerces '12345' to
        # 12345.0 — str(.Value) verification rejected every numeric write;
        # .Text returns the displayed literal, which is what 'type X' means
        from agentic_rag_mcp.office_lanes.proxy import _XLS_WRITE_TEMPLATE as T
        assert ".Text) != str(val)" in T
        assert ".Value) != str(val)" not in T

    def test_templates_init_com_apartment_before_dispatch(self):
        # slow-respone-come-back-again (2026-11-14): some OfficeMCP RunPython
        # workers execute scripts on a COM-uninitialized thread (-2147221008)
        # — every v2 template must CoInitialize before it Dispatches
        from agentic_rag_mcp.office_lanes.proxy import (
            _PPT_WRITE_TEMPLATE,
            _READ_TEMPLATE,
            _WRITE_TEMPLATE,
            _XLS_WRITE_TEMPLATE,
        )
        for T in (_WRITE_TEMPLATE, _READ_TEMPLATE, _XLS_WRITE_TEMPLATE,
                  _PPT_WRITE_TEMPLATE):
            assert "pythoncom.CoInitialize()" in T
            assert T.index("pythoncom.CoInitialize()") < T.index("win32com.client.Dispatch(")

    def test_write_templates_attach_to_running_app_first(self):
        # xls-saveas-method-failed (2026-11-14): a bare Dispatch can spawn a
        # second app instance that holds none of the user's open files —
        # every write template attaches to the RUNNING app first
        from agentic_rag_mcp.office_lanes.proxy import (
            _PPT_WRITE_TEMPLATE,
            _WRITE_TEMPLATE,
            _XLS_WRITE_TEMPLATE,
        )
        for T in (_WRITE_TEMPLATE, _XLS_WRITE_TEMPLATE, _PPT_WRITE_TEMPLATE):
            assert T.index("GetActiveObject(") < T.index("Dispatch(")

    def test_write_templates_pre_close_is_verified_and_honest(self):
        # xls-saveas-method-failed (2026-11-14): the office apps refuse
        # SaveAs onto an already-open file — the same-path pre-close must
        # record close failures (never a silent except:pass), verify the
        # file actually closed, and refuse with the situation named BEFORE
        # the SaveAs call instead of surfacing the raw COM error
        from agentic_rag_mcp.office_lanes.proxy import (
            _PPT_WRITE_TEMPLATE,
            _WRITE_TEMPLATE,
            _XLS_WRITE_TEMPLATE,
        )
        for T in (_WRITE_TEMPLATE, _XLS_WRITE_TEMPLATE, _PPT_WRITE_TEMPLATE):
            assert "except Exception as _e" in T      # close failures recorded
            assert "could not be" in T                # the honest refusal
            assert "blocked: the target file" in T
            assert T.index("blocked: the target file") < T.index(".SaveAs")
            assert "for _attempt in range(2)" in T    # the retry
            # the busy-app wrap: a modal/edit-mode app is named honestly,
            # never surfaced as the raw property error
            assert "refused" in T
            assert "automation" in T

    def test_xls_saveas_silences_the_overwrite_prompt(self):
        # xls-saveas-method-failed round 2 (2026-11-14): Excel's SaveAs onto
        # an existing path raises the "replace file?" dialog, which headless
        # COM cannot show — 0x800A03EC. DisplayAlerts must be off before
        # the SaveAs call and restored after; a failure raises the honest
        # recovered-twin envelope instead of the raw COM tuple.
        from agentic_rag_mcp.office_lanes.proxy import _XLS_WRITE_TEMPLATE as T
        assert T.index("xl.DisplayAlerts = False") < T.index("wb.SaveAs(")
        assert "finally:" in T
        assert T.index("xl.DisplayAlerts = True") > T.index("wb.SaveAs(")
        assert "recovered or temporary name" in T   # the honest wrap


def _word_print_template():
    assert hasattr(office_proxy, "_WORD_PRINT_TEMPLATE"), (
        "T042 must add the fixed _WORD_PRINT_TEMPLATE")
    return office_proxy._WORD_PRINT_TEMPLATE


def _word_print_source():
    return textwrap.dedent(_word_print_template())


def _if_guards(source, tree, node):
    parents = {child: parent for parent in ast.walk(tree)
               for child in ast.iter_child_nodes(parent)}
    guards = []
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.If):
            guards.append(ast.get_source_segment(source, node.test) or "")
    return guards


def _fake_http_proxy(monkeypatch, frame):
    """An OfficeProxy with only its HTTP/SSE boundary mocked; no COM runs."""
    proxy = OfficeProxy.__new__(OfficeProxy)
    proxy.base = "http://office.test"
    proxy.timeout_s = 180.0
    proxy._endpoint = "/messages"
    proxy._lock = threading.Lock()
    posts = []

    def ensure():
        proxy._endpoint = "/messages"

    def next_frame(*args, **kwargs):
        if isinstance(frame, BaseException):
            raise frame
        return frame

    def post(url, json, timeout):
        posts.append({"url": url, "json": json, "timeout": timeout})
        return Mock()

    monkeypatch.setattr(proxy, "_ensure", ensure)
    monkeypatch.setattr(proxy, "_next", next_frame)
    monkeypatch.setattr(office_proxy.httpx, "post", post)
    return proxy, posts


class TestWordPrintPreviewT036:
    def test_com_initializes_and_attaches_before_dispatch(self):
        source = _word_print_source()
        assert "pythoncom.CoInitialize()" in source
        assert source.index("pythoncom.CoInitialize()") < source.index(
            "GetActiveObject(")
        assert source.index("GetActiveObject(") < source.index("Dispatch(")

    def test_dispatch_requires_no_winword_process(self):
        # A running-but-unregistered Word must produce an honest failure, not
        # an empty second instance that hides the user's documents.
        source = _word_print_source()
        tree = ast.parse(source)
        dispatch = [n for n in ast.walk(tree)
                    if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "Dispatch"]
        assert len(dispatch) == 1
        assert "WINWORD" in source.upper()
        guards = _if_guards(source, tree, dispatch[0])
        assert any(
            any(marker in guard.upper()
                for marker in ("WINWORD", "RUNNING", "PROCESS"))
            and ("NOT" in guard.upper()
                 or "==0" in "".join(guard.split()))
            for guard in guards
        ), "Dispatch must be guarded by a no-WINWORD-process check"

    def test_document_preview_and_all_display_checks_are_verified(self):
        source = _word_print_source()
        assert "doc.PrintPreview()" in source       # Document, not Backstage
        assert "word.PrintPreview" in source       # independent read-back
        assert re.search(r"ActiveWindow\.View\.Type[^\n]*==\s*4", source)
        assert "ActiveWindow.Hwnd" in source
        assert "IsWindowVisible(hwnd)" in source
        assert "SetForegroundWindow(hwnd)" in source
        assert "GetForegroundWindow() == hwnd" in source
        assert "preview_ok" in source
        assert "visible" in source and "foreground" in source

    def test_blank_document_is_conditional_and_disclosed(self):
        source = _word_print_source()
        tree = ast.parse(source)
        adds = [n for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == "Add"
                and isinstance(n.func.value, ast.Attribute)
                and n.func.value.attr == "Documents"]
        assert len(adds) == 1
        guards = _if_guards(source, tree, adds[0])
        assert any("COUNT" in guard.upper()
                   and ("NOT" in guard.upper()
                        or "==0" in "".join(guard.split()))
                   for guard in guards)
        assert "blank_created" in source

    def test_existing_document_count_and_saved_flags_are_preserved(self):
        source = _word_print_source()
        for marker in ("before_count", "after_count", "before_saved",
                       "after_saved", "count_ok", "saved_ok",
                       "documents_preserved"):
            assert marker in source
        assert source.index("before_count") < source.index("doc.PrintPreview()")
        assert source.index("before_saved") < source.index("doc.PrintPreview()")
        assert source.index("doc.PrintPreview()") < source.index("after_count")
        assert source.index("doc.PrintPreview()") < source.index("after_saved")
        compact = "".join(source.split())
        assert "after_count==before_count+int(blank_created)" in compact
        assert "before_saved==after_saved[:before_count]" in compact
        assert ".Saved" in source                  # read-only snapshots
        assert ".Name" not in source and ".FullName" not in source
        assert "document_names" not in source

    def test_no_print_mutation_dialog_or_evidence_free_backstage(self):
        source = _word_print_source()
        tree = ast.parse(source)
        called = {n.func.attr for n in ast.walk(tree)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)}
        assert {"PrintOut", "Save", "SaveAs", "SaveAs2", "Close", "Quit",
                "Dialogs", "Show", "Display"}.isdisjoint(called)
        # This proxy has no UI-tree evidence. Only separately gated T043
        # orchestration may consider bounded ExecuteMso for explicit legacy
        # unsupported results; busy/modal/timeout must never reach Backstage.
        assert "ExecuteMso" not in called
        assert "PrintPreviewAndPrint" not in source
        for node in ast.walk(tree):
            targets = (node.targets if isinstance(node, ast.Assign) else
                       [node.target] if isinstance(node, (ast.AnnAssign,
                                                          ast.AugAssign)) else [])
            assert not any(isinstance(part, ast.Attribute)
                           and part.attr == "Saved"
                           for target in targets for part in ast.walk(target))

    def test_show_word_print_sync_api_uses_fixed_template(self, monkeypatch):
        assert hasattr(OfficeProxy, "show_word_print"), (
            "T042 must add OfficeProxy.show_word_print()")
        assert not inspect.iscoroutinefunction(OfficeProxy.show_word_print)
        assert list(inspect.signature(
            OfficeProxy.show_word_print).parameters) == ["self"]
        payload = {
            "preview_ok": True,
            "view_type": 4,
            "visible": True,
            "foreground": True,
            "blank_created": False,
            "document_count": 2,
            "count_ok": True,
            "saved_ok": True,
            "documents_preserved": True,
        }
        tool_text = json.dumps({"success": True,
                                "output": json.dumps(payload)})
        frame = {"result": {"content": [{"type": "text", "text": tool_text}]}}
        proxy, posts = _fake_http_proxy(monkeypatch, frame)

        out = proxy.show_word_print()

        assert out == {"status": "ok", **payload}
        assert len(posts) == 1
        request = posts[0]["json"]
        assert request["method"] == "tools/call"
        assert request["params"]["name"] == "RunPython"
        assert request["params"]["arguments"] == {
            "code": _word_print_template()}
        assert 0 < posts[0]["timeout"] < 180.0
        assert proxy.timeout_s == 180.0           # later callers keep defaults

    @pytest.mark.parametrize("reason", [
        "Word is busy and rejected the COM call",
        "Word has a modal dialog open",
        "legacy PrintPreview is explicitly unsupported",
    ])
    def test_busy_modal_and_unsupported_never_fall_back_to_backstage(
            self, monkeypatch, reason):
        proxy, posts = _fake_http_proxy(
            monkeypatch, {"error": {"message": reason}})

        out = proxy.show_word_print()

        assert out["status"] == "error"
        assert len(posts) == 1
        code = posts[0]["json"]["params"]["arguments"]["code"]
        assert "ExecuteMso" not in code
        assert "PrintPreviewAndPrint" not in code
        assert 0 < posts[0]["timeout"] < 180.0

    def test_timeout_is_bounded_and_not_retried(self, monkeypatch):
        proxy, posts = _fake_http_proxy(
            monkeypatch, ConnectionError("OfficeMCP response timeout"))

        try:
            out = proxy.show_word_print()
        except ConnectionError:
            pass
        else:
            assert isinstance(out, dict) and out.get("status") != "ok"

        assert len(posts) == 1
        assert 0 < posts[0]["timeout"] < 180.0
        assert proxy.timeout_s == 180.0

    def test_existing_call_still_uses_its_two_attempt_180s_defaults(
            self, monkeypatch):
        assert inspect.signature(
            OfficeProxy.__init__).parameters["timeout_s"].default == 180.0
        proxy, posts = _fake_http_proxy(
            monkeypatch, ConnectionError("OfficeMCP response timeout"))

        with pytest.raises(ConnectionError):
            proxy.call("RunPython", {})

        assert len(posts) == 2
        assert [post["timeout"] for post in posts] == [180.0, 180.0]
