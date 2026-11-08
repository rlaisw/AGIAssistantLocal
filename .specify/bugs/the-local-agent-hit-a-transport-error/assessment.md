# Bug Assessment: Dify's MCP provider timeout (300 s) is the real chat-side ceiling — below the sidecar's honest 540 s envelope

- **Slug**: `the-local-agent-hit-a-transport-error`
- **Created**: 2026-11-08T10:00+00:00
- **Source**: pasted text (the agent's honest relay: "The local agent hit a transport error… 'peer closed connection without sending complete message body'") + live investigation
- **Verdict**: valid — and the pasted text itself is the previous fix (`it-is-a-transport-failure-…`) **working exactly as designed**: no retry, honest relay. The bug is the *underlying* connection drop, now fully explained.
- **Severity**: medium — every chat-side `hermes_*` tool call is silently cut at 300 s; the honest envelope (540 s) only protects direct sidecar calls, so long desktop turns through the chat fail as "transport errors" and users must re-ask

## Report (verbatim or summarized)

> "The local agent hit a transport error while handling that — the connection dropped before it could report back ('peer closed connection without sending complete message body')"

The 09:47:11 chat turn ("open control panel , display wallpaper setting"): the agent passed the full task to `hermes_launch_app` (desktop followups working), the sidecar opened the streaming response at 09:47:17, and the session terminated at **exactly 09:52:17 — 300 s later**. The no-retry rule fired: the agent relayed honestly ("I won't retry within this turn… Just ask me again"), the turn completed `normal` at 09:52:20.

## Symptom

Chat-side tool calls are cut at exactly 300 seconds with a transport error, regardless of the sidecar's 540-second honest envelope. Expected: chat turns enjoy the same ~540 s envelope as direct calls, ending in either success or the sidecar's honest verdict — never a connection drop.

## Reproduction (measured, 2026-11-08 UTC)

1. 09:47:17 — sidecar receives the tool call (`POST /mcp 200`, streaming response opens; sidecar log)
2. 09:52:17 — **exactly 300 s later** — `mcp.server.streamable_http Terminating session` (the stream dies); no audit verdict for the turn (the launch task was killed mid-flight)
3. 09:52:20 — the turn completes with the honest transport-error relay (the previous fix working)
4. **The 300 is the Dify MCP provider client's timeout**: `tool_mcp_providers.timeout = 300` for `agentic-rag` (raised 30 → 300 on 2026-11-06 per the `close-excel-wait-long-time` note — the correct knob, wrong value for this architecture). The sidecar budgets 540 s; the chat-side client cuts at 300 s — the envelope never gets to fire through the chat
5. **Retroactive explanation** of the `it-is-a-transport-failure-…` turn (09:00:31): attempt 1 died at the 300 s provider timeout (the "transport failure" in the agent's reasoning), the retry ran until the daemon's ~600 s workflow kill (603.3 s) — two ceilings stacking, both now identified

## Suspected Code Paths

- Dify DB row `tool_mcp_providers` (`agentic-rag`): `timeout = 300` — the MCP client's per-request read ceiling; loaded by `docker-api-1` at start (the DEPLOY.md note documents re-application after provider re-syncs)
- `src/agentic_rag_mcp/server.py` — the 540 s launch-lane envelope (working as designed; unreachable through the chat until the provider timeout exceeds it)
- No sidecar code defect — the previous fixes (async tools + keep-alives, 540 envelope, no-retry rule) all performed correctly; the misconfiguration is above them

## Root Cause Hypothesis

**High confidence.** The Dify-side MCP client enforces a 300-second per-request timeout (the provider row I configured on 11-06, chosen before the desktop-followup architecture made 8–10-minute turns legitimate). Any chat-side `hermes_*` call whose work exceeds 300 s — long desktop navigation under consent waits, big office turns — has its stream cut by the *client*, surfacing as "peer closed connection without sending complete message body". The sidecar's honest 540 s envelope only bounds direct calls; through the chat, the 300 s ceiling fires first. The three-layer honesty stack (envelope, keep-alives, no-retry) means these cuts now always end in truthful relays instead of silent kills — the failure is honest but still a failure.

## Proposed Remediation

**Preferred**: raise the provider row's `timeout` from 300 to **600** (`UPDATE tool_mcp_providers SET timeout = 600 WHERE name = 'agentic-rag'`) and restart `docker-api-1` to load it. With the client ceiling (600) above the sidecar's honest envelope (540), chat-side turns now end exactly like direct calls: success or the truthful "Hermes did not finish within 540s" verdict — the envelope becomes the binding, honest bound end-to-end. Update the DEPLOY.md note (30 → 600 with the why) so future re-syncs re-apply the right value.

**Alternatives**:
- Lower the sidecar envelope to ~270 s to fit under the 300 s client ceiling — rejected: shrinks the legitimate turn window everywhere (including direct/battery calls) to protect a misconfigured client
- Set both to identical values — rejected: the envelope must sit strictly *below* every external ceiling so the honest verdict always wins the race

**Files likely to change**:
- Dify DB row `tool_mcp_providers` (live config) + `docker-api-1` restart
- `DEPLOY.md` — the provider-timeout note (value + rationale)
- No sidecar source changes

**Tests to add or update**:
- Live: after the change, a chat-side turn that exceeds 300 s must no longer produce "peer closed connection" — either it completes or ends with the sidecar's honest 540 s verdict (a long navigation request is the natural probe)
- The provider-row check joins `reboot.sh`'s scope question (see Risks) — at minimum, DEPLOY.md documents the re-apply command

## Risks & Considerations

- The provider row is not in git (live Dify config) — the DEPLOY.md note is the persistence mechanism; provider re-syncs (`sync-tools`) may reset it and need re-application + api restart
- A 600 s client ceiling with a 540 s envelope leaves 60 s of slack for the verdict to travel — adequate; the daemon's ~600 s workflow window still bounds the whole turn (attempt + relay), which the no-retry rule keeps to a single attempt
- `docker-api-1` restart briefly interrupts the chat (seconds) — schedule it between user turns
- Office/file lanes inherit the same fix (their calls also ran under the 300 s ceiling) — office turns that take 300–540 s (observed: 300–400 s routinely) were silently exposed to the same cut; this fix protects them too

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the 300 s → 600 s raise matches the measured architecture; the value should be revisited only if the envelope changes]
