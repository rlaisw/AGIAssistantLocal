"""Spec 037 — browser routing gate (FR-001/FR-002): classify a browser
intent and pick its lane. Known/repeatable flows -> scripted; exploratory
-> dynamic; a browser intent NEVER lands on the low-level OS lane."""

from __future__ import annotations

import re
from dataclasses import dataclass

# known/repeatable-flow phrasing: fixed login/scrape/form/download verbs +
# "like yesterday/usual/every day" repetition markers
_REPEATABLE = re.compile(
    r"\b(log ?in|sign ?in)\b.*\b(download|statement|invoice)\b"
    r"|\b(daily|weekly|scheduled)\b.*\b(scrape|export|report)\b"
    r"|\b(scrape|harvest)\b.*\b(site|catalog)\b"
    r"|\b(download|save)\b.*\b(file|statement|invoice|report)\b"
    r"|\b(fill ?in|fill out|submit)\b.*\b(form)\b"
    r"|\blike\s+(yesterday|usual|before|last time)\b"
    r"|\b(as always|the usual|every (day|morning))\b"
    # browsing-is-working-but-very-slow (2026-11-11): search-and-report is
    # a KNOWN flow — the scripted search_and_report fast path (~10-25s)
    r"|\bsearch( for|ing)?\b.*\b(report|tell|show|display|find out)\b"
    r"|\bsearch (for|the)\b"
    r"|\bwhat is\b.*\b(today|now|current)\b"
    r"|\blook up\b.*\b(tell|show|and)\b"
    r"|\b(find|check)\b.*\b(today'?s?|current)\b"
    r"|\bsearch the\b",
    re.IGNORECASE)
# exploratory phrasing: open-ended reading/comparison/discovery
_EXPLORATORY = re.compile(
    r"\b(what does|find out|look around|compare|explore|browse|read)\b"
    r"|\b(cheapest|cheaper|best)\b.*\b(find|which)\b"
    r"|\b(take a look|check out|see what)\b",
    re.IGNORECASE)
# any browser surface at all
_BROWSER_HINT = re.compile(
    r"\b(browser|web ?site|website|web ?page|url|http|chrome|edge|firefox"
    r"|internet|pages?|portal|site|log ?in|scrape|intranet|form|forms?"
    r"|search( for| the|ing)?|look ?up|find out)\b"
    r"|\bwhat is\b.{0,40}\b(today|now|current|weather|price|temperature)\b",
    re.IGNORECASE)
# long-flow markers: the split hint rides the verdict, never blocks
_LONG = re.compile(
    r"\b(all|whole|entire|every)\b.*\b(pages?|catalog|site)\b"
    r"|\b(500|hundreds of|thousands of)\b.*\b(pages?|items)\b",
    re.IGNORECASE)

_ASK_BACK = ("Blocked: that request is not a browser task — ask the user "
             "to rephrase it as a web/browse request (the browser lanes "
             "route only browser intents)")


@dataclass
class BrowserVerdict:
    lane: str          # scripted | dynamic | ask-back  (never "os")
    reason: str
    script: str | None = None
    split_hint: bool = False


def gate_browser_intent(task: str) -> BrowserVerdict:
    """FR-002 pin: no browser intent routes to the OS lane; a non-browser
    request is an honest ask-back, never a silent route elsewhere."""
    text = (task or "").strip()
    if not text or not _BROWSER_HINT.search(text):
        return BrowserVerdict(lane="ask-back", reason=_ASK_BACK)
    split_hint = bool(_LONG.search(text))
    if _REPEATABLE.search(text):
        reason = ("known/repeatable web flow — scripted lane (deterministic "
                  "scripted run with per-step checkpoints)")
        return BrowserVerdict(lane="scripted", reason=reason,
                               split_hint=split_hint)
    reason = ("exploratory browsing — dynamic lane (Playwright MCP, "
              "report observed content only)")
    return BrowserVerdict(lane="dynamic", reason=reason,
                          split_hint=split_hint)