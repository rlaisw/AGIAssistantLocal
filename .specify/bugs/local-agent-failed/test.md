# Bug Verification: "The local agent failed" — bounded attach marathon

- **Slug**: `local-agent-failed`
- **Tested**: 2026-11-05T08:22+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified (fix scope) — with two new findings routed to sibling lifecycles

## Summary

The fix's contract — attach-failure turns stay bounded — was **exercised live and held**: on a COM-broken Outlook, the turn did one fast `GetActiveObject`, one `Dispatch`, then stopped honestly, finishing in seconds (previously this exact state produced 600 s+ marathon turns and a gateway death). The assessment's original symptom (a strip-windowed email turn ending in "local agent failed") did not reproduce post-fix: the 08:15:42 email compose completed end-to-end — fresh Outlook launched, attached, the "hello test v3" draft composed into Drafts and verified by EntryID.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction: strip-windowed email turn | live compose at 08:15:42 (fix phase) + compose/cancel cycle at 08:20:10 (test phase) | **pass** | 08:15:42: `status ok, draft_pending True` — draft composed, EntryID-verified (via the direct-SSE fallback around the still-stripped gateway). 08:20:10: bounded attach exercised on a re-broken Outlook — fast honest failure, no marathon |
| Bounded attach (the fix) behavior | the 08:20:10 compose turn | **pass** | STEP 2 GetActiveObject (fast) → STEP 3 ONE Dispatch → STOP — the whole turn finished in seconds with honest COM errors; under the pre-fix instructions this state ran 600 s+ |
| Cancel flow | `cancel that email` | **pass** | `status ok, draft_pending False` — pending state resolved, "the pending email was not sent" |
| New / updated tests | `pytest tests/unit/test_hermes_office_tool.py` | **pass** | 17 passed incl. the bounded-attach guard |
| Regression suite | `pytest tests/unit` | **pass** | 332 passed |
| Lint | `ruff check src/agentic_rag_mcp/hermes_client.py` | **pass** | clean |

## Output Excerpts

```
08:15:42 (reproduction passes): STEP 5: Compose draft OK — new item created
  with To "raymond.lai@tvb.com.hk", Subject "hello test v3", Body "test abc v3"
  verbatim, saved into Drafts. Never sent. → status ok, draft_pending True
08:20:10 (bounded attach live): STEP 2 GetActiveObject FAILED (0x800401E3);
  STEP 3 Dispatch FAILED (0x80080005) → turn over in seconds (was 600 s+)
08:20:10 cancel: cancelled — the pending email was not sent → ok
pytest tests/unit → 332 passed
```

## Residual Risks

- **New finding (→ `only-one-version-of-outlook` lifecycle)**: the Outlook instance freshly launched by the 08:15 compose (DCOM Dispatch from OfficeMCP) **lost its ROT registration within ~5 minutes** — the COM-unreachable state recurred on a clean instance, not just the original broken one. DCOM-launched Outlooks may be inherently unreliable for later attach in this setup; each new compose may need to launch-or-attach in the same turn (which the direct-SSE path can do).
- **New small finding (→ future fix)**: the tool envelope reported `draft_pending: true` for a **failed** compose (server.py sets pending state on compose-shaped tasks before/regardless of success) — a minor honesty gap; the cancel path still resolved it cleanly.
- The gateway argument-strip (#148459) is still present and the direct-SSE fallback that saves turns is the agent's own improvisation, not yet official instructions — the recommended next cycle (see fix.md follow-ups) is to promote it.
- The "send it" flow was not exercised by this verification — sending a real email requires the owner's explicit intent; the user's "hello test v3" draft remains pending in Drafts for exactly that.

## Recommendation

**Close this bug — verified in scope.** The bounded attach is behaviorally proven (seconds, not minutes), the reproduction's symptom did not recur, and all suites pass. Route the two new findings where they belong: the DCOM-launched-Outlook ROT loss to the `only-one-version-of-outlook` lifecycle, the failed-compose `draft_pending` gap to a small future fix, and the direct-SSE fallback promotion to the recommended re-assessment of the strip model.
