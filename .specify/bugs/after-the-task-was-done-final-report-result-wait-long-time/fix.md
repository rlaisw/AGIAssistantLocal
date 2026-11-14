# Bug Fix: structural v2 fast-path exemption — the skill loop now refuses after exempt ops

- **Slug**: after-the-task-was-done-final-report-result-wait-long-time
- **Fixed**: 2026-11-14T06:00:00+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — part 1 (structural exemption) live and verified; part 2 (lighter steering model) remains the owner's parked decision, now backed by this lifecycle's measurements

## Summary

The skill loop is now structurally exempt during v2 fast-path turns: the audit funnel classifies every operation per conversation, and while the conversation's last operational op was one of the seven exempt v2 tools, `skill_search` and `skill_save` answer with an honest skip envelope instead of executing — eliminating the measured ~60–100 s post-task loop rounds that made the final report wait minutes after seconds-long work. The published DSL rule stays as documentation; the gate, not the instruction, now holds.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/loop_gate.py` | added | conversation-scoped last-op classifier: the 7 exempt v2 ops set `exempt`; every other non-neutral operational op restores `loop`; skill-*/status/ask-back/control rows are neutral; `SKIP_REASON` is the shared honest envelope |
| `src/agentic_rag_mcp/hermes_audit.py` | modified | `write_attempt` — the single funnel all 42 lane call-sites audit through — records the classification; one hook covers every lane including future ones |
| `src/agentic_rag_mcp/skill_manager/api.py` | modified | `search`/`save` early-return the blocked skip envelope when the gate is active; `_timed` audits them as `decision: blocked` with the reason (observable, not silent) |
| `tests/unit/test_loop_gate.py` | added | 9 pins (below) |

## Diff Highlights (optional)

```python
# skill_manager/api.py — inside search._fn / save._fn
if exempt_active(cid):
    return {"status": "blocked", "found": False, "skills": [],   # search
            "reason": SKIP_REASON}

# hermes_audit.write_attempt — the funnel hook
_loop_gate_record(operation, conversation_id)
```

## Tests Added or Updated

- `test_loop_gate.py::TestGateClassification` — all 7 exempt ops mark the conversation; loop-lane ops (office-task, launch-app, run-command, browser-dynamic, browser-scripted-run, file ops) restore the loop; neutral ops change nothing; no-conversation rows classify nothing.
- `test_loop_gate.py::TestAuditFunnelIntegration` — a `browser-read-v2` audit row activates the gate for that conversation; an `office-task` row deactivates it.
- `test_loop_gate.py::TestLoopToolsRefuse` — search/save return the blocked skip envelope during an exempt turn (nothing read or written); the refusal is audited as `skill-search`/`skill-save` with `decision: blocked`; loop turns keep the full working loop.

## Local Verification

- Commands run: `pytest tests/unit/test_loop_gate.py` → **9 passed**; full `pytest tests/unit` → **652 passed, 0 failed** (up from 643 — the 9 new pins; zero regressions); `ruff check` on changed files → clean.
- Sidecar: `deploy redeploy` → rebuilt, health ok, tools 53/53 (no tool-count change).
- **Live E2E on the rebuilt sidecar** (conversation `loop-gate-live-verify`): `browser_read_v2` → ok (marks the conversation exempt) → `skill_search` → **blocked with the skip envelope** → `skill_save` → **blocked with the skip envelope**; both refusals audited (`decision: blocked`, reason intact). The agent now receives the structural answer in the tool result and proceeds straight to the report.

## Deviations from Assessment

None for part 1 — applied as proposed (conversation-scoped classification, advisory-refusal envelopes, audit visibility, unit pins). Part 2 (the lighter steering model for the `hermes_agent` node) is the owner's parked decision by the assessment's own framing; today's measured round costs (~60–100 s vs the 11.3 s General-path baseline) are the standing evidence for it, recorded in the assessment.

## Follow-ups

- The next natural v2 task turn in the chat UI is the behavioral confirmation: the post-task wait should drop by the two refused rounds (~100–160 s measured); the remaining wait is the relay + answer rounds, whose floor is the steering-model decision.
- Owner decision pending: lighter steering model for the Hermes lane node (part 2) — with the loop rounds now structurally gone, its remaining benefit is the relay/answer rounds.
- Long-run watch: `skill-search`/`skill-save` rows with `decision: blocked` + `loop-exempt` are the gate working; a rise in such rows on *non*-v2 tasks would indicate misclassification (none expected — classification is op-name-exact).
