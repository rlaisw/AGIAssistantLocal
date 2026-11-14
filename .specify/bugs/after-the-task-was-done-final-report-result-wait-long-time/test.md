# Bug Verification: the post-task wait is gone — a full browser task turn now ends in 14 s with zero loop rows

- **Slug**: after-the-task-was-done-final-report-result-wait-long-time
- **Tested**: 2026-11-14T06:10:00+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified — the original scenario replayed live end-to-end; the symptom no longer reproduces; the enforcement path proven in both directions

## Summary

A live replay of the exact scenario class (imperative browser search-and-report through the chatflow) completed **end-to-end in 14.0 s** — navigate + read executed, the final report included — with **exactly 2 audit rows and zero skill-loop rows** for the conversation. The bug's own measured turn (2026-11-14 05:36) had the same tool work done in 2.1 s and then ran `skill_search` 100 s later plus `skill_save` 61 s after that, with the answer arriving past 3 minutes. The loop rounds no longer occur — and where an agent attempts them anyway, the gate refuses with the honest skip envelope (proven live on the rebuilt sidecar in the fix phase, both refusals audited).

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix, live E2E) | chat replay "open chrome, go to bing, search for hong kong temperature today and tell me what it says" (conversation `09e5d91e…`) | **pass** | `browser-navigate-v2` (1.0 s) + `browser-read-v2` (0.5 s) executed; **2 audit rows total, zero skill-search/skill-save rows**; turn `message_end` **14.0 s** including the final report — vs the bug turn's 3+ minutes with the same tool work |
| Enforcement path (live) | direct MCP sequence on the rebuilt sidecar (fix phase, conversation `loop-gate-live-verify`): v2 op → `skill_search`/`skill_save` | **pass** | both loop tools returned the blocked skip envelope; both refusals audited `decision: blocked` with the reason intact |
| Non-v2 lanes unaffected | unit pins (`TestGateClassification`, `TestLoopToolsRefuse::test_loop_turns_keep_the_full_loop`) + the loop-class restore pin | **pass** | loop-lane ops restore the full working loop; neutral ops change nothing |
| New / updated tests | `pytest tests/unit/test_loop_gate.py` | **pass** | 9 passed |
| Regression suite | `pytest tests/unit` (full) | **pass** | 652 passed, 0 failed |
| Lint / type-check | `ruff check` (changed files) | **pass** | All checks passed |

## Output Excerpts

```
bug turn (05:36, pre-fix):   reads done 2.1s → skill_search +100s → skill_save +61s → answer 3+ min
E2E replay (post-fix):       navigate 1.0s → read 0.5s → message_end 14.0s | audit rows: exactly 2, no loop rows
enforcement (rebuilt sidecar): skill_search → {"status":"blocked","reason":"loop-exempt turn (v2 fast path)…"}
                              skill_save   → {"status":"blocked", …}  both audited decision: blocked
pytest tests/unit → 652 passed, 0 failed
```

## Residual Risks

- The remaining post-tool wait (relay round + answer node, the part-2 steering-model cost, ~60–100 s/round when the agent deliberates over the large lane instruction set) is the parked owner decision, unchanged by this lifecycle and recorded with fresh numbers in the assessment. This turn's 14 s shows it is not a floor on every turn — but heavy deliberation turns can still pay it.
- A first replay with a bare question phrasing ("search hong kong temperature today…") answered without any tools (General-lane routing, no audit rows) — the known classifier phrasing quirk, adjacent to the parked pre-router work; not this bug.
- The gate is process-local state: a sidecar restart clears the conversation map (harmless — the next op re-stamps the class; a stale refusal window is bounded by the same turn).
- One v2 turn in the fix phase predating the gate ran the loop; the gate only prevents loop *tool executions* — the agent's deliberation time around a *refused* call is still paid if it attempts the loop (the envelope tells it to proceed, bounding this to one round).

## Recommendation

**Close the bug — verified end-to-end on the real scenario.** The user's exact complaint class was replayed live: the task completes, and the final report now arrives in the same breath (14 s end-to-end vs 3+ minutes), with the enforcement proven in both the negative (loop refused + audited) and positive (clean turn, no loop attempts) directions. The steering-model decision remains open as the owner's parked call with this lifecycle's measurements attached.
