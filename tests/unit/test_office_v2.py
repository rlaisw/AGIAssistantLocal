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

    def test_write_template_never_closes_after_save(self):
        # the post-save Close (the screen-empty bug) must NOT return
        assert "doc.Close()\noutput" not in _WRITE_TEMPLATE

    def test_data_parameterization(self):
        # the literal text/name ride the `data` argument — the code is OURS,
        # never agent-composed (no injection surface)
        assert "json.loads(data)" in _WRITE_TEMPLATE
        assert "d['text']" in _WRITE_TEMPLATE
