"""Spec 030 — Office conversation state.

In-memory, thread-safe, keyed by conversation id (data-model
§PendingDraft/§ActiveDocument): the active document a follow-up continues
on, and the pending draft a confirmation may send (the COM EntryID + the
shown content). The pending draft lives until resolved (confirmed → sent;
cancelled or replaced → dropped) and is NEVER deleted from Outlook.
State is conversation-scoped scratch: lost on sidecar restart — the honest
fallback is an ask-back, never an assumption.
"""

from __future__ import annotations

import threading


class OfficeState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._convs: dict[str, dict] = {}

    def _conv(self, conversation_id: str) -> dict:
        return self._convs.setdefault(conversation_id,
                                      {"active_document": None,
                                       "pending_draft": None,
                                       "interrupted": None})

    # ---- active document (FR-013) ------------------------------------
    def active_document(self, conversation_id: str) -> str | None:
        with self._lock:
            return self._conv(conversation_id)["active_document"]

    def set_active_document(self, conversation_id: str, windows_path: str) -> None:
        with self._lock:
            self._conv(conversation_id)["active_document"] = windows_path

    # ---- pending draft (FR-009) ---------------------------------------
    def pending_draft(self, conversation_id: str) -> dict | None:
        with self._lock:
            return self._conv(conversation_id)["pending_draft"]

    def set_pending_draft(self, conversation_id: str, draft: dict) -> None:
        """A new compose replaces any pending draft (it is never deleted
        from Outlook's Drafts folder — it only loses pending status)."""
        with self._lock:
            self._conv(conversation_id)["pending_draft"] = draft

    def drop_pending_draft(self, conversation_id: str) -> dict | None:
        """Resolve the pending draft (cancel path); returns it for honest
        reporting, or None when nothing was pending."""
        with self._lock:
            conv = self._conv(conversation_id)
            draft = conv["pending_draft"]
            conv["pending_draft"] = None
            return draft

    # ---- interrupted task (FR-005 resume) -----------------------------
    def interrupted(self, conversation_id: str) -> dict | None:
        """The record a 'continue' resumes: the original task plus the
        partial report of the interrupted attempt."""
        with self._lock:
            return self._conv(conversation_id)["interrupted"]

    def set_interrupted(self, conversation_id: str, record: dict) -> None:
        with self._lock:
            self._conv(conversation_id)["interrupted"] = record

    def clear_interrupted(self, conversation_id: str) -> None:
        with self._lock:
            self._conv(conversation_id)["interrupted"] = None

    def clear(self, conversation_id: str) -> None:
        with self._lock:
            self._convs.pop(conversation_id, None)
