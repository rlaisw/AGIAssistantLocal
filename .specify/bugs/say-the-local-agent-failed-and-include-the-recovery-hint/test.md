# Bug Verification: burst-retry rule — refuted as causation, vindicated as persistence

- **Slug**: `say-the-local-agent-failed-and-include-the-recovery-hint`
- **Tested**: 2026-11-05T09:22+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

The live verification split exactly down the middle and that is the honest result: one run (09:16) fired the full 15 canaries with zero deliveries — refuting "the burst flips the channel" as causation — and one run minutes later (09:20) survived **11 stripped calls** (a guaranteed failure under the old 3-canary cap), reached a healthy phase, attached to the running Outlook, and **composed the draft** (`status ok, draft_pending True`). The raised cap does not control the upstream oscillation, but it demonstrably converts the channel's recurring healthy phases into completed tasks instead of early give-ups.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix), run 1 | live email task, 09:16 | **fail (hypothesis)** | 15 consecutive canaries, 0 delivered — honest error fired with the new retry-based text; no flip |
| Reproduction (post-fix), run 2 | live email task, 09:20 | **pass (behavior)** | 11 stripped calls persisted through (old cap = certain failure), then 9 delivered; Outlook attached (running instance — the ROT loss also recovered); draft composed, `draft_pending True` |
| New / updated tests | `pytest tests/unit/test_hermes_office_tool.py tests/unit/test_office_gate.py` | **pass** | 49 passed, incl. the 15-cap guard and the absent falsified wait text |
| Regression suite | `pytest tests/unit` | **pass** | 332 passed |
| Lint / type-check | `ruff check src/agentic_rag_mcp/hermes_client.py` | **pass** | clean |

## Output Excerpts

```
09:16 run:  args log — stripped: 15, delivered: 0
            → TASK: FAILED — OfficeMCP channel degraded (argument strip);
              recovery: ask again — retrying the request flips the channel
              back; do NOT restart…
09:20 run:  args log — stripped: 11, delivered: 9
            STEP 2: channel check OK (after persistence) · STEP 3: Outlook
            attach OK (running instance) → status ok, draft_pending True
pytest tests/unit → 332 passed
```

## Residual Risks

- The recovery is **probabilistic**: the upstream strip oscillates on its own schedule (healthy phases recur within minutes, but a turn that stays inside a stripped phase still fails honestly after 15 canaries). The causal wording in the deployed rule ("the burst itself flips the channel back") remains unproven and should be softened in the next cycle.
- The user now has **two copies** of the "hello test v3" draft in Outlook's Drafts (one from 08:15, one from this verification's probe) — delete one; the pending-draft state lives in probe conversations, not the user's chat conversation, so "send it" from the user's chat will locate a draft by content.
- The durable fix is unchanged: the gateway-independent executor via a WSL-side relay (container → OfficeMCP is currently unreachable; see fix.md follow-ups) — the only design that removes the upstream dependency (#148459) entirely.
- Outlook's COM state also oscillated today (unattachable at 08:20, attachable at 09:20) — same class of Windows-side intermittency, tracked by the `only-one-version` lifecycle.

## Recommendation

**Hold as partial — with the practical outcome recorded.** The wrong "wait 15 minutes" advice is gone, the raised cap has a live-verified success that was impossible under the old cap, and the honest 15-canary backstop works when the phase doesn't turn. This is usable reliability, not a cure. The next high-value cycle is the re-assessment for the **gateway-independent office executor** (relay + direct OfficeMCP), which ends the oscillation dependence; soften the causal rule wording in the same pass.
