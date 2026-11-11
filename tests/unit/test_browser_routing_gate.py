"""Spec 037 — browser routing gate suite (task T003): the FR-001/FR-002
matrix — known-flow → scripted, exploratory → dynamic, browser intent NEVER
lands on the OS lane, long flows split."""

from __future__ import annotations

import pytest

from agentic_rag_mcp.browser_lanes.routing_gate import gate_browser_intent


@pytest.mark.parametrize("task,lane", [
    # known/repeatable flows -> scripted (FR-001)
    ("log into the portal and download this month's statement", "scripted"),
    ("run the daily price scrape like yesterday", "scripted"),
    ("fill in the leave-request form on the intranet like usual", "scripted"),
    # exploratory -> dynamic (FR-001)
    ("what does this page say about the new pricing", "dynamic"),
    ("compare these two product pages and tell me the cheaper", "dynamic"),
    ("look around the docs site and find the API key section", "dynamic"),
    # browser-as-desktop decoys -> NEVER os (FR-002)
    ("open the browser window and click around a bit", "dynamic"),
    ("open Chrome and show me the news site", "dynamic"),
])
def test_matrix(task, lane):
    verdict = gate_browser_intent(task)
    assert verdict.lane == lane, f"{task!r} -> {verdict.lane} (want {lane})"
    assert verdict.lane != "os"


def test_non_browser_intent_ask_back():
    # a request with no browser content is not ours to route
    verdict = gate_browser_intent("restart the print spooler service")
    assert verdict.lane == "ask-back"
    assert "browser" in verdict.reason.lower()


def test_long_flow_split_hint():
    verdict = gate_browser_intent(
        "scrape the whole 500-page catalog site like yesterday's daily scrape")
    assert verdict.lane == "scripted"
    assert verdict.split_hint is True


def test_verdict_carries_honest_reason():
    verdict = gate_browser_intent("open the browser and read this page aloud")
    assert verdict.reason  # always honest, always named