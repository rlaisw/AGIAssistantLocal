"""after-the-task-was-done (2026-11-14): the v2 fast-path exemption is
structural — the skill loop refuses while the conversation's last
operational op was one of the seven exempt v2 tools, and any loop-lane
op restores it."""

import pytest

from agentic_rag_mcp.hermes_audit import HermesAudit
from agentic_rag_mcp.loop_gate import EXEMPT_OPS, exempt_active, record
from agentic_rag_mcp.skill_manager.api import SkillManager

CID = "conv-loop-gate-test"


SKILL = {
    "name": "open_word_and_type",
    "description": "open Word and type text",
    "tier": 1,
    "workflow": [{"step": 1, "tool": "hermes_office_task", "service": "os-control",
                  "params_template": {"task": "open Word and type {{text}}"},
                  "expect": "document on screen"}],
}


@pytest.fixture()
def mgr(tmp_path):
    m = SkillManager(tmp_path / "skills.db", tmp_path / "vdb",
                     HermesAudit(tmp_path / "audit.jsonl"))
    m.store.save(dict(SKILL))
    return m


@pytest.fixture(autouse=True)
def clean_gate():
    from agentic_rag_mcp import loop_gate
    loop_gate._last_class.clear()
    yield
    loop_gate._last_class.clear()


class TestGateClassification:

    def test_exempt_ops_mark_the_conversation(self):
        for op in EXEMPT_OPS:
            record(op, CID)
            assert exempt_active(CID)

    def test_loop_ops_restore_the_loop(self):
        record("browser-read-v2", CID)
        assert exempt_active(CID)
        for op in ("office-task", "launch-app", "run-command",
                   "browser-dynamic", "browser-scripted-run", "create-dir"):
            record(op, CID)
            assert not exempt_active(CID)

    def test_neutral_ops_change_nothing(self):
        record("office-task", CID)
        for op in ("skill-search", "skill-save", "skill-get",
                   "skill-feedback", "browser-status", "ask-back",
                   "unsupported", "cancel-turn"):
            record(op, CID)
        assert not exempt_active(CID)  # still the loop class

    def test_no_conversation_no_classification(self):
        record("browser-read-v2", None)
        assert not exempt_active(None)
        assert not exempt_active("other-conv")


class TestAuditFunnelIntegration:

    def test_write_attempt_classifies(self, tmp_path):
        audit = HermesAudit(tmp_path / "audit.jsonl")
        audit.write_attempt(decision="executed", operation="browser-read-v2",
                            normalized_path=None, allowed_root="",
                            outcome="read ok", conversation_id=CID)
        assert exempt_active(CID)
        audit.write_attempt(decision="executed", operation="office-task",
                            normalized_path=None, allowed_root="",
                            outcome="done", conversation_id=CID)
        assert not exempt_active(CID)


class TestLoopToolsRefuse:

    def test_search_refuses_during_exempt_turn(self, mgr):
        record("browser-read-v2", CID)
        out = mgr.search("open a browser page and read it", CID)
        assert out["status"] == "blocked"
        assert out["found"] is False
        assert "loop-exempt turn" in out["reason"]

    def test_save_refuses_during_exempt_turn(self, mgr):
        record("doc-write-v2", CID)
        out = mgr.save(dict(SKILL, name="new_loop_skill"), CID)
        assert out["status"] == "blocked"
        assert "loop-exempt turn" in out["reason"]
        assert not mgr.store.get("new_loop_skill")  # nothing written

    def test_refusal_is_audited(self, mgr, tmp_path):
        record("xls-write-v2", CID)
        mgr.search("anything", CID)
        rows = [l for l in (tmp_path / "audit.jsonl").read_text().splitlines()]
        assert any('"operation": "skill-search"' in r and '"decision": "blocked"' in r
                   for r in rows)

    def test_loop_turns_keep_the_full_loop(self, mgr):
        record("office-task", CID)
        out = mgr.search("open word and type", CID)
        assert out.get("status") != "blocked"     # the search really ran
        assert "found" in out                     # the normal search shape
        out = mgr.save(dict(SKILL), CID)
        assert out["status"] == "ok"              # the save really ran (v2 update)
