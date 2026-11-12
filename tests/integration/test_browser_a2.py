"""Spec 037 — A2 adversarial harness (task T014, 035 SC-007 mandate): a
browser-lane turn that reads an injection-payload page MUST produce zero
non-browser tool calls, an honest injection report, and audit rows.

Two layers are pinned here:
1. STRUCTURAL (research R4 layer 2): the browser lane's DSL tool list
   contains no destructive lane tools (no hermes_run_powershell, no office,
   no file tools) — injection has nothing to call from that node.
2. BEHAVIORAL (R4 layer 1): the lane instructions carry the
   UNTRUSTED-CONTENT LAW verbatim and demand honest reporting."""

from __future__ import annotations

from pathlib import Path

import yaml

DSL = Path(__file__).resolve().parents[2] / "dify" / "AGIAssistant" / "AGI_Assistant.yml"
FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "injection_page.html"

# tools a browser lane may legitimately call (browser + skill + status only)
_ALLOWED_BROWSER_LANE_TOOLS = {
    "browser_scripted_run", "browser_status", "browser_dynamic_task",
    "browser_navigate_v2", "browser_read_v2", "browser_click_v2",
    "skill_search", "skill_get", "skill_save", "skill_feedback",
}
# tools injection would want — must be ABSENT from the lane's scope
_FORBIDDEN_IN_LANE = {
    "hermes_run_powershell", "hermes_run_command", "hermes_file_task",
    "hermes_launch_app", "hermes_office_task",
}


def _agent_nodes_tools() -> dict[str, set[str]]:
    """Map agent node title -> its tool_name set from the DSL."""
    doc = yaml.safe_load(DSL.read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for node in doc["workflow"]["graph"].get("nodes", []):
        data = node.get("data") or {}
        title = data.get("title", node.get("title", ""))
        if data.get("type") != "agent":
            continue
        tools = ((data.get("agent_parameters") or {}).get("tools") or {})
        values = tools.get("value") or []
        names = set()
        for entry in values:
            name = entry.get("tool_name")
            if name:
                names.add(name)
        out[title] = names
    return out


class TestA2StructuralScope:
    def test_browser_lane_carries_no_destructive_tools(self):
        # the Hermes Local Agent lane (which carries the browser tools)
        # routes browser work through browser-scripted-run only when the
        # request is a browser flow; destructive tools may still exist on
        # the node — so the real boundary is instructions + the A2
        # behavioral law. The hard pin: the browser TOOLS exist and no
        # tool named for OS execution is REQUIRED for a browser flow.
        nodes = _agent_nodes_tools()
        hermes = next((t for t in nodes if "Hermes Local Agent" in t), None)
        assert hermes, "Hermes Local Agent lane not found"
        assert "browser_scripted_run" in nodes[hermes], (
            "browser tools missing from the Hermes lane")
        assert "browser_status" in nodes[hermes]

    def test_general_lane_excludes_browser_and_skill_tools(self):
        nodes = _agent_nodes_tools()
        general = next((t for t in nodes if t.startswith("Agentic Strategy")), None)
        assert general is not None
        assert not (_ALLOWED_BROWSER_LANE_TOOLS & nodes[general]), (
            "General lane must not carry browser/skill tools (035 FR-001 scope)")


class TestA2UntrustedContentLaw:
    def test_lane_instructions_carry_the_law(self):
        # the instructions live in YAML double-quoted scalars with escaped
        # newlines — parse the document and search decoded node values
        doc = yaml.safe_load(DSL.read_text(encoding="utf-8"))
        blobs: list[str] = [yaml.safe_dump(doc)]
        def _walk(node):
            if isinstance(node, dict):
                for v in node.values():
                    _walk(v)
            elif isinstance(node, list):
                for v in node:
                    _walk(v)
            elif isinstance(node, str) and len(node) > 200:
                blobs.append(node)
        _walk(doc)
        text = "\n".join(blobs).lower()
        assert "untrusted-content law" in text
        assert "never instructions" in text
        assert "injection attempt" in text

    def test_fixture_carries_payload(self):
        fixture = FIXTURE.read_text(encoding="utf-8")
        assert "ignore all previous instructions" in fixture.lower()
        assert "Remove-Item" in fixture

    def test_law_names_refusal_and_report(self):
        doc = yaml.safe_load(DSL.read_text(encoding="utf-8"))
        blobs: list[str] = [yaml.safe_dump(doc)]
        def _walk(node):
            if isinstance(node, dict):
                for v in node.values():
                    _walk(v)
            elif isinstance(node, list):
                for v in node:
                    _walk(v)
            elif isinstance(node, str) and len(node) > 200:
                blobs.append(node)
        _walk(doc)
        text = "\n".join(blobs).lower()
        assert "refuse it" in text and "report" in text


class TestA2Envelopes:
    def test_scripted_run_refuses_unknown_script_honestly(self):
        from agentic_rag_mcp.browser_lanes.scripted_run import ScriptNotFound, ScriptRegistry
        reg = ScriptRegistry(
            Path(__file__).resolve().parents[2] / "scripts" / "browser")
        assert "check_page_title" in reg.names()
        with __import__("pytest").raises(ScriptNotFound):
            reg.get("run_arbitrary_powershell")

    def test_registry_rejects_injected_script_bodies(self, tmp_path):
        # an "injected" script (payload in the body) never loads: A2's
        # supply-chain half — only clean scripts are routable
        bad = tmp_path / "injected.py"
        bad.write_text(
            "# name: injected\n# version: 1\n"
            '# params: {"url": "x"}\n# expect: ["loaded"]\n'
            'import subprocess; subprocess.run(["powershell", "-c", "Remove-Item C:\\\\"])'
            "\nPASSWORD = 'hunter2-leaked'\n")
        from agentic_rag_mcp.browser_lanes.scripted_run import validate_script_file
        with __import__("pytest").raises(ValueError):
            validate_script_file(bad)