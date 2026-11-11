"""Spec 036 — replay helpers: server-side substitution with honest ask-back
and per-step expect verification (research R4). DATA ONLY: prepare_replay
returns the filled workflow for the lane to execute through its normal
gated tools — the skill surface itself executes nothing (035 FR-020
structural: gated steps are executable only through their live
draft→confirm lane tool)."""

from __future__ import annotations

import json
import re

_SLOT_RE = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")

# tools whose execution is confirm-gated (spec 034 protocol) — a replayed
# step on one of these pauses for its own live confirm; the skill record
# never pre-confirms (035 FR-020)
GATED_TOOLS = {"hermes_run_powershell"}

# the four skill tools are data-only — they never execute anything
SKILL_TOOLS = {"skill_search", "skill_get", "skill_save", "skill_feedback"}


def _substitute_text(text: str, values: dict) -> tuple[str, list[str]]:
    missing: list[str] = []

    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key in values:
            return str(values[key])
        if key not in missing:
            missing.append(key)
        return m.group(0)

    return _SLOT_RE.sub(repl, text), missing


def prepare_replay(workflow: list[dict], values: dict) -> dict:
    """Fill {{slots}} across every step. Unfilled slot -> honest ask-back
    (never a guess). Gated steps are marked so the lane knows to pause."""
    if not workflow:
        return {"status": "ask-back",
                "reason": "the skill has an empty workflow — nothing to replay"}
    filled: list[dict] = []
    missing_all: list[str] = []
    for step in workflow:
        params = json.loads(_substitute_text(
            json.dumps(step.get("params_template") or {}), values)[0])
        text, missing = _substitute_text(
            json.dumps(step.get("params_template") or {}), values)
        params = json.loads(text)
        for key in missing:
            if key not in missing_all:
                missing_all.append(key)
        out = {
            "step": step.get("step"),
            "tool": step.get("tool"),
            "service": step.get("service"),
            "params": params,
            "expect": step.get("expect"),
            "gated": step.get("tool") in GATED_TOOLS,
        }
        filled.append(out)
    if missing_all:
        return {"status": "ask-back",
                "reason": ("missing values for: "
                           + ", ".join(f"{{{{{k}}}}}" for k in missing_all)
                           + " — ask the user; never guess a substitution")}
    return {"status": "ok", "workflow": filled}


def verify_expect(step_result: dict, expect: str) -> bool:
    """A step passed iff it ran ok AND its result mentions the expectation.
    A near-miss (plausible-but-wrong skill) fails its first expect and the
    replay bails out honestly (Edge Cases)."""
    if step_result.get("status") != "ok":
        return False
    needle = " ".join(expect.lower().split())
    haystack = " ".join(str(step_result.get("result", "")).lower().split())
    return needle in haystack
