"""Unit: Office conversation state (spec 030, data-model §PendingDraft/§ActiveDocument).

Failing-first: written before office_state exists. In-memory, conversation-
keyed: the active document a follow-up continues on, and the pending draft a
confirmation may send (COM EntryID + shown content) — lives until resolved,
never deleted.
"""

from __future__ import annotations

from agentic_rag_mcp.office_state import OfficeState


def test_active_document_roundtrip():
    s = OfficeState()
    assert s.active_document("c1") is None
    s.set_active_document("c1", "C:\\OfficeMCP\\book1.xlsx")
    assert s.active_document("c1") == "C:\\OfficeMCP\\book1.xlsx"


def test_active_document_switch():
    s = OfficeState()
    s.set_active_document("c1", "C:\\OfficeMCP\\a.xlsx")
    s.set_active_document("c1", "C:\\OfficeMCP\\b.xlsx")
    assert s.active_document("c1") == "C:\\OfficeMCP\\b.xlsx"


def test_conversations_isolated():
    s = OfficeState()
    s.set_active_document("c1", "C:\\OfficeMCP\\mine.xlsx")
    assert s.active_document("c2") is None


def test_pending_draft_lifecycle():
    s = OfficeState()
    draft = {"entry_id": "EID-1", "recipients": "a@b.com",
             "subject": "test", "body": "hi"}
    s.set_pending_draft("c1", draft)
    assert s.pending_draft("c1") == draft
    assert s.pending_draft("c2") is None          # isolated
    dropped = s.drop_pending_draft("c1")
    assert dropped == draft                       # returned for honest reporting
    assert s.pending_draft("c1") is None          # lives until resolved, then gone
    assert s.drop_pending_draft("c1") is None     # second cancel is a no-op


def test_new_compose_replaces_pending():
    s = OfficeState()
    s.set_pending_draft("c1", {"entry_id": "EID-1", "recipients": "a@b.com",
                               "subject": "one", "body": "x"})
    s.set_pending_draft("c1", {"entry_id": "EID-2", "recipients": "c@d.com",
                               "subject": "two", "body": "y"})
    assert s.pending_draft("c1")["entry_id"] == "EID-2"


def test_restart_loss_semantics():
    """Documented assumption: state is in-memory — a new instance is empty,
    which the tool treats as an honest ask-back, never an assumption."""
    s1 = OfficeState()
    s1.set_active_document("c1", "C:\\OfficeMCP\\book.xlsx")
    s2 = OfficeState()
    assert s2.active_document("c1") is None
    assert s2.pending_draft("c1") is None


def test_interrupted_task_lifecycle():
    s = OfficeState()
    assert s.interrupted("c1") is None
    s.set_interrupted("c1", {"original_task": "open Excel ...",
                             "partial_report": "STEP 1 OK ... TASK: PARTIAL"})
    assert s.interrupted("c1")["original_task"] == "open Excel ..."
    s.clear_interrupted("c1")
    assert s.interrupted("c1") is None


def test_interrupted_isolated_and_replaced():
    s = OfficeState()
    s.set_interrupted("c1", {"original_task": "a", "partial_report": "p1"})
    assert s.interrupted("c2") is None
    s.set_interrupted("c1", {"original_task": "b", "partial_report": "p2"})
    assert s.interrupted("c1")["original_task"] == "b"


def test_clear_conversation():
    s = OfficeState()
    s.set_active_document("c1", "C:\\OfficeMCP\\book.xlsx")
    s.set_pending_draft("c1", {"entry_id": "E", "recipients": "a@b.com",
                               "subject": "s", "body": "b"})
    s.set_interrupted("c1", {"original_task": "t", "partial_report": "p"})
    s.clear("c1")
    assert s.active_document("c1") is None
    assert s.pending_draft("c1") is None
    assert s.interrupted("c1") is None
