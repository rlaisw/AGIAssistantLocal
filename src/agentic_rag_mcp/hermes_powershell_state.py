"""Spec 034 — conversation-scoped pending command drafts (data-model.md).

Mirrors the office lane's pending-email pattern, shrunk to the minimum: one
pending draft per conversation; a new draft replaces the old; state is
in-memory and ephemeral by design — the audit JSONL is the durable record
of every draft ever registered.
"""

from __future__ import annotations

import threading


class PowerShellState:
    def __init__(self) -> None:
        self._pending: dict[str, str] = {}
        self._lock = threading.Lock()

    def set_pending(self, conversation_id: str, command: str) -> None:
        with self._lock:
            self._pending[conversation_id] = command

    def pending(self, conversation_id: str) -> str | None:
        with self._lock:
            return self._pending.get(conversation_id)

    def clear(self, conversation_id: str) -> None:
        with self._lock:
            self._pending.pop(conversation_id, None)


_state = PowerShellState()


def get_powershell_state() -> PowerShellState:
    return _state
