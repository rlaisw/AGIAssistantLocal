# Bug Verification: STEP BATCHING — works, adherence is probabilistic (41 s and 63 s vs 84–89 s baseline)

- **Slug**: `a-little-bit-slow-to-create-email`
- **Tested**: 2026-11-06T01:10+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

The batching rule demonstrably speeds up turns — both post-fix live composes completed far under the 84–89 s pre-fix baseline — but adherence varies by turn: yesterday's stripped-channel compose batched perfectly (2 steps, **41 s**), while this morning's (after 17 idle hours, also stripped) ran 6 loosely-batched steps (**63 s**, including a 5-canary detection where the rule says 2). The flow is robust and every turn now completes; the latency win is real but not uniform, because the fix is instruction-level and model adherence is probabilistic.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction, run 1 (yesterday, fix phase) | timed live compose, stripped channel, 10:03 | **pass** | 2 steps (detect → combined compose+verify), **41 s** vs 84–89 s baseline |
| Reproduction, run 2 (this morning) | timed live compose after 17 h idle, stripped channel, 01:09 | **pass, with adherence caveat** | 6 steps: the agent burned 5 canaries (rule says 2) and split attach/compose/read-back into three steps instead of one combined script → **63 s**; still `status ok, draft_pending True`, direct-channel recovery, full audit trail |
| New / updated tests | `pytest tests/unit/test_hermes_office_tool.py tests/unit/test_office_gate.py` | **pass** | 49 passed — the batching rule is instruction-pinned |
| Regression suite | `pytest tests/unit` | **pass** | 332 passed |
| Lint | `ruff check src/agentic_rag_mcp/hermes_client.py` | **pass** | clean |

## Output Excerpts

```
run 1 (10:03): STEP 2: Compose + verify OK (via direct channel) … 41 s
run 2 (01:09): STEP 1 running-apps · STEP 2 channel check FAILED (5 echoes)
  · STEP 3 direct-channel init · STEP 4 attach · STEP 5 compose · STEP 6
  read-back (via direct channel) → status ok, draft_pending True — 63 s
pytest tests/unit → 332 passed
```

## Residual Risks

- **Adherence variance is the ceiling of this fix**: the rule is instructions to an LLM — some turns batch tightly (41 s), some don't (63 s). The guard test pins the instruction's presence, not the model's compliance.
- The detection budget was also exceeded once (5 canaries vs the rule's 2) — same adherence class.
- Both residual LLM layers (Dify agent + gateway agent) remain; the wall-clock user experience is ~1–2 min from send to answer depending on adherence.
- Uniform latency requires the **deterministic sidecar executor** (no LLM in the mechanical loop, ~10–20 s guaranteed) — the standing architectural follow-up from the assessment.
- Another verification draft ("morning-speed-verify") is in the Drafts folder — delete unwanted copies.

## Recommendation

**Hold as partial — the fix is working, its ceiling is known.** Both reproduction runs beat the baseline substantially and every turn now completes through any channel phase (the direct-channel recovery carried both). If the variance matters to the owner, the next step is not another prompt tweak — it is the deterministic executor follow-up, which makes the speed structural instead of probabilistic. Re-verify casually on the next natural email turns; no further formal cycle needed for this bug.
