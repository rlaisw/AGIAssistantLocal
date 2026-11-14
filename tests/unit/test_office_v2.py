"""Office v2 (slow-total-time-75-6-seconds, 2026-11-13): the single-hop
document primitives — name sanitization, payload parsing, templates."""

from __future__ import annotations

import json

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
