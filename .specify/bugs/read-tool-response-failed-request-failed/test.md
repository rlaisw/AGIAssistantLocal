# Bug Verification: async tools + live SSE keep-alive — a 188 s turn survives the old 129 s cut boundary

- **Slug**: `read-tool-response-failed-request-failed`
- **Tested**: 2026-11-06T06:50+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original symptom — a tool-response stream cut with "incomplete chunked read" on any turn longer than ~120 s while the work completes server-side — no longer reproduces: a forced **188.5-second** office turn (past both the 129 s and 224 s cut incidents) completed with `status=ok` over the same stream, with **12 SSE keep-alive pings** observed flowing every 15 s throughout. The mechanism fix (async tools freeing the event loop so the SDK's keep-alive writer runs) is confirmed at the transport level.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) — past the old boundary | live HTTP office task with a forced 115 s RunPython sleep (total turn 188.5 s), raw stream dump | **pass** | 12 `: ping` keep-alives at exact 15 s intervals (15→180 s); `RESULT: status=ok` delivered on the same stream at 188.5 s. Pre-fix, this exact turn shape was cut mid-body (129 s and 224 s incidents) |
| Reproduction corroboration (fix phase) | 166 s forced-sleep turn + 65/75/40 s sleep turns + natural 33 s PPT task | **pass** | All completed `status=ok` on the same stream; the 15 s ping cadence visible in raw dumps from the first |
| Keep-alive mechanism | raw `: ping - <timestamp>` comments observed at 15.0/30.0/…/180.0 s | **pass** | The SDK's keep-alive writer — frozen by the old sync tools — now runs continuously during tool computation |
| New / updated tests | `pytest tests/unit` | **pass** | 332 passed, incl. the STRIP MEMORY / INTERRUPTED-TURN PROTOCOL / folded-env-check guards |
| Lint | `ruff check` on the changed files | **pass (no new findings)** | 5 pre-existing I001 import-sort findings unchanged from baseline; the intentional keep-alive `except: pass` silenced with noqa |

## Output Excerpts

```
[ 15.0s] SSE keep-alive ping #1   …   [180.0s] SSE keep-alive ping #12
[188.5s] RESULT: status=ok
pytest tests/unit → 332 passed
```

## Residual Risks

- The upstream strip (hermes-agent #148459) persists — the direct channel carries most turns; orthogonal to this fix and already routed around deterministically
- The `ctx.report_progress` belt-and-suspenders frames are unnecessary for the fix (the `: ping` keep-alives suffice); they may be simplified away after a soak period
- A hypothetical *total-duration* client cap (distinct from the idle-read mechanism this fix removes) can no longer be observed as long as natural turns stay under a few minutes; the Dify provider `timeout=300` is now loaded, and the sidecar's 600 s Hermes budget remains the honest backstop
- The `directive_ctx` rename fixed a latent shadowing bug; similar collisions elsewhere would surface the same way (as warning logs) — none observed

## Recommendation

**Close the bug — verified end-to-end at the transport level.** The reproduction crossed both prior cut incidents with the result delivered intact; the mechanism (event-loop starvation of the keep-alive writer) is directly observed fixed via the ping cadence. Natural turns now carry a live stream regardless of duration. No further cycle needed for this class.
