"""Spec 028 — append-only audit log for the Hermes file-task lane (FR-012/013).

One JSONL entry per attempted operation, written at the tool's single verdict
point: executed entries are written post-completion with the outcome (so a
mid-task stop never erases the truth), blocked/error entries carry the
reason. The lane never rewrites or prunes existing entries.
"""

from __future__ import annotations

import fcntl
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from .loop_gate import record as _loop_gate_record

_LOCK = threading.Lock()
_DECISIONS = ("executed", "blocked", "error")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class HermesAudit:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write_attempt(self, *, decision: str, operation: str,
                      normalized_path: str | None, allowed_root: str,
                      reason: str | None = None, outcome: str | None = None,
                      duration_s: float | None = None,
                      timing: dict | None = None,
                      conversation_id: str | None = None) -> None:
        if decision not in _DECISIONS:
            raise ValueError(f"decision must be one of {_DECISIONS}, got {decision!r}")
        # after-the-task-was-done (2026-11-14): the single funnel every lane
        # audits through also classifies the conversation for the loop gate —
        # v2 fast-path ops make the skill loop refuse until real loop-lane
        # work runs in the conversation
        _loop_gate_record(operation, conversation_id)
        entry = {
            "ts": _now(),
            "decision": decision,
            "operation": operation,
            "normalized_path": normalized_path,
            "allowed_root": allowed_root,
        }
        # spec 036 (T030): skill-* rows carry the conversation; additive —
        # legacy entries without it stay valid, callers that omit it unchanged
        if conversation_id:
            entry["conversation_id"] = conversation_id
        if decision == "executed":
            entry["outcome"] = outcome
        else:
            entry["reason"] = reason
        # every-steps-hold-long-time (2026-11-09): optional turn benchmark —
        # absent on legacy entries and on attempts that never ran the agent
        if duration_s is not None:
            entry["duration_s"] = round(duration_s, 1)
        if timing:
            entry["timing"] = timing
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with _LOCK, open(self.path, "a", encoding="utf-8") as f:
            # cross-process appends stay whole lines under the flock
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                os.write(f.fileno(), line.encode("utf-8"))
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)