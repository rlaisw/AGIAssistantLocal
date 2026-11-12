# Bug Fix: trust bootstrap + audit cid + save-thrash wording (items 2+3 of the assessment)

- **Slug**: whole-process-is-slow-take-long-time-to-finish
- **Fixed**: 2026-11-12T07:09:45Z
- **Assessment**: ./assessment.md
- **Status**: applied (items 2+3; item 1 — the desktop v2 proxy — is its own lifecycle)

## Summary

The skill trust loop can now bootstrap: a same-name `skill_save` after a successful manual repeat-solve increments `success_count` (3 repeats → `reusable: true` — live-verified). Launch audit rows carry `conversation_id` (they were unqueryable per-conversation), and the save description demands copying the example record instead of building fields one at a time.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/skill_manager/store.py` | `record_repeat_solve()` | guarded: `UPDATE … WHERE name=? AND version > 1` — only in-place updates (v1 of a NEW intent is not a repeat) count |
| `src/agentic_rag_mcp/skill_manager/api.py` | `save()` calls it on version > 1 | the bootstrap: repeated manual solves of the same intent accumulate trust |
| `src/agentic_rag_mcp/server.py` | `hermes_launch_app`: `conversation_id` on all four audit writes (blocked/error/error/executed) | the audit is now per-conversation queryable |
| `src/agentic_rag_mcp/server.py` | `skill_save` docstring | "+ COPY the example record's shape exactly; never construct fields one at a time." |
| `tests/unit/test_skill_feedback.py` | +2 pins | 3rd repeat-solve → reusable (own fixture — the shared `mgr` fixture pre-saves); fresh v1 → no inflation |

## Local Verification

- **595 unit tests green**, ruff clean, sidecar rebuilt (43 tools).
- **Live bootstrap proof** (real tool calls): save v1 (no increment) → repeat-saves v2, v3 (sample 2, reusable False) → **3rd repeat (v4) → search returns sample 3, rate 1.0, `reusable: True`** — the exact deadlock from the assessment, broken end-to-end.

## Deviations from Assessment

- The wording edit needed a line-anchored append (the assessment's phrasing didn't exist verbatim in the docstring) — same intent.
- `record_repeat_solve` counts ALL same-name updates as repeat-solves (the guard is version > 1, not same-conversation): the DSL's flow (manual-solve-then-save) is the only sanctioned same-name save path, so this is the pragmatic guard; a cross-conversation same-intent repeat IS genuine evidence, so the looser guard is also more correct.

## Follow-ups

- Item 1 (the desktop v2 proxy — the 109 s → 20-40 s structural fix) awaits its own lifecycle: say "start the desktop v2 spec".
- The `bootstrap_test_probe` skill (v4) stays in the store — a harmless live-test record (no delete exists, by design).
- Watch the next real "open MS Word, type hello": after 2 more manual repeats the skill becomes reusable and the search round starts paying off.
