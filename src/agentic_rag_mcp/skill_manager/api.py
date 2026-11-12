"""Spec 036 — the four MCP tool handlers: search/get/save/feedback
(contracts/README.md). Trust is pre-computed (reusable flag), outage is a
distinct honest envelope from a miss (research R6), every call audits
with duration/timing (FR-014)."""

from __future__ import annotations

import time

from ..hermes_audit import HermesAudit
from .executor import prepare_replay
from .intent import SkillIntent
from .store import SkillNotFound, SkillStore, reusable

_ESCALATION = ("escalate to the human admin: two consecutive failures on this "
               "skill — do NOT retry again and do NOT delete the skill")


def _unavailable(exc: Exception) -> dict:
    return {"status": "error",
            "reason": (f"error:skill-store-unavailable — the skill store is "
                       f"unreachable ({exc.__class__.__name__}); completing this "
                       f"task manually without the skill loop")}


class SkillManager:
    """Server-side shared skill store surface. Outage -> honest degradation
    (FR-013); the lane routes manually and says so."""

    def __init__(self, db_path, vectordb_path, audit: HermesAudit,
                 min_rate: float = 0.80, min_successes: int = 3,
                 embedder_factory=None):
        self.store = SkillStore(db_path)
        self.intent = SkillIntent(vectordb_path, embedder_factory)
        self.audit = audit
        self.min_rate, self.min_successes = min_rate, min_successes

    # -- helpers ---------------------------------------------------------

    def _timed(self, operation: str, conversation_id: str, fn,
               ok_outcome: str = ""):
        t0 = time.monotonic()
        try:
            out = fn()
        # outage or store error — honest envelope (FR-013): every failure
        # mode in this boundary (OSError, sqlite3.Error, lance errors)
        # degrades to the same unavailable envelope, so catching broadly
        # here is the designed behavior, not sloppiness
        except Exception as exc:  # noqa: BLE001
            self.audit.write_attempt(
                decision="error", operation=operation, normalized_path=None,
                allowed_root="", reason=f"skill-store-unavailable: {exc}",
                conversation_id=conversation_id,
                duration_s=time.monotonic() - t0)
            return _unavailable(exc)
        # no-reusable-skill-on-file-do-not-open-word (2026-11-12): audit the
        # TRUE decision — a blocked/error envelope must not read as executed,
        # and its reason must survive (the retry storm was invisible before).
        status = out.get("status") if isinstance(out, dict) else None
        decision = {"blocked": "blocked", "error": "error"}.get(status,
                                                               "executed")
        self.audit.write_attempt(
            decision=decision, operation=operation, normalized_path=None,
            allowed_root="", outcome=ok_outcome[:200],
            reason=(str(out.get("reason"))[:300]
                    if decision != "executed" else None),
            conversation_id=conversation_id,
            duration_s=time.monotonic() - t0)
        return out

    def _trust_row(self, name: str) -> dict | None:
        counts = self.store.counts(name)
        skill = self.store.get(name)
        if not skill:
            return None
        return {
            "name": name,
            "description": skill["description"],
            "success_rate": (round(counts[0] / (counts[0] + counts[1]), 3)
                             if counts and (counts[0] + counts[1]) else 0.0),
            "sample": counts[0] if counts else 0,
            "reusable": bool(counts and reusable(
                counts, self.min_rate, self.min_successes)),
        }

    # -- the four operations (contracts) ----------------------------------

    def search(self, intent: str, cid: str, limit: int = 5) -> dict:
        def _fn():
            names = self.intent.search(intent, limit=limit)
            rows = [r for r in (self._trust_row(n) for n in names) if r]
            if not rows:
                return {"found": False, "skills": []}
            return {"found": True, "skills": rows}

        return self._timed("skill-search", cid, _fn, ok_outcome=intent[:120])

    def get(self, name: str, cid: str, values: dict | None = None) -> dict:
        def _fn():
            skill = self.store.get(name)
            if not skill:
                return {"status": "error",
                        "reason": f"error:skill-not-found — no skill named {name!r}"}
            if values is not None:
                prepared = prepare_replay(skill["workflow"], values)
                if prepared["status"] != "ok":
                    return {"status": "ask-back", "reason": prepared["reason"]}
                skill = {**skill, "workflow": prepared["workflow"]}
            return {"status": "ok", "skill": skill}

        return self._timed("skill-get", cid, _fn, ok_outcome=name)

    def save(self, skill: dict, cid: str) -> dict:
        def _fn():
            try:
                name, version = self.store.save(skill)
            except ValueError as exc:
                return {"status": "blocked", "reason": str(exc)}
            if version > 1:
                # trust bootstrap (whole-process-is-slow, 2026-11-12): the
                # same-name save follows a successful manual solve of the
                # same intent — count it toward the >=3 reuse threshold
                self.store.record_repeat_solve(name)
            self.intent.upsert(name, self.store.get(name)["description"])
            return {"status": "ok", "name": name, "version": version}

        return self._timed("skill-save", cid, _fn, ok_outcome=skill.get("name", ""))

    def feedback(self, skill_name: str, outcome: str, cid: str,
                 error_context: str | None = None) -> dict:
        def _fn():
            if outcome not in ("success", "failure"):
                return {"status": "blocked",
                        "reason": "rejected: outcome must be success or failure"}
            if outcome == "failure" and not (error_context or "").strip():
                return {"status": "blocked",
                        "reason": "rejected: error_context is required on failure"}
            try:
                self.store.record_feedback(skill_name, outcome, error_context)
            except SkillNotFound:
                return {"status": "error",
                        "reason": f"error:skill-not-found — no skill named "
                                  f"{skill_name!r}; never record feedback for an "
                                  f"unknown skill"}
            streak = self.store.consecutive_failures(skill_name)
            out = {"status": "ok", "acknowledged": True}
            if streak >= 2:
                out["escalate"] = True
                out["reason"] = _ESCALATION
            return out

        return self._timed("skill-feedback", cid, _fn, ok_outcome=skill_name)
