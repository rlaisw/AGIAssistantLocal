"""Spec 036 — feedback + escalation suite (task T014): append-only rows,
error_context on failure, escalation after two consecutive failures,
and the no-delete API surface."""

from __future__ import annotations

import pytest

from agentic_rag_mcp.skill_manager.api import SkillManager

SKILL = {
    "name": "fix_print_spooler",
    "description": "Restarts print spooler. Use for printing issues.",
    "tier": 1,
    "workflow": [{"step": 1, "tool": "hermes_run_command", "service": "os-control",
                  "params_template": {"task": "restart {{service_name}}"},
                  "expect": "service restarted"}],
}


@pytest.fixture()
def mgr(tmp_path):
    from agentic_rag_mcp.hermes_audit import HermesAudit
    m = SkillManager(tmp_path / "skills.db", tmp_path / "vdb",
                     HermesAudit(tmp_path / "audit.jsonl"))
    m.store.save(dict(SKILL))
    return m


class TestFeedback:
    def test_acknowledged_and_appended(self, mgr):
        out = mgr.feedback("fix_print_spooler", "success", cid="c1")
        assert out == {"status": "ok", "acknowledged": True}

    def test_error_context_required_on_failure(self, mgr):
        out = mgr.feedback("fix_print_spooler", "failure", cid="c1")
        assert out["status"] == "blocked"
        assert "error_context" in out["reason"]
        out2 = mgr.feedback("fix_print_spooler", "failure",
                             error_context="service missing", cid="c1")
        assert out2["status"] == "ok"

    def test_missing_skill_explicit(self, mgr):
        out = mgr.feedback("ghost", "success", cid="c1")
        assert out["status"] == "error"
        assert "skill-not-found" in out["reason"]


class TestEscalation:
    def test_two_consecutive_failures_escalate_and_keep_skill(self, mgr):
        mgr.feedback("fix_print_spooler", "failure",
                     error_context="first failure", cid="c1")
        out = mgr.feedback("fix_print_spooler", "failure",
                           error_context="retry also failed", cid="c2")
        assert out["status"] == "ok"
        assert out.get("escalate") is True
        # the skill survives — never deleted
        assert mgr.store.get("fix_print_spooler")["failure_count"] == 2

    def test_success_between_failures_resets_the_streak(self, mgr):
        mgr.feedback("fix_print_spooler", "failure", error_context="f1", cid="c1")
        mgr.feedback("fix_print_spooler", "success", cid="c2")
        out = mgr.feedback("fix_print_spooler", "failure",
                            error_context="f2", cid="c3")
        assert out.get("escalate") is not True  # streak broken by the success

    def test_no_delete_in_api(self):
        for forbidden in ("delete", "remove", "skill_delete"):
            assert not hasattr(SkillManager, forbidden)

class TestSaveAuditHonesty:
    """no-reusable-skill-on-file-do-not-open-word (2026-11-12): a rejected
    save must audit as BLOCKED with its reason — never as 'executed'."""

    def test_rejected_save_audits_blocked_with_reason(self, mgr, tmp_path):
        import json as _json
        bad = {"name": "Bad Name", "description": "d", "tier": 1,
               "workflow": []}
        out = mgr.save(bad, cid="c-audit")
        assert out["status"] == "blocked"
        with open(mgr.audit.path) as f:
            rows = [_json.loads(l) for l in f.read().splitlines()]
        save_rows = [r for r in rows if r["operation"] == "skill-save"]
        assert save_rows and save_rows[-1]["decision"] == "blocked"
        assert "name" in (save_rows[-1].get("reason") or "")

    def test_successful_save_audits_executed(self, mgr):
        import json as _json
        out = mgr.save(dict(SKILL), cid="c-ok")
        assert out["status"] == "ok"
        with open(mgr.audit.path) as f:
            rows = [_json.loads(l) for l in f.read().splitlines()]
        save_rows = [r for r in rows if r["operation"] == "skill-save"]
        assert save_rows[-1]["decision"] == "executed"
