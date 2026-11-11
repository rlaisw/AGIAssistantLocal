# Bug Fix: Dynamic browsing slow — tiers 1+2 applied, wall-time blocked by a persistent gateway arg-strip

- **Slug**: browsing-is-working-but-very-slow
- **Fixed**: 2026-11-11T12:10:55Z
- **Assessment**: ./assessment.md
- **Status**: partial (workload tier applied and proven; wall-time blocked by a newly-persistent upstream issue — see Deviations)

## Summary

The efficiency instructions (direct-URL navigation, one-snapshot reads) and the ad/analytics origin blocking are applied and rebuild-deployed — the workload metric proves the tier (2004 → 251 events, an 8× reduction). But live re-timing showed the **dominant wall-time factor today is the Hermes gateway arg-strip, now persistent across fresh sessions**, forcing the expensive direct-channel recovery path (59.5s and 250.6s runs), and a recovery session left the **browser profile locked** for the next turn.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | `BROWSER_DYNAMIC_INSTRUCTIONS`: WORK FAST block (direct-URL when derivable, ONE snapshot, no micro-action snapshots, 2–3 calls per read task) + profile-release hygiene (close the browser when done — a locked profile breaks every later browsing task) |
| `playwright-mcp-server` task (host, cmdlet-registered) | rebuilt | `--blocked-origins` for doubleclick, googlesyndication, google-analytics, googletagmanager, facebook.net, adservice.google.com, analytics.google.com |

## Local Verification

- **Workload (proven)**: 12:07 baseline 2004 events/44.5s → post-fix run **251 events/59.5s** — the event volume dropped 8×; the run's duration was dominated by the arg-strip recovery it had to perform.
- **Wall-time (blocked)**: second fresh-session run hit the strip again AND a profile lock left by the prior recovery session → 250.6s. The strip appeared in **both fresh conversations** today — a state change from the previously intermittent behavior.
- Suites: 562 unit green; sidecar rebuilt (40 tools); `:3002` live with blocked origins.

## Deviations from Assessment

**Stop-and-document per the fix rules**: the assessment attributed the slowness primarily to the LLM-workload profile with the arg-strip as a known class. The live re-timing shows the strip has become **persistent across sessions** (both test conversations), making it the dominant wall-time factor — recovery via raw-SSE-over-curl is inherently slow (~40–200s) and its sessions leak profile locks. The efficiency tier cannot deliver wall-time while the strip persists. **Recommend a fresh `/speckit.bug.assess` for the arg-strip persistence** (slug suggestion: `gateway-arg-strip-persistent`) — it is an upstream Hermes gateway issue (the "arg-strip stickiness" class in the house records), where the durable fix lives beyond this repo (upstream gateway patch), with the profile-release hygiene (applied here) as the local mitigation.

## Tests Added or Updated

None new (prompt text + task args); the existing 562 stay green. Verification is the audit timing rows, recorded above.

## Follow-ups

- **New lifecycle needed**: `gateway-arg-strip-persistent` — the strip now hits every fresh session; upstream fix or a lighter persistent direct channel.
- Tier 3 (scripted-first routing + the deterministic executor, ~10–20s) remains the structural endgame — the arg-strip issue makes it MORE attractive since the scripted lane does not ride the gateway's MCP arg path at all.
- Watch for the profile-lock class: the hygiene line should clear it; if a lock recurs, the recovery must also kill leaked chromium processes.