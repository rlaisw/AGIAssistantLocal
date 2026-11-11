"""Spec 038 — conversation-scoped Tier-2 recommendation state (FR-004):
mirrors the spec-034 PowerShellState pattern (dict + lock, in-memory,
audit JSONL the durable record). One pending recommendation per
conversation; a new tier-1 run supersedes; a recommendation is never a
standing consent."""

from __future__ import annotations

import threading


class Tier2State:
    def __init__(self) -> None:
        self._pending: dict[str, dict] = {}
        self._lock = threading.Lock()

    def set_pending(self, record: dict) -> None:
        """Register a fresh tier-2 recommendation (from a tier1 'tier2'
        verdict). Replaces any pending record in that conversation."""
        with self._lock:
            self._pending[record["conversation_id"]] = dict(record)

    def pending(self, conversation_id: str) -> dict | None:
        with self._lock:
            rec = self._pending.get(conversation_id)
            return dict(rec) if rec else None

    def supersede(self, conversation_id: str) -> None:
        """A new tier-1 run in this conversation invalidates the old
        recommendation — a stale confirm must not execute (FR-004)."""
        with self._lock:
            self._pending.pop(conversation_id, None)

    def clear(self, conversation_id: str) -> None:
        with self._lock:
            self._pending.pop(conversation_id, None)