"""Spec 038 — the tier-2 lane matrix suite (task T011): no-recommendation
blocked, confirm executes ONLY the stored repair, never-list refused at
draft AND execution with both preconditions, supersession, audit rows."""

from __future__ import annotations

from agentic_rag_mcp.hermes_audit import HermesAudit
from agentic_rag_mcp.task_gateway.client import TaskGatewayClient
from agentic_rag_mcp.task_gateway.lane import TaskLane, get_tier2_state


class _FakeClient(TaskGatewayClient):
    def __init__(self, tier2_response=None):
        self.tier2_response = tier2_response or {"status": "ok",
                                                 "result": "ok",
                                                 "detail": "repaired"}

    def tier2(self, issue_type, cid):
        return dict(self.tier2_response)


def _lane(tmp_path, client=None):
    audit = HermesAudit(tmp_path / "audit.jsonl")
    return TaskLane(client or _FakeClient(), audit), audit


def _seed(cid="c1", repair_name="system_file_check",
          repair_text="sfc /scannow"):
    get_tier2_state().clear(cid)
    get_tier2_state().set_pending({
        "conversation_id": cid, "issue_type": "general",
        "repair_name": repair_name, "repair_text": repair_text})


class TestDraftPhase:
    def test_no_recommendation_blocked(self, tmp_path):
        lane, _audit = _lane(tmp_path)
        get_tier2_state().clear("c-none")
        out = lane.tier2("general", "c-none", confirm=False)
        assert out["status"] == "blocked"
        assert "no fresh tier-2 recommendation" in out["reason"]

    def test_draft_returns_pending_confirmation_named_repair(self, tmp_path):
        lane, _audit = _lane(tmp_path)
        _seed()
        out = lane.tier2("general", "c1", confirm=False)
        assert out["status"] == "pending-confirmation"
        assert out["repair_name"] == "system_file_check"
        assert out["repair_text"] == "sfc /scannow"
        assert "VERBATIM" in out["instruction"]

    def test_neverlist_refused_at_draft_with_both_preconditions(self, tmp_path):
        lane, _audit = _lane(tmp_path)
        _seed(repair_name="format_disk",
               repair_text="Format-Volume -DriveLetter D")
        out = lane.tier2("general", "c1", confirm=False)
        assert out["status"] == "blocked"
        assert "system integrity" in out["reason"]
        # the pending poisoned repair was cleared — a later confirm cannot run it
        assert get_tier2_state().pending("c1") is None

    def test_draft_writes_audit_row(self, tmp_path):
        lane, audit = _lane(tmp_path)
        _seed()
        lane.tier2("general", "c1", confirm=False)
        with open(audit.path) as f:
            rows = [__import__("json").loads(l)
                    for l in f.read().splitlines()]
        assert any(r["operation"] == "task-tier2-draft"
                   and r.get("conversation_id") == "c1" for r in rows)


class TestConfirmPhase:
    def test_confirm_executes_stored_repair(self, tmp_path):
        lane, _audit = _lane(tmp_path)
        _seed()
        out = lane.tier2("general", "c1", confirm=True)
        assert out["status"] == "ok"
        assert out["repair_name"] == "system_file_check"
        # consumed: a second confirm is blocked
        out2 = lane.tier2("general", "c1", confirm=True)
        assert out2["status"] == "blocked"

    def test_confirm_without_recommendation_blocked(self, tmp_path):
        lane, _audit = _lane(tmp_path)
        get_tier2_state().clear("c-fresh")
        assert lane.tier2("general", "c-fresh", confirm=True)["status"] == "blocked"

    def test_neverlist_refused_at_execution_too(self, tmp_path):
        # defense-in-depth: the confirm phase re-scans — a never-listed
        # record that lands BETWEEN draft and confirm is refused there
        lane, _audit = _lane(tmp_path)
        _seed(repair_text="sfc /scannow")
        lane.tier2("general", "c1", confirm=False)  # draft passes (clean)
        # the pending record is replaced with a poisoned one before confirm
        _seed(repair_text="diskpart /s clean-all.txt")
        out = lane.tier2("general", "c1", confirm=True)
        assert out["status"] == "blocked"
        assert "system integrity" in out["reason"]
        assert get_tier2_state().pending("c1") is None

    def test_neverlist_refusal_audited_and_state_cleared(self, tmp_path):
        lane, audit = _lane(tmp_path)
        _seed(repair_text="format c:")
        lane.tier2("general", "c1", confirm=True)
        with open(audit.path) as f:
            rows = [__import__("json").loads(l)
                    for l in f.read().splitlines()]
        assert any(r["operation"] == "task-tier2-refused" for r in rows)
        assert get_tier2_state().pending("c1") is None


class TestSupersession:
    def test_new_tier1_supersedes_old_recommendation(self, tmp_path):
        lane, _audit = _lane(tmp_path)
        _seed(repair_name="old_repair")
        get_tier2_state().supersede("c1")
        assert get_tier2_state().pending("c1") is None
        out = lane.tier2("general", "c1", confirm=True)
        assert out["status"] == "blocked"  # stale confirm cannot execute


class TestJobsLane:
    def test_install_returns_handle(self, tmp_path):
        lane, _audit = _lane(tmp_path)

        class _InstallClient(_FakeClient):
            def install(self, version, channel, cid):
                return {"status": "ok", "job_id": "j1", "status2": "queued"}

        lane.client = _InstallClient()
        out = lane.install("365", "Current", cid="c1")
        assert out["job_id"] == "j1"

    def test_job_status_polls(self, tmp_path):
        lane, _audit = _lane(tmp_path)

        class _JobClient(_FakeClient):
            def job_status(self, job_id, cid):
                return {"status": "ok", "job": {"job_id": job_id,
                                                "status": "running"}}

        lane.client = _JobClient()
        out = lane.job_status("j1", cid="c1")
        assert out["job"]["status"] == "running"

    def test_job_audit_rows(self, tmp_path):
        lane, audit = _lane(tmp_path)

        class _JobClient(_FakeClient):
            def job_status(self, job_id, cid):
                return {"status": "ok", "job": {"job_id": job_id,
                                                "status": "completed"}}

        lane.client = _JobClient()
        lane.job_status("j9", cid="c1")
        with open(audit.path) as f:
            rows = [__import__("json").loads(l)
                    for l in f.read().splitlines()]
        assert any(r["operation"] == "task-job-status"
                   and r.get("conversation_id") == "c1" for r in rows)