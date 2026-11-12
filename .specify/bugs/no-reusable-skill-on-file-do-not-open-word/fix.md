# Bug Fix: skill_save — one aggregated rejection + honest audit + published example

- **Slug**: no-reusable-skill-on-file-do-not-open-word
- **Fixed**: 2026-11-12T06:34:24Z
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

A rejected skill_save now returns ONE message naming every invalid field (was: first-fail-only, drip-feeding the agent 4+ retries), the audit records the TRUE decision (`blocked` + reason, was: `executed` with no reason), and both tool surfaces carry a copy-paste example record so the first attempt uses the right keys.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/skill_manager/store.py` | `validate_skill` aggregates | collects every violation, joins into one message capped at 6 items; contract still `str | None` (substring assertions keep working) |
| `src/agentic_rag_mcp/skill_manager/api.py` | `_timed` decision-aware | `blocked`/`error` envelopes audit as such WITH their reason; executed otherwise (applies to all four ops) |
| `src/agentic_rag_mcp/server.py` | `skill_save` docstring | example record + "fix them all in the next call" |
| `dify/AGIAssistant/AGI_Assistant.yml` | tool_description | same example (YAML-legal form — plain scalar, no colon-space) + published |
| `tests/unit/test_skill_store.py` | +3 pins | all-violations-in-one-message; valid passes; bounded list |
| `tests/unit/test_skill_feedback.py` | +2 pins | rejected save → audit `blocked` WITH reason; success → `executed` |
| `tests/unit/test_skill_save_docs.py` | new | the example ships on BOTH surfaces |

## Local Verification

- `pytest tests/unit/` → **583 passed**; ruff clean.
- **Live probe** (real tool call with 4 bad fields): ONE message —
  `rejected: name — must be snake_case …; description — …; tier — …; workflow step 1 — missing 'tool'; … missing 'service'; … 'expect' field (FR-006)`
  and the audit row: `decision: blocked` with the full reason (was `executed`, reason dropped).
- Published app: `workflows` table contains the example marker (count 2 — draft + published version).

## Deviations from Assessment

One live discovery: the artifact was mid-clobbered by the owner's own apply-model cycle (they switched the chat default to `qwen/qwen3.8-flash` in the UI — the feature working as designed); the example edit was re-applied on top of their selection and then published, so both survive future export cycles.

## Follow-ups

- The retry storm cannot be re-measured until the next novel-task save in the Chat UI — expected: one attempt (the agent now has the example + the all-fields message).
- The aggregate moves the audit-truthfulness behavior to ALL skill ops (search/get/feedback) — no test regression, an improvement.
