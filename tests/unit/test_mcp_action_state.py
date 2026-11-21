"""Unit: conversation-scoped MCP-Action proposals (spec 047, T004).

The store validates the closed action schemas and consumes consent only for a
plain response on the immediately following turn. These tests intentionally
cover state, not tool envelopes or the user-facing offer text.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from agentic_rag_mcp.mcp_action.state import ProposalStore

EFFECT = "Change the requested printer setting, then display the result."


def _create(store, conversation_id="c1", dialogue_count=4):
    return store.create(
        conversation_id,
        "windows_default_printer",
        {"printer": "Printer A"},
        EFFECT,
        dialogue_count,
    )


def _assert_blocked(decision):
    assert decision.status == "blocked"
    assert decision.proposal is None
    assert isinstance(decision.reason, str) and decision.reason


@pytest.mark.parametrize(
    ("action_id", "parameters"),
    [
        ("windows_default_printer", {"printer": "Printer A"}),
        ("word_printer_duplex", {"printer": "Printer A", "orientation": "long-edge"}),
        ("word_printer_duplex", {"printer": "Printer A", "orientation": "short-edge"}),
    ],
)
def test_create_accepts_the_two_reviewed_actions(action_id, parameters):
    proposal = ProposalStore().create("c1", action_id, parameters, EFFECT, 4)
    assert proposal.action_id == action_id
    assert proposal.parameters == parameters


@pytest.mark.parametrize(
    "action_id",
    ["", "WINDOWS_DEFAULT_PRINTER", "excel_change_setting", "run_powershell", None],
)
def test_create_rejects_every_other_action_id(action_id):
    with pytest.raises(ValueError):
        ProposalStore().create("c1", action_id, {"printer": "Printer A"}, EFFECT, 4)


def test_proposal_exposes_creation_metadata_and_default_caveats():
    store = ProposalStore(clock=lambda: 1000.0)
    proposal = _create(store, dialogue_count=0)

    assert isinstance(proposal.proposal_id, str) and proposal.proposal_id
    assert proposal.conversation_id == "c1"
    assert proposal.parameters == {"printer": "Printer A"}
    assert proposal.effect == EFFECT
    assert proposal.caveats == []
    assert proposal.created_dialogue_count == 0
    assert proposal.created_at_utc.utcoffset() == timedelta(0)
    assert proposal.expires_at_monotonic == pytest.approx(1900.0)

    with_caveats = store.create(
        "c2",
        "windows_default_printer",
        {"printer": "Printer B"},
        EFFECT,
        0,
        caveats=["A managed default may not persist."],
    )
    assert with_caveats.caveats == ["A managed default may not persist."]
    assert with_caveats.proposal_id != proposal.proposal_id


@pytest.mark.parametrize("conversation_id", ["", "   ", None, 123])
def test_create_requires_a_nonempty_conversation_id(conversation_id):
    with pytest.raises(ValueError):
        ProposalStore().create(
            conversation_id,
            "windows_default_printer",
            {"printer": "Printer A"},
            EFFECT,
            4,
        )


@pytest.mark.parametrize(
    ("action_id", "parameters"),
    [
        ("windows_default_printer", {}),
        ("windows_default_printer", {"printer": "P", "orientation": "long-edge"}),
        ("windows_default_printer", {"printer": "P", "command": "whoami"}),
        ("windows_default_printer", None),
        ("windows_default_printer", ["P"]),
        ("word_printer_duplex", {"printer": "P"}),
        ("word_printer_duplex", {"orientation": "long-edge"}),
        ("word_printer_duplex", {"printer": "P", "orientation": "long-edge", "effect": "x"}),
    ],
)
def test_parameter_schemas_are_closed(action_id, parameters):
    with pytest.raises(ValueError):
        ProposalStore().create("c1", action_id, parameters, EFFECT, 4)


@pytest.mark.parametrize(
    "name",
    [
        "Office * Test",
        "Quote ' Printer",
        'Double " Printer',
        "$(whoami) Printer",
        "Backtick ` Printer",
        "Imprimante café",
        "Printer  Copy",
    ],
)
def test_printer_is_trimmed_and_literal_content_is_preserved(name):
    proposal = ProposalStore().create(
        "c1",
        "windows_default_printer",
        {"printer": f" \t{name}\t "},
        EFFECT,
        4,
    )
    assert proposal.parameters["printer"] == name


@pytest.mark.parametrize("printer", ["", " ", "\t", "\r\n", None, 7, ["Printer"]])
def test_printer_must_be_a_nonempty_string_after_trimming(printer):
    with pytest.raises(ValueError):
        ProposalStore().create(
            "c1", "windows_default_printer", {"printer": printer}, EFFECT, 4
        )


@pytest.mark.parametrize("printer", ["Bad\0Printer", "Bad\rPrinter", "Bad\nPrinter"])
def test_printer_rejects_nul_cr_and_lf(printer):
    with pytest.raises(ValueError):
        ProposalStore().create(
            "c1", "windows_default_printer", {"printer": printer}, EFFECT, 4
        )


def test_printer_length_is_bounded():
    store = ProposalStore()
    proposal = store.create(
        "c1", "windows_default_printer", {"printer": "P" * 256}, EFFECT, 4
    )
    assert len(proposal.parameters["printer"]) == 256
    with pytest.raises(ValueError):
        store.create(
            "c2", "windows_default_printer", {"printer": "P" * 257}, EFFECT, 4
        )


@pytest.mark.parametrize("orientation", ["", "long_edge", "Long-Edge", "two-sided", None, 1])
def test_duplex_orientation_is_exactly_long_edge_or_short_edge(orientation):
    with pytest.raises(ValueError):
        ProposalStore().create(
            "c1",
            "word_printer_duplex",
            {"printer": "Printer A", "orientation": orientation},
            EFFECT,
            4,
        )


@pytest.mark.parametrize("dialogue_count", [-1, 1.5, "1", None, True, False])
def test_create_dialogue_count_must_be_an_integer_at_least_zero(dialogue_count):
    with pytest.raises(ValueError):
        ProposalStore().create(
            "c1",
            "windows_default_printer",
            {"printer": "Printer A"},
            EFFECT,
            dialogue_count,
        )


@pytest.mark.parametrize("dialogue_count", [-1, 5.0, "5", None, True, False])
def test_resolve_rejects_invalid_dialogue_counts_without_leaving_pending(dialogue_count):
    store = ProposalStore()
    _create(store)
    _assert_blocked(store.resolve("c1", dialogue_count, "yes"))
    _assert_blocked(store.resolve("c1", 5, "yes"))


def test_newer_create_supersedes_the_conversations_previous_proposal():
    store = ProposalStore()
    first = _create(store)
    second = store.create(
        "c1",
        "word_printer_duplex",
        {"printer": "Printer B", "orientation": "short-edge"},
        "Set short-edge duplex.",
        8,
    )

    decision = store.resolve("c1", 9, "yes")
    assert decision.status == "reserved"
    assert decision.proposal.proposal_id == second.proposal_id
    assert decision.proposal.proposal_id != first.proposal_id
    assert decision.proposal.parameters == {
        "printer": "Printer B",
        "orientation": "short-edge",
    }


@pytest.mark.parametrize(
    "query",
    [
        "yes",
        "YES",
        "  yes  ",
        "Yeah!",
        "yep.",
        "okay",
        "OK!!!",
        "confirm",
        "proceed",
        "go ahead",
        "yes, help to do it",
        "Yes, help me do it.",
        "yes, please do it",
        "yes, go ahead",
        "okay, do it",
        "sure, please do it",
    ],
)
def test_plain_affirmative_vocabulary_reserves(query):
    store = ProposalStore()
    proposal = _create(store)
    decision = store.resolve("c1", 5, query)
    assert decision.status == "reserved"
    assert decision.proposal is proposal


@pytest.mark.parametrize(
    "query", ["no", "NO", "  no  ", "Nope!", "cancel", "CANCEL.", "stop", "never mind"]
)
def test_plain_negative_vocabulary_cancels(query):
    store = ProposalStore()
    _create(store)
    decision = store.resolve("c1", 5, query, phase="cancel")
    assert decision.status == "cancelled"
    _assert_blocked(store.resolve("c1", 5, "no", phase="cancel"))


@pytest.mark.parametrize(
    ("phase", "query", "matching_query"),
    [
        ("confirm", "no", "yes"),
        ("confirm", "cancel", "yes"),
        ("cancel", "yes", "no"),
        ("cancel", "okay", "no"),
    ],
)
def test_phase_query_mismatch_invalidates(phase, query, matching_query):
    store = ProposalStore()
    _create(store)
    _assert_blocked(store.resolve("c1", 5, query, phase=phase))
    _assert_blocked(store.resolve("c1", 5, matching_query, phase=phase))


@pytest.mark.parametrize(
    ("phase", "dialogue_count", "query"),
    [
        ("confirm", 4, "yes"),
        ("confirm", 6, "yes"),
        ("cancel", 4, "no"),
        ("cancel", 6, "no"),
    ],
)
def test_only_the_immediately_following_turn_can_resolve(phase, dialogue_count, query):
    store = ProposalStore()
    _create(store)
    _assert_blocked(store.resolve("c1", dialogue_count, query, phase=phase))
    _assert_blocked(store.resolve("c1", 5, "yes" if phase == "confirm" else "no", phase=phase))


def test_later_unrelated_turn_invalidates():
    store = ProposalStore()
    _create(store)
    _assert_blocked(store.resolve("c1", 6, "Tell me about the weather instead."))
    _assert_blocked(store.resolve("c1", 7, "yes"))


@pytest.mark.parametrize(
    "query",
    [
        "yes, but use another printer",
        "yes, change to short-edge instead",
        "no, but actually do it",
        "maybe",
        "",
    ],
)
def test_modified_unrecognized_or_empty_response_invalidates(query):
    store = ProposalStore()
    _create(store)
    _assert_blocked(store.resolve("c1", 5, query))
    _assert_blocked(store.resolve("c1", 5, "yes"))


@pytest.mark.parametrize(
    ("age", "expected"), [(899.99, "reserved"), (900.0, "blocked"), (900.01, "blocked")]
)
def test_monotonic_expiry_boundary(age, expected):
    now = [100.0]
    store = ProposalStore(clock=lambda: now[0])
    proposal = _create(store)
    now[0] += age

    decision = store.resolve("c1", 5, "yes")
    assert decision.status == expected
    if expected == "reserved":
        assert decision.proposal is proposal
    else:
        _assert_blocked(decision)
        _assert_blocked(store.resolve("c1", 5, "yes"))


def test_wrong_conversation_is_blocked_without_consuming_real_proposals():
    store = ProposalStore()
    first = _create(store, "c1")
    second = _create(store, "c2")

    _assert_blocked(store.resolve("different-conversation", 5, "yes"))
    assert store.resolve("c1", 5, "yes").proposal is first
    assert store.resolve("c2", 5, "yes").proposal is second


def test_repeated_confirmation_is_blocked():
    store = ProposalStore()
    _create(store)
    assert store.resolve("c1", 5, "yes").status == "reserved"
    _assert_blocked(store.resolve("c1", 5, "yes"))


def test_confirmation_after_cancellation_is_blocked():
    store = ProposalStore()
    _create(store)
    assert store.resolve("c1", 5, "no", phase="cancel").status == "cancelled"
    _assert_blocked(store.resolve("c1", 5, "yes"))


def test_concurrent_confirmation_reserves_exactly_once():
    store = ProposalStore()
    proposal = _create(store)
    barrier = threading.Barrier(2)

    def confirm():
        barrier.wait(timeout=5)
        return store.resolve("c1", 5, "yes")

    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = list(pool.map(lambda _: confirm(), range(2)))

    assert sorted(decision.status for decision in decisions) == ["blocked", "reserved"]
    reserved = [decision for decision in decisions if decision.status == "reserved"]
    assert len(reserved) == 1
    assert reserved[0].proposal is proposal
    _assert_blocked(store.resolve("c1", 5, "yes"))


@pytest.mark.parametrize("trigger", ["create", "resolve"])
def test_expired_entries_are_cleaned_by_unrelated_state_operations(trigger):
    now = [10.0]
    store = ProposalStore(clock=lambda: now[0])
    _create(store)
    now[0] = 910.0

    if trigger == "create":
        _create(store, "other", dialogue_count=0)
    else:
        _assert_blocked(store.resolve("other", 1, "yes"))

    # Rewinding the fake clock exposes entries that were merely ignored rather
    # than removed: a cleaned proposal must stay gone even below its old TTL.
    now[0] = 10.0
    _assert_blocked(store.resolve("c1", 5, "yes"))


@pytest.mark.parametrize(("phase", "query"), [("confirm", "yes"), ("cancel", "no")])
def test_orphan_resolution_on_a_new_empty_store_fails_closed(phase, query):
    _assert_blocked(ProposalStore().resolve("orphan", 1, query, phase=phase))


def test_new_store_after_restart_fails_closed():
    old_store = ProposalStore()
    _create(old_store)
    restarted_store = ProposalStore()
    _assert_blocked(restarted_store.resolve("c1", 5, "yes"))
