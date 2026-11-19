"""Spec 045 unit pins: the ask-before-answering steering rule must exist in
every Agentic Strategy system prompt of the chatflow DSL. Red before the edit,
green after — these catch console reverts, careless hand edits, and drift."""

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


def _strategy_prompts() -> list[str]:
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


def test_dsl_loads_and_strategy_prompts_found():
    prompts = _strategy_prompts()
    assert prompts, "no Agentic Strategy system prompts found in the DSL"
    assert len(prompts) == 2, f"expected 2 strategy prompts, found {len(prompts)}"


@pytest.mark.parametrize("fragment", [HEADLINE, CRITICAL_DEF, NO_OVER_ASKING, NO_RE_ASK, SECRETS_EXCLUSION])
def test_rule_fragments_present_in_every_strategy_prompt(fragment):
    prompts = _strategy_prompts()
    assert len(prompts) == 2, f"expected 2 strategy prompts, found {len(prompts)}"
    missing_in = [i for i, text in enumerate(prompts) if fragment not in text]
    assert not missing_in, f"fragment {fragment!r} missing from prompt(s) {missing_in}"
