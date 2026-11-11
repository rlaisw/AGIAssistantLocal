"""Spec 036 — replay walk (T031): drive a prepared workflow through the
EXISTING lane tool handlers, step by step, verifying each step's expect.

Pause/resume on gated steps (035 FR-020): a step whose tool is confirm-gated
is never executed by the walk itself — the walk returns `pending-confirmation`
naming the lane tool, the draft registers in the spec-034 conversation state
(via the lane tool's own call), and the NEXT walk call (confirm=True from the
agent, after the user's live confirmation) resumes at the following step.
Cancellation aborts the walk without recording skill failure. The skill
record pre-confirms nothing: the only path to a gated tool's execution is
the lane tool's own live draft→confirm, exactly as a fresh request."""

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
    (never a guess). Gated steps are marked so the walk knows to pause."""
    if not workflow:
        return {"status": "ask-back",
                "reason": "the skill has an empty workflow — nothing to replay"}
    filled: list[dict] = []
    missing_all: list[str] = []
    for step in workflow:
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


class ReplayWalk:
    """Server-side replay of one prepared workflow.

    `execute_step` runs ONE step through its lane handler and, on success,
    advances. A gated step NEVER executes here: `next_action` reports
    `pending-confirmation` with the exact lane tool call the agent must
    make (the lane tool registers the draft in the spec-034 state); after
    the user confirms and the lane tool executes, `advance_past_gated`
    moves the cursor. `cancel` aborts honestly — no failure feedback.
    """

    def __init__(self, audit, skill_name: str, conversation_id: str,
                 workflow: list[dict]):
        self.audit = audit
        self.skill_name = skill_name
        self.conversation_id = conversation_id
        self.workflow = workflow
        self.cursor = 0
        self.audit.write_attempt(
            decision="executed", operation="skill-replay-start",
            normalized_path=None, allowed_root="",
            outcome=f"{skill_name} v-step {len(workflow)}",
            conversation_id=conversation_id)

    def _abort(self, outcome: str, reason: str, decision: str = "executed") -> dict:
        self.audit.write_attempt(
            decision=decision, operation="skill-replay-abort",
            normalized_path=None, allowed_root="",
            reason=reason if decision != "executed" else None,
            outcome=outcome[:200], conversation_id=self.conversation_id)
        return {"status": "aborted", "reason": reason,
                "completed_steps": self.cursor}

    def done(self) -> bool:
        return self.cursor >= len(self.workflow)

    def current_step(self) -> dict | None:
        return self.workflow[self.cursor] if not self.done() else None

    def next_action(self) -> dict:
        """What the agent must do for the current step. Non-gated steps
        carry the lane call params; gated steps carry pending-confirmation —
        this class NEVER executes a gated tool (035 FR-020 structural)."""
        step = self.current_step()
        if step is None:
            return {"status": "done",
                    "completed_steps": self.cursor,
                    "skill": self.skill_name}
        if step.get("gated"):
            return {"status": "pending-confirmation",
                    "step": self.cursor + 1,
                    "tool": step["tool"],
                    "params": step["params"],
                    "instruction": (
                        f"call {step['tool']} with these params to draft "
                        f"the command, show it VERBATIM, and only execute "
                        f"after the user's live confirmation — the skill "
                        "record does not pre-confirm; then advance the walk"),
                    "skill": self.skill_name}
        return {"status": "run-step",
                "step": self.cursor + 1,
                "tool": step["tool"],
                "service": step.get("service"),
                "params": step["params"],
                "expect": step.get("expect"),
                "skill": self.skill_name}

    def record_step_result(self, step_result: dict) -> dict:
        """Verify the current step's expect against the lane tool's result.
        Pass -> advance; fail -> honest abort (near-miss bailout)."""
        step = self.current_step()
        if step is None:
            return {"status": "done", "completed_steps": self.cursor}
        if step.get("gated"):
            # structural: a gated step's execution result arrives only via
            # advance_past_gated, never through this path
            return self._abort("gated-step-ran-without-confirmation",
                               "the walk refuses to record a result for a "
                               "gated step — confirm via the lane tool first",
                               decision="blocked")
        if verify_expect(step_result, step.get("expect") or ""):
            self.cursor += 1
            if self.done():
                return {"status": "done", "completed_steps": self.cursor,
                        "skill": self.skill_name}
            return self.next_action()
        return self._abort(
            f"expect mismatch at step {self.cursor + 1}",
            f"step expected '{step.get('expect')}' — "
            f"got '{str(step_result.get('result', ''))[:200]}'; the replay "
            f"stops honestly (no forcing the workflow)",
            decision="error")

    def advance_past_gated(self) -> dict:
        """After a confirmed gated step executed via its lane tool, resume
        the walk at the next step."""
        step = self.current_step()
        if step is None or not step.get("gated"):
            return self._abort("advance-without-gated-step",
                               "no gated step to advance past",
                               decision="blocked")
        self.cursor += 1
        if self.done():
            return {"status": "done", "completed_steps": self.cursor,
                    "skill": self.skill_name}
        return self.next_action()

    def cancel(self, reason: str = "user cancelled") -> dict:
        """Abort without failure feedback for the skill (spec edge case:
        cancellation is not skill failure)."""
        return self._abort("cancelled", f"{reason} — no failure feedback "
                                        "recorded for the skill")