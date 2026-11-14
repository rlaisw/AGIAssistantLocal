"""after-the-task-was-done (2026-11-14): structural v2 fast-path exemption.

The published DSL rule (still-little-bit-slow, 2026-11-13) says the seven
v2 deterministic tools skip the skill loop — no skill_search before, no
skill_save after. Instruction-level rules of this shape do not hold
(measured 2026-11-14: loop rounds ran ~60-100 s after exempt v2 work,
after the task was visibly done), so this gate enforces it structurally:
the audit funnel classifies every operation per conversation, and while
the conversation's last operational op was v2-exempt, the loop tools
answer with an honest skip envelope instead of executing. Any non-exempt
operational op (a hermes lane, a scripted run, a task-gateway call)
restores the loop for everything after it."""

from __future__ import annotations

EXEMPT_OPS = frozenset({
    "doc-write-v2", "doc-read-v2", "xls-write-v2", "ppt-write-v2",
    "browser-navigate-v2", "browser-read-v2", "browser-click-v2",
})
# loop machinery, status probes, and control rows never change the
# conversation's class — only real operational work does
NEUTRAL_OPS = frozenset({
    "skill-search", "skill-save", "skill-get", "skill-feedback",
    "browser-status", "ask-back", "unsupported", "cancel-turn",
})

SKIP_REASON = ("loop-exempt turn (v2 fast path): the conversation's last "
               "operation was a v2 deterministic tool, which skips the skill "
               "loop entirely — no skill_search, no skill_save; proceed with "
               "the task and report directly (learning records add only "
               "protocol rounds around sub-2-second tool calls)")

_last_class: dict[str, str] = {}


def record(operation: str, conversation_id: str | None) -> None:
    if not conversation_id or operation in NEUTRAL_OPS:
        return
    _last_class[conversation_id] = "exempt" if operation in EXEMPT_OPS else "loop"


def exempt_active(conversation_id: str | None) -> bool:
    return bool(conversation_id) and _last_class.get(conversation_id) == "exempt"
