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