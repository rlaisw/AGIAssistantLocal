# Bug Verification: provider row 600 + restarts did NOT remove the ~300 s chat-side cut — the ceiling lives deeper

- **Slug**: `the-local-agent-hit-a-transport-error`
- **Tested**: 2026-11-09T01:45+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: **failed** — the symptom still reproduces with the fix fully applied; the assessment's root-cause attribution (the provider row) is disproven as the *operative* ceiling through the chat path

## Summary

Two behavioral samples through the chat — one before and one after a full `docker-plugin_daemon-1` restart, with the provider row verified at 600/600 and both api-1 and the daemon freshly restarted — **both hit the identical "peer closed connection / incomplete chunked read" at ~300 s of tool time**. The fix's configuration change is correct as far as it goes but is not the ceiling that cuts chat-side calls; the ~300 s limit lives in a component that does not read the provider row (most plausibly the plugin-daemon's tool-invocation RPC timeout or the agent plugin's invocation layer).

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Behavioral sample 1 (fix config live, api restarted) | chat turn "open control panel , show me network adapter configuration…" (01:01:12 → 01:06:22) | **fail** | `status=normal` but the answer relays the transport error: *"The local agent couldn't complete that — the connection to it dropped mid-request ('peer closed connection without sending complete message body')"* — the no-retry rule worked (honest relay, no stacking), but the cut still occurred at ~300 s of tool time |
| Provider row + restart verification | `SELECT timeout, sse_read_timeout` → **600/600**; api-1 healthy (Up 15 h) | **pass** (config) | The fix's changes were all in place and loaded |
| No natural traffic since the fix | messages query since 2026-11-08 10:05 | none | No user turns in the window — both samples were manufactured by this verification |
| Behavioral sample 2 (after **plugin-daemon restart** — the one component not restarted by the fix) | same request (01:07:08 → 01:12:30, daemon Up 25 s) | **fail** | Identical transport error at ~300 s of tool time — the daemon restart did not change the cut, ruling out a stale-cached row in the daemon |
| Component inventory (read-only) | plugin daemon cwd: only agent/ollama/openrouter plugins — **no MCP plugin**; the MCP client is native to the api | informative | The MCP connection (timeout=600 from the row) is made api-side; the tool *invocation* flows daemon↔api via RPC — the ~300 s cut is therefore in the invocation RPC layer (daemon Go constant or agent plugin), not the MCP connection config |
| Regression suite | `pytest tests/unit` | **pass** | 354 passed (no source changes; confirmation only) |

## Output Excerpts

```
sample 1 (row=600, api restarted):  "…connection to it dropped mid-request
  ('peer closed connection…')" — turn 310 s, cut at ~300 s tool time
sample 2 (daemon restarted too):     identical error — turn 322 s
row check: 600|600 | api-1 healthy | daemon Up 25 s at sample time
pytest tests/unit → 354 passed
```

## Residual Risks

- Every prior observation stands: the honesty stack (no-retry relay, honest envelope on direct calls, keep-alives) made both failures *truthful* — users get an accurate "connection dropped" message and a re-ask hint rather than a silent kill; the UX cost is a failed request, not a lie
- The eliminated candidates now number four: sidecar (direct calls sustain 540 s), provider row (600, loaded), api-1 (restarted), plugin daemon (restarted) — the ~300 s ceiling is in the daemon↔api tool-invocation RPC or the agent plugin's invocation layer, both untouched by any config knob found so far
- Two failed verification turns left no side effects (Control Panel may be open on the desktop from partial navigation — close at will)

## Recommendation

**Reopen the root cause: re-run `/speckit.bug.assess` with this evidence.** The assessment's mechanism (provider-row timeout as the operative chat-side ceiling) is disproven by the restart-controlled samples; the row change is still *correct* (it must sit above the envelope — keep it) but the actual hunt must move to the plugin-daemon's tool-invocation RPC timeout (a Go-side constant or env in `/app/main`, e.g. a per-invocation deadline around 300 s) and the agent plugin's invocation layer. The measurable signature for that hunt: a chat tool call dies at 300.000 s ± 10 s of tool time, invariant to every Dify-side config so far changed.