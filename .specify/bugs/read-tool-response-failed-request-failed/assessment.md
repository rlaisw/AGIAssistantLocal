# Bug Assessment: 224 s PPT turn cut by the unlocated ~120 s deadline — the instrumentation deferred in close-excel-wait-long-time is now mandatory

- **Slug**: `read-tool-response-failed-request-failed`
- **Created**: 2026-11-06T06:05+00:00
- **Source**: pasted text (chat transcript of the PowerPoint request + the transport error + the recovery)
- **Verdict**: valid — recurrence of the `close-excel-wait-long-time` boundary; the prior fix's own follow-up trigger has fired
- **Severity**: medium — every office turn above ~120 s gets its response stream cut (user sees an error while the work completes server-side), then a retry doubles the wait; cold-app tasks legitimately exceed the boundary

## Report (verbatim or summarized)

> "The tool returned an error: 'read tool response failed: request failed: Failed to invoke tool: Error during cleanup: peer closed connection without sending complete message body (incomplete chunked read)'"

The user asked for a PowerPoint file (`ppt-2026-11-06 ver1.pptx`, text "hello world 2026 11 06"). Attempt 1 completed the work server-side but its response stream was cut; the agent then checked the directory with `hermes_file_task`, found the file + `~$` lock, retried, verified the text was already present (nothing duplicated), re-verified from disk, and reported success. Total visible time ≈ 6 minutes.

## Symptom

Office turns longer than ~120 s have their tool-response stream cut mid-body — the user sees a transport error while the sidecar has actually finished the work honestly. Expected: one turn, one answer.

## Reproduction (measured, 2026-11-06 UTC)

1. 05:54:54 — the user's message
2. 05:58:38 — attempt 1 completes server-side in **224 s** (batched script: PowerPoint cold-launch, one slide with the text, save, in-app read-back "slide 1 shape text = 'hello world 2026 11 06'", 32,412 bytes on disk, visible-state rule followed) — the response stream was already dead by then; the Dify side reported the incomplete-chunked-read
3. 05:59:11 — the agent's smart recovery: `hermes_file_task` directory check → file + `~$` lock present
4. 06:00:14 — retry: attach, open, **verify the text ALREADY present** (nothing added — no duplication), save, close+re-open from disk (32,416 bytes)
5. 06:01:03 — done. User-visible total: **6 min 9 s**
6. Boundary data across both days: 50 s ✓ · 56 s ✓ · 66 s ✓ · **129 s ✗ · 224 s ✗** — the cut boundary sits between ~66 s and ~129 s (prior fix's hunt through Dify core, plugin daemon, mcp SDK, and DB rows found no constant; the instrumentation was explicitly deferred as the next step)

## Suspected Code Paths

- The unpinned ~120 s deadline — `close-excel-wait-long-time/fix.md` Deviations documents the full hunt (agent strategy, mcp SDK session idle = 1800 s, plugin-daemon env, api env, MCP provider row 30→300/300). This turn proves the raised provider timeout did **not** move the boundary
- The sidecar has no disconnect observability: when the stream dies mid-turn, nothing on our side timestamps the close or names the closer — the exact instrumentation gap the prior fix deferred
- Turn duration drivers: ~3–4 LLM agent hops (kimi-k3 with the now-large instruction set, ~30 s each) + channel detection (gateway stripped → 2 canaries + direct-SSE setup) + PowerPoint cold start + COM work ≈ 224 s for cold-app tasks — a legitimate floor near the boundary even with perfect batching

## Root Cause Hypothesis

**High confidence on the behavior, low on the location (unchanged).** A read deadline between 66 s and 129 s cuts the MCP tool-response stream; the work completes server-side regardless. The new 224 s data point confirms the deadline is not the provider-row timeout (raised 30→300 with no effect) and not total-duration-independent. The closer is one of: the Dify agent plugin's tool invoke wrapper, the plugin-daemon RPC, or a proxy layer — unidentifiable without timestamped disconnect evidence, which only sidecar-side instrumentation can produce.

## Proposed Remediation

**Preferred**: the deferred instrumentation, then the boundary fix. (1) Add sidecar disconnect logging: a uvicorn/FastMCP hook (or an access-log line on `disconnect`) that timestamps every mid-stream response close with the tool name, turn age, and which side closed — after one more >129 s natural turn, the closer is identified and the constant patched at its source. (2) With the closer known, raise the deadline to ~300 s (below the sidecar's 600 s Hermes budget). (3) Cheap time-shaving meanwhile: fold the "Environment check" pre-step into the combined script (one fewer LLM hop, ~30 s), and skip gateway canaries when a previous step in the same task already found the strip (the direct channel is the operating mode all day — the detection cost is pure overhead in stripped periods).

**Alternatives**:
- Progress keep-alives from the sidecar's streamable-HTTP response (periodic bytes during tool execution to reset any per-read deadline) — mechanism exists in the mcp SDK? unverified; only if the instrumentation shows a per-read (not total) deadline
- Cap the sidecar's Hermes budget at ~110 s and fail honestly below the boundary — rejected: converts slow-but-successful turns into failures

**Files likely to change**:
- `src/agentic_rag_mcp/server.py` (or the FastMCP app wiring in it) — disconnect instrumentation
- `src/agentic_rag_mcp/hermes_client.py` — environment-check folding + strip-memory rule
- `tests/unit/test_hermes_office_tool.py` — guards for the folded-check rule

**Tests to add or update**:
- Guard: "skip further gateway canaries once the strip is found in the same task"; environment check folded into the combined script

## Risks & Considerations

- The instrumentation itself must be cheap and always-on (an access-log-level line, not per-chunk logging)
- Patching the deadline at its source (once found) adds local drift in a Dify-owned component — record in DEPLOY.md like the other local patches
- The agent's recovery flow this turn (file-check before retry, verify-before-add) should be preserved as-is — it prevented a duplicate and is the model for interrupted-turn handling; consider codifying it in the lane instructions as a bonus
- 224 s includes a legitimate PowerPoint cold start — the time-shaving rules reduce but cannot eliminate boundary crossings; the deadline fix is the real closure

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the instrumentation is justified by two cut turns with different durations (129 s, 224 s) and its output directly answers the location question]
