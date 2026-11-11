"""Spec 036 — replay executor suite (tasks T016/T018): substitution with
honest ask-back, per-step expect verification, near-miss bailout, gated-step
live re-confirmation (035 FR-020 — structural, A3 pin), replay scoping."""

from __future__ import annotations

from agentic_rag_mcp.skill_manager.executor import (
    GATED_TOOLS,
    SKILL_TOOLS,
    prepare_replay,
    verify_expect,
)

WF = [
    {"step": 1, "tool": "hermes_run_command", "service": "os-control",
     "params_template": {"task": "restart {{service_name}}"},
     "expect": "service restarted"},
    {"step": 2, "tool": "hermes_run_powershell", "service": "os-control",
     "params_template": {"draft": "Set-Service -Name {{service_name}} -StartupType Automatic"},
     "expect": "startup type set"},
]


class TestSubstitution:
    def test_fills_slots(self):
        out = prepare_replay(WF, {"service_name": "Spooler"})
        assert out["workflow"][0]["params"]["task"] == "restart Spooler"
        assert out["workflow"][1]["params"]["draft"] == (
            "Set-Service -Name Spooler -StartupType Automatic")

    def test_unfilled_slot_is_ask_back_never_guess(self):
        out = prepare_replay(WF, {})
        assert out["status"] == "ask-back"
        assert "service_name" in out["reason"]

    def test_empty_workflow_ask_back(self):
        out = prepare_replay([], {})
        assert out["status"] == "ask-back"


class TestExpectVerification:
    def test_match_passes(self):
        assert verify_expect({"status": "ok", "result": "service restarted now"},
                             "service restarted") is True

    def test_mismatch_bails_out(self):
        assert verify_expect({"status": "ok", "result": "unrelated"}, 
                              "service restarted") is False

    def test_error_result_never_passes(self):
        assert verify_expect({"status": "error"}, "anything") is False


class TestGatedReplayStructural:
    """035 FR-020 / A3: the skill surface cannot execute anything."""

    def test_skill_tools_never_execute(self):
        # the four skill tools are data-only; gated execution exists only in
        # the lane tools — this is the structural invariant
        assert SKILL_TOOLS == {"skill_search", "skill_get",
                                "skill_save", "skill_feedback"}
        assert "hermes_run_powershell" in GATED_TOOLS
        assert not (SKILL_TOOLS & GATED_TOOLS)

    def test_gated_step_marked_for_live_confirm(self):
        out = prepare_replay(WF, {"service_name": "Spooler"})
        assert out["workflow"][1]["gated"] is True   # pause: needs live confirm
        assert out["workflow"][0]["gated"] is False

    def test_prepared_replay_carries_no_execution(self):
        # prepare_replay returns DATA only — no callables, no runners
        out = prepare_replay(WF, {"service_name": "Spooler"})
        for step in out["workflow"]:
            assert set(step) <= {"step", "tool", "service", "params",
                                 "expect", "gated"}

class TestReplayWalk:
    """T031: the walk drives steps through the lane tools, pauses on gated
    steps, resumes after live confirmation, and cancels without failure."""

    @staticmethod
    def _wf():
        return [
            {"step": 1, "tool": "hermes_run_command", "service": "os-control",
             "params": {"task": "restart Spooler"}, "expect": "service restarted",
             "gated": False},
            {"step": 2, "tool": "hermes_run_powershell", "service": "os-control",
             "params": {"draft": "Set-Service -Name Spooler -StartupType Automatic"},
             "expect": "startup type set", "gated": True},
            {"step": 3, "tool": "hermes_run_command", "service": "os-control",
             "params": {"task": "check Spooler"}, "expect": "running",
             "gated": False},
        ]

    @staticmethod
    def _audit():
        import pathlib
        import tempfile

        from agentic_rag_mcp.hermes_audit import HermesAudit
        return HermesAudit(pathlib.Path(tempfile.mkdtemp()) / "audit.jsonl")

    def test_walk_pauses_at_gated_step(self):
        from agentic_rag_mcp.skill_manager.executor import ReplayWalk
        walk = ReplayWalk(self._audit(), "fix_print_spooler", "c1", self._wf())
        out = walk.next_action()
        assert out["status"] == "run-step" and out["step"] == 1
        out2 = walk.record_step_result({"status": "ok",
                                        "result": "the service restarted ok"})
        assert out2["status"] == "pending-confirmation"
        assert out2["tool"] == "hermes_run_powershell"
        # nothing executes past the gated step until advance_past_gated
        assert walk.cursor == 1

    def test_gated_result_never_recorded_directly(self):
        from agentic_rag_mcp.skill_manager.executor import ReplayWalk
        walk = ReplayWalk(self._audit(), "fix_print_spooler", "c1", self._wf())
        walk.next_action()
        walk.record_step_result({"status": "ok", "result": "service restarted"})
        # attempt to feed a gated step's "result" straight in: refused
        out = walk.record_step_result({"status": "ok",
                                        "result": "startup type set"})
        assert out["status"] == "aborted"

    def test_resume_after_confirmed_gated_step(self):
        from agentic_rag_mcp.skill_manager.executor import ReplayWalk
        walk = ReplayWalk(self._audit(), "fix_print_spooler", "c1", self._wf())
        walk.next_action()
        walk.record_step_result({"status": "ok", "result": "service restarted"})
        out = walk.advance_past_gated()
        assert out["status"] == "run-step" and out["step"] == 3
        out2 = walk.record_step_result({"status": "ok", "result": "Spooler is running"})
        assert out2["status"] == "done" and out2["completed_steps"] == 3

    def test_cancel_aborts_without_failure(self):
        from agentic_rag_mcp.skill_manager.executor import ReplayWalk
        walk = ReplayWalk(self._audit(), "fix_print_spooler", "c1", self._wf())
        walk.next_action()
        walk.record_step_result({"status": "ok", "result": "service restarted"})
        out = walk.cancel()
        assert out["status"] == "aborted" and "no failure feedback" in out["reason"]

    def test_expect_mismatch_aborts_honestly(self):
        from agentic_rag_mcp.skill_manager.executor import ReplayWalk
        walk = ReplayWalk(self._audit(), "fix_print_spooler", "c1", self._wf())
        walk.next_action()
        out = walk.record_step_result({"status": "ok", "result": "unrelated"})
        assert out["status"] == "aborted"
        assert "step expected" in out["reason"] and "stops honestly" in out["reason"]

    def test_start_and_abort_write_audit_rows(self):
        from agentic_rag_mcp.skill_manager.executor import ReplayWalk
        audit = self._audit()
        walk = ReplayWalk(audit, "fix_print_spooler", "c1", self._wf())
        walk.cancel()
        with open(audit.path) as f:
            lines = f.read().strip().splitlines()
        ops = [__import__("json").loads(l)["operation"] for l in lines]
        assert "skill-replay-start" in ops and "skill-replay-abort" in ops
        # T030: rows carry the conversation
        assert all("conversation_id" not in l or '"c1"' in l
                   for l in lines)

    def test_walk_records_carry_conversation_id(self):
        import json as _json

        from agentic_rag_mcp.skill_manager.executor import ReplayWalk
        audit = self._audit()
        walk = ReplayWalk(audit, "fix_print_spooler", "c42", self._wf())
        walk.cancel()
        with open(audit.path) as f:
            rows = [_json.loads(l) for l in f.read().splitlines()]
        assert all(r.get("conversation_id") == "c42" for r in rows)
