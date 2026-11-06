# Bug Verification: conversation-level strip memory — save+close class 109 s → 42 s, detection tax gone

- **Slug**: `completed-message-wait-long-time`
- **Tested**: 2026-11-06T07:30+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified (one new minor finding routed below)

## Summary

The original complaint — a save+close whose 3 s of COM work took 109 s, largely re-paying the channel-detection tax every task — no longer reproduces: in a fresh three-task conversation, the first task detected the strip once (as designed), and both follow-on tasks **skipped detection entirely** (no canary or degradation step in their reports), with the save+close class completing in **42.4 s** — down from 109 s, with the batched work running straight on the direct channel. One new minor finding surfaced: an agent-side edit-protocol gap on an "add a second line" follow-up (routed below, not a regression of this fix).

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix): fresh 3-task conversation | live `hermes_office_task` ×3, same conversation_id: create (Word) → edit → save+close | **pass** | Task 1: detection ran once (expected; strip recorded) — 57.5 s. Task 2: **detection skipped** — 38.7 s. Task 3 (save+close, the bug's exact class): **detection skipped, one batched step via direct channel** — **42.4 s vs the 109 s baseline** |
| Detection-skip semantics | report scan for canary/degradation steps in follow-on tasks | **pass** | Tasks 2–3 contain no channel-detection narration; task 1 recorded the strip and the hint carried |
| State store unit test | `tests/unit/test_office_state.py::test_gateway_strip_state_is_conversation_scoped_and_clearable` | **pass** | Sticky, scoped, clearable |
| Regression suite | `pytest tests/unit` | **pass** | **333 passed** |
| Lint | `ruff check` on changed files | **pass** | 5 pre-existing I001s only (same as baseline) |
| Task 2 (edit follow-up) | live | **fail — new minor finding** | 38.7 s but `status=error PARTIAL`: the agent found only one line in the document and honestly stopped instead of blindly appending ("If there was a specific first line… tell me its text"). Honest behavior, but the create-task's text and the edit's expectation mismatched (the agent may have written the doc with the line inside a different shape/paragraph, or lost it in the read-back). Not a regression of this fix (detection-skip worked); a candidate for a small follow-up lifecycle on edit-protocol verification |

## Output Excerpts

```
TASK 1 (fresh conversation, detection expected): 57.5s detection_in_report=True
TASK 2 (follow-on):  38.7s detection_in_report=False
TASK 3 (save+close):  42.4s detection_in_report=False
  STEP 1: save-and-close Word (batched, via direct channel) OK — attached…
  save+close class: 42.4s (the bug's turn: 109s)
pytest tests/unit → 333 passed
```

## Residual Risks

- The remaining ~40–60 s on office turns is the nested-LLM floor (Dify hop + gateway agent iterations) — the deterministic executor remains the last latency lever (three lifecycles point at it)
- The sticky flag is in-memory: one detection per conversation per sidecar restart — acceptable
- The task-2 edit-protocol confusion (single-line doc vs expected two) is a small new finding: honest ask-back, no data loss, but worth a mini-lifecycle if it recurs
- The upstream strip (#148459) persists; if it ever heals, the flag clears automatically (gateway-channel delivery observed → clear)

## Recommendation

**Close the bug — verified end-to-end.** The detection tax is structurally removed for follow-on tasks (proven live: zero detection steps in both follow-on turns), and the bug's own save+close class dropped from 109 s to 42.4 s. The remaining latency is the documented LLM floor, and the executor spec is the owner's call. The task-2 edit finding is noted for a potential small follow-up lifecycle, independent of this one.