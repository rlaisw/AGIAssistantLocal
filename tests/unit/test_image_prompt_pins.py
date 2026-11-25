"""Spec 050 prompt pins: the binding image policy exists in BOTH general lanes
(Agentic Strategy + Agentic Strategy (Local)) and nowhere else. Modeled on
test_ask_before_answering.py: red before the DSL edit, green after, and it
catches console reverts and one-lane-only pastes.
"""

from __future__ import annotations

import pathlib

import yaml

_DSL = pathlib.Path(__file__).resolve().parents[2] / "dify" / "AGIAssistant" / "AGI_Assistant.yml"

GENERAL_NODES = ("Agentic Strategy", "Agentic Strategy (Local)")
OPERATIONAL_NODES = ("Hermes Local Agent", "PPT-Master", "PPT-Master (Local)")

HEADER = "ANSWER FORMAT — IMAGES (binding):"
BINDING = "BINDING:"
CAP = "CAP: an answer MUST NOT inline more than 10 images"
PLAN_SILENTLY = "plan silently"
SELF_CHECK = "SELF-CHECK"
NO_INVENT = "Never invent an image URL"
FLAT_ARRAY = "web_research also returns a flat images array"
GROUPING = "grouped with the text they belong to, in document order"
SPREAD = "not just one or two"
REUSE = "Reused research keeps its images"
TEXT_ONLY_STATEMENT = "the sources had no usable images"
GENERATED = "antv_infographic returns an interactive HTML page"
CITATIONS = "ANSWER FORMAT — CITATIONS:"

OLD_SOFT = "ANSWER FORMAT — IMAGES (default action)"
OLD_FETCH_MANY = "Fetch as many as are useful"


def _prompts() -> dict[str, str]:
    dsl = yaml.safe_load(_DSL.read_text(encoding="utf-8"))
    found: dict[str, str] = {}

    def walk(node) -> None:
        if isinstance(node, dict):
            title = node.get("title")
            value = ((node.get("agent_parameters") or {}).get("instruction") or {}).get("value")
            if isinstance(title, str) and isinstance(value, str):
                found[title] = value
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(dsl)
    return found


def test_both_general_prompts_carry_the_binding_policy():
    prompts = _prompts()
    for title in GENERAL_NODES:
        assert title in prompts, f"missing prompt node: {title}"
        text = prompts[title]
        for marker in (HEADER, BINDING, CAP, PLAN_SILENTLY, SELF_CHECK,
                       NO_INVENT, FLAT_ARRAY, GROUPING, SPREAD,
                       REUSE, TEXT_ONLY_STATEMENT, GENERATED):
            assert marker in text, f"{title} missing: {marker}"


def test_binding_block_precedes_citations_in_both_lanes():
    prompts = _prompts()
    for title in GENERAL_NODES:
        text = prompts[title]
        assert text.index(HEADER) < text.index(CITATIONS), title


def test_exactly_one_images_block_per_general_prompt():
    prompts = _prompts()
    for title in GENERAL_NODES:
        assert prompts[title].count(HEADER) == 1, title


def test_soft_default_wording_is_replaced():
    prompts = _prompts()
    for title in GENERAL_NODES:
        text = prompts[title]
        assert OLD_SOFT not in text, title
        assert OLD_FETCH_MANY not in text, title


def test_operational_lanes_are_untouched():
    prompts = _prompts()
    for title in OPERATIONAL_NODES:
        if title in prompts:
            assert HEADER not in prompts[title], title
            assert CAP not in prompts[title], title
