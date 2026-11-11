"""Spec 038 — Tier2State suite (task T005): the 034-pattern conversation-
scoped recommendation+confirm state with supersession (FR-004)."""

from __future__ import annotations

import threading

from agentic_rag_mcp.task_gateway.tier2_state import Tier2State


def _rec(**kw):
    base = {"conversation_id": "c1", "issue_type": "print",
            "repair_name": "restart_spooler",
            "repair_text": "Restart-Service Spooler"}
    base.update(kw)
    return base


class TestBasics:
    def test_empty_pending_is_none(self):
        assert Tier2State().pending("c1") is None

    def test_set_and_pending(self):
        st = Tier2State()
        st.set_pending(_rec())
        assert st.pending("c1")["repair_name"] == "restart_spooler"

    def test_conversation_scoped(self):
        st = Tier2State()
        st.set_pending(_rec())
        assert st.pending("c2") is None  # another conversation: clean slate

    def test_clear(self):
        st = Tier2State()
        st.set_pending(_rec())
        st.clear("c1")
        assert st.pending("c1") is None

    def test_set_replaces_pending(self):
        # a new recommendation supersedes the old (one pending, newest wins)
        st = Tier2State()
        st.set_pending(_rec())
        st.set_pending(_rec(repair_name="deeper_repair",
                             repair_text="DISM /Online /Cleanup-Image /RestoreHealth"))
        assert st.pending("c1")["repair_name"] == "deeper_repair"


class TestSupersession:
    def test_new_tier1_supersedes(self):
        # FR-004: a fresh tier1 run replaces the recommendation — the old
        # confirm must not execute a stale repair
        st = Tier2State()
        st.set_pending(_rec())
        st.supersede("c1")
        assert st.pending("c1") is None

    def test_thread_safe(self):
        st = Tier2State()
        errs: list[Exception] = []

        def worker(i: int):
            try:
                for _ in range(50):
                    st.set_pending(_rec(repair_name=f"r{i}"))
                    st.pending("c1")
                    st.clear("c1")
            except Exception as exc:  # noqa: BLE001
                errs.append(exc)

        ts = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert not errs