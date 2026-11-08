# Bug Verification: No-retry-on-transport-error — forced reproduction proves the agent relays honestly instead of re-invoking

- **Slug**: `it-is-a-transport-failure-let-me-try-again-once-since-it-may-be-transient`
- **Tested**: 2026-11-08T09:25+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original symptom — the agent retrying a transport-failed tool call within the same turn and the cumulative time killing the run silently (no verdict, no audit) — no longer reproduces: a **forced reproduction** (killing the sidecar mid-tool-call through a fresh chat turn) produced the textbook post-fix behavior: the agent quoted the no-retry rule in its reasoning, relayed the failure honestly with the recovery hint, did **not** re-invoke, and the turn completed `normal` in ~35 s instead of dying at ~600 s mid-retry.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) — **forced transport failure** | fresh chat turn ("open notepad and type the quick brown fox"); sidecar container restarted at +32 s mid-tool-call (in-flight stream killed — the exact "peer closed connection" class) | **pass** | Turn 09:19:23 → 09:19:58, `status=normal`, answer honest: *"the launch request didn't make it through — the connection to the local agent dropped mid-response ('peer closed connection without sending complete message body')… I won't automatically retry… just ask me again"*; the agent's reasoning explicitly cites the rule: *"Per my instructions, I must NOT retry the same tool within this turn… relay the failure honestly and let the user re-ask"* — **no second attempt**, no silent kill, cumulative-window escape closed |
| Pre-fix contrast | the 09:00:31 natural turn (evidence from the assessment) | documented | Same transport-error trigger → the agent retried → run killed at 603.3 s, empty answer, no audit. The forced run's 35 s honest relay is the behavioral delta |
| Live-graph assertion | `graph::text LIKE '%do NOT retry the same tool%'` on the current published version | **pass** | true; repo artifact synced (grep count 1) |
| Regression suite | `pytest tests/unit` | **pass** | **354 passed** |
| Lint | n/a (prompt-only change; no source files touched by this fix) | **not-run** | No code changed — nothing to lint beyond the suite run |

## Output Excerpts

```
forced kill at +32s (mid-tool-call) → turn completes at +35s, status=normal:
  "…the connection to the local agent dropped mid-response ('peer closed
  connection without sending complete message body')… I won't automatically
  retry… just ask me again."
  reasoning: "Per my instructions, I must NOT retry the same tool within
  this turn … relay the failure honestly and let the user re-ask."
graph LIKE '%do NOT retry the same tool%' → t | pytest → 354 passed
```

## Residual Risks

- The no-retry rule is prompt-level: today's forced test shows the model (kimi-k3) obeying it verbatim; adherence across future contexts is expected but not guaranteed — a natural-turn violation would surface as a killed run again, and the audit/graph checks would confirm whether the rule was still live
- Transport blips now surface honestly in chat — which makes any *persistent* underlying blip diagnosable for the first time; if the same error text recurs frequently, it graduates to its own root-cause lifecycle (the fix creates the observability)
- The forced test killed one in-flight sidecar call (by design); the container auto-restarted and the stateless streamable transport reconnected on the next call — no cleanup needed

## Recommendation

**Close the bug — verified end-to-end with a forced reproduction.** The agent demonstrably does not retry transport-failed tool calls, relays the honest error with the user-facing recovery hint, and the turn that previously died silently at ~600 s now completes in under a minute with a truthful verdict. All static and behavioral checks hold.