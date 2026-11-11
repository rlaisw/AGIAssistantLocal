"""Spec 038 — the gated task-gateway LANE: the four MCP tool handlers with
the tier protocol, confirmation semantics, never-list binding, job
discipline, and audit on every attempt (contracts/README.md)."""

from __future__ import annotations

import time

from ..hermes_audit import HermesAudit
from .client import TaskGatewayClient
from .neverlist import scan
from .tier2_state import Tier2State

_state = Tier2State()


def get_tier2_state() -> Tier2State:
    return _state


def _blocked(audit: HermesAudit, operation: str, reason: str, cid: str) -> dict:
    audit.write_attempt(decision="blocked", operation=operation,
                        normalized_path=None, allowed_root="",
                        reason=reason, conversation_id=cid)
    return {"status": "blocked", "reason": reason}


class TaskLane:
    def __init__(self, client: TaskGatewayClient, audit: HermesAudit):
        self.client = client
        self.audit = audit
        self._state = _state

    def _timed(self, operation: str, cid: str, fn) -> dict:
        t0 = time.monotonic()
        try:
            out = fn()
        except Exception as exc:  # noqa: BLE001 — every outage mode degrades to the same envelope (036 discipline)
            self.audit.write_attempt(
                decision="error", operation=operation, normalized_path=None,
                allowed_root="",
                reason=f"task-gateway failure: {exc.__class__.__name__}: {exc}",
                conversation_id=cid,
                duration_s=time.monotonic() - t0)
            return {"status": "error",
                    "reason": f"error:task-gateway-unavailable — {exc}"}
        dur = time.monotonic() - t0
        self.audit.write_attempt(
            decision="executed", operation=operation, normalized_path=None,
            allowed_root="", outcome=str(out)[:200],
            conversation_id=cid, duration_s=dur)
        return out

    # -- US1: tier-1 first (FR-001) ---------------------------------------

    def tier1(self, issue_type: str, issue_text: str, cid: str) -> dict:
        def _fn():
            out = self.client.tier1(issue_type, issue_text, cid=cid)
            if out.get("status") != "ok":
                return out
            if out.get("recommendation") == "tier2":
                # register pending recommendation (FR-004: fresh, scoped)
                self._state.set_pending({
                    "conversation_id": cid, "issue_type": issue_type,
                    "repair_name": out.get("repair_name", "unknown"),
                    "repair_text": out.get("repair_text", ""),
                })
                return {"status": "ok", **out,
                        "pending_repair": out.get("repair_name")}
            return {"status": "ok", **out}

        # a new tier-1 run supersedes any prior recommendation in this
        # conversation (FR-004) — registered AFTER the call returns its own
        # verdict so the new recommendation replaces cleanly in set_pending
        return self._timed("task-tier1", cid, _fn)

    # -- US2: tier-2 two-phase (FR-002/003) ---------------------------------

    def tier2(self, issue_type: str, cid: str, confirm: bool = False) -> dict:
        rec = self._state.pending(cid)
        if not confirm:
            if not rec:
                reason = ("Blocked: no fresh tier-2 recommendation in this "
                          "conversation — run task_helpdesk_tier1 first and "
                          "relay its verdict; a recommendation never stands "
                          "across conversations (FR-004).")
                return _blocked(self.audit, "task-tier2-draft", reason, cid)
            # never-list at DRAFT (defense-in-depth, 034 discipline)
            hit = scan(rec.get("repair_text", ""))
            if hit:
                self._state.clear(cid)
                reason = (hit + " Escalate to the human admin — this repair "
                          "is refused even with the tier-2 recommendation.")
                return _blocked(self.audit, "task-tier2-refused", reason, cid)
            return self._timed(
                "task-tier2-draft", cid,
                lambda: {"status": "pending-confirmation",
                         "repair_name": rec["repair_name"],
                         "repair_text": rec["repair_text"],
                         "instruction": ("Show this repair VERBATIM and ask "
                                        "the user to confirm; only a plain "
                                        "affirmative for this exact repair "
                                        "executes it (confirm=true).")})
        # confirm phase: ONLY the stored repair, both preconditions, re-scan
        if not rec:
            reason = ("Blocked: no pending recommendation to confirm — run "
                      "task_helpdesk_tier1 and relay its verdict first.")
            return _blocked(self.audit, "task-tier2-refused", reason, cid)
        hit = scan(rec.get("repair_text", ""))
        if hit:
            self._state.clear(cid)
            reason = (hit + " Escalate to the human admin.")
            return _blocked(self.audit, "task-tier2-refused", reason, cid)

        def _fn():
            out = self.client.tier2(issue_type, cid=cid)
            if out.get("status") == "ok":
                self._state.clear(cid)
                out["repair_name"] = rec["repair_name"]
            return out

        return self._timed("task-tier2-executed", cid, _fn)

    # -- US3: install job + poll (FR-005/006) -------------------------------

    def install(self, version: str, channel: str, cid: str) -> dict:
        return self._timed(
            "task-office-install", cid,
            lambda: self.client.install(version, channel, cid=cid))

    def job_status(self, job_id: str, cid: str) -> dict:
        return self._timed(
            "task-job-status", cid,
            lambda: self.client.job_status(job_id, cid=cid))