"""Spec 045 unit pins: the ask-before-answering steering rule must exist in
EVERY answering prompt of the chatflow DSL — both Agentic Strategy nodes, the
Hermes Local Agent, and both PPT-Master nodes (bug fix 2026-11-19: the rule
initially covered only the strategy prompts, leaving the other answering
lanes free to answer without asking). Red before the edit, green after —
these catch console reverts, careless hand edits, and drift."""

from __future__ import annotations

import pathlib

import pytest
import yaml

_DSL = pathlib.Path(__file__).resolve().parents[2] / "dify" / "AGIAssistant" / "AGI_Assistant.yml"

HEADLINE = (
    "Before answering the user's question, ask for any critical missing information."
)
CRITICAL_DEF = "materially changes the answer"
NO_OVER_ASKING = "do not interrogate"
NO_RE_ASK = "Never re-ask what the conversation already established"
SECRETS_EXCLUSION = "Never ask for passwords or API keys"
CONTEXT_DEPENDENT = "Context-dependent questions"
UNIVERSAL_FACTS = "Universal facts with a single right answer"
END_REPLY = "END THE REPLY THERE"


ANSWERING_NODE_TITLES = (
    "Agentic Strategy",
    "Agentic Strategy (Local)",
    "Hermes Local Agent",
    "PPT-Master",
    "PPT-Master (Local)",
)


def _strategy_prompts() -> list[str]:
    dsl = yaml.safe_load(_DSL.read_text(encoding="utf-8"))
    prompts: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if node.get("title") in ANSWERING_NODE_TITLES:
                value = ((node.get("agent_parameters") or {}).get("instruction") or {}).get("value")
                if isinstance(value, str):
                    prompts.append(value)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(dsl)
    return prompts


def test_dsl_loads_and_answering_prompts_found():
    prompts = _strategy_prompts()
    assert prompts, "no answering prompts found in the DSL"
    assert len(prompts) == len(ANSWERING_NODE_TITLES), (
        f"expected {len(ANSWERING_NODE_TITLES)} answering prompts "
        f"(strategy x2, Hermes Local Agent, PPT-Master x2), found {len(prompts)}"
    )


@pytest.mark.parametrize("fragment", [HEADLINE, CRITICAL_DEF, NO_OVER_ASKING, NO_RE_ASK, SECRETS_EXCLUSION, CONTEXT_DEPENDENT, UNIVERSAL_FACTS, END_REPLY])
def test_rule_fragments_present_in_every_strategy_prompt(fragment):
    prompts = _strategy_prompts()
    assert len(prompts) == len(ANSWERING_NODE_TITLES), f"expected all answering prompts, found {len(prompts)}"
    missing_in = [i for i, text in enumerate(prompts) if fragment not in text]
    assert not missing_in, f"fragment {fragment!r} missing from prompt(s) {missing_in}"


def _agentic_strategy_prompts() -> list[str]:
    dsl = yaml.safe_load(_DSL.read_text(encoding="utf-8"))
    prompts: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if str(node.get("title", "")).startswith("Agentic Strategy"):
                value = ((node.get("agent_parameters") or {}).get("instruction") or {}).get("value")
                if isinstance(value, str):
                    prompts.append(value)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(dsl)
    return prompts


def test_follow_up_guidance_present_in_both_agentic_strategy_prompts():
    prompts = _agentic_strategy_prompts()
    assert len(prompts) == 2, f"expected both Agentic Strategy prompts, found {len(prompts)}"
    for i, text in enumerate(prompts):
        assert "ANSWER FORMAT — FOLLOW-UP" in text, f"missing follow-up guidance in prompt {i}"
        assert "final paragraph" in text, f"missing final-paragraph placement in prompt {i}"
        assert "Want me to" in text, f"missing follow-up question example in prompt {i}"
