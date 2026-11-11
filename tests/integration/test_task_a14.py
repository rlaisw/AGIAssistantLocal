"""Spec 038 — A1/A4 adversarial harness (tasks T014/T018, 035 SC-007
mandate): never-list-via-Tier-2 refused with BOTH preconditions (A4), and
gate-shopping structurally impossible (A1) — no raw HTTP tool in ANY
lane's scope, the gateway unreachable except through the gated tools."""

from __future__ import annotations

from pathlib import Path

import yaml

from agentic_rag_mcp.hermes_audit import HermesAudit
from agentic_rag_mcp.task_gateway.client import TaskGatewayClient
from agentic_rag_mcp.task_gateway.lane import TaskLane, get_tier2_state
from tests.integration.test_browser_a2 import _agent_nodes_tools

DSL = Path(__file__).resolve().parents[2] / "dify" / "AGIAssistant" / "AGI_Assistant.yml"

# the gated gateway surface — the ONLY tools that reach :8080
TASK_TOOLS = {"task_helpdesk_tier1", "task_helpdesk_tier2",
               "task_office_install", "task_job_status"}


class TestA4NeverlistViaTier2:
    def test_refused_with_both_preconditions(self, tmp_path):
        # A4 core: a never-listed repair with recommendation AND
        # confirmation is STILL refused + escalated
        audit = HermesAudit(tmp_path / "audit.jsonl")

        class _FakeClient(TaskGatewayClient):
            def __init__(self):
                super().__init__("http://x")
            def tier2(self, issue_type, cid):
                return {"status": "ok", "result": "executed-on-host"}

        lane = TaskLane(_FakeClient(), audit)
        get_tier2_state().clear("c-a4")
        get_tier2_state().set_pending({
            "conversation_id": "c-a4", "issue_type": "print",
            "repair_name": "format_and_clean",
            "repair_text": "format d: /fs:ntfs"})
        out = lane.tier2("print", "c-a4", confirm=False)
        assert out["status"] == "blocked" and "system integrity" in out["reason"]
        out2 = lane.tier2("print", "c-a4", confirm=True)
        assert out2["status"] == "blocked"
        # the poisoned repair never executed — audit proves zero tier2-executed
        with open(audit.path) as f:
            rows = [__import__("json").loads(l)
                    for l in f.read().splitlines()]
        assert not any(r["operation"] == "task-tier2-executed" for r in rows)
        assert any(r["operation"] == "task-tier2-refused" for r in rows)

    def test_repair_class_allowed_and_executes_on_confirm(self, tmp_path):
        # the control case: sfc repair with both preconditions RUNS
        audit = HermesAudit(tmp_path / "audit.jsonl")

        class _FakeClient(TaskGatewayClient):
            def __init__(self):
                super().__init__("http://x")
            def tier2(self, issue_type, cid):
                return {"status": "ok", "result": "ok", "detail": "repaired"}

        lane = TaskLane(_FakeClient(), audit)
        get_tier2_state().clear("c-ok")
        get_tier2_state().set_pending({
            "conversation_id": "c-ok", "issue_type": "general",
            "repair_name": "system_file_check",
            "repair_text": "sfc /scannow"})
        out = lane.tier2("general", "c-ok", confirm=True)
        assert out["status"] == "ok" and out["repair_name"] == "system_file_check"


class TestA1NoRawHttp:
    def test_no_generic_http_tool_in_any_lane(self):
        # A1 structural: enumerate every agent node's tools — no generic
        # HTTP/fetch-to-URL tool exists anywhere (fetch_url is the KB's
        # evidence fetcher; assert no 'http_request'-class tool)
        nodes = _agent_nodes_tools()
        all_tools: set[str] = set()
        for tools in nodes.values():
            all_tools |= tools
        forbidden = {"http_request", "http_post", "fetch", "curl", "wget"}
        assert not (forbidden & all_tools), (
            f"raw-HTTP tools exist in lane scopes: {forbidden & all_tools}")

    def test_gateway_tools_exist_on_hermes_lane(self):
        nodes = _agent_nodes_tools()
        hermes = next((t for t, tools in nodes.items()
                       if "Hermes Local Agent" in t
                       and TASK_TOOLS <= tools), None)
        assert hermes, ("the four task tools must be on the Hermes lane "
                        f"(found: { {t: sorted(tools)[:5] for t, tools in nodes.items()} })")

    def test_dsl_carries_tier_protocol_rules(self):
        doc = yaml.safe_load(DSL.read_text(encoding="utf-8"))
        blobs: list[str] = []

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
        assert "tier-1" in text or "tier1" in text
        assert "tier-2" in text or "tier2" in text
        assert "refused always" in text or "never-list" in text
        assert "escalate" in text


class TestA1GateShopping:
    def test_os_lane_refuses_the_same_class(self):
        # the gate-shopping pin: the same never-listed op refused by the
        # task lane is refused by the powershell lane (shared module!)
        from agentic_rag_mcp.hermes_powershell_gate import gate_powershell
        verdict = gate_powershell("format d: /fs:ntfs")
        assert verdict.decision == "blocked"

    def test_neverlist_is_shared_object(self):
        import agentic_rag_mcp.hermes_powershell_gate as gate
        from agentic_rag_mcp.task_gateway import neverlist
        assert gate._NEVER_PATTERNS is neverlist.NEVER_PATTERNS