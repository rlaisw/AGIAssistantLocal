# Bug Assessment: Outlook compose — transport timeout on a long multi-step turn (NOT a "two instances" issue)

- **Slug**: `cannot-open-two-instances-of-outlook`
- **Created**: 2026-11-04
- **Source**: pasted text (chat transcript from the deployed Chat UI)
- **Verdict**: valid — but the **title misidentifies the cause**: the failure was a Dify→sidecar transport timeout on a long turn, not a "two instances of Outlook" conflict
- **Severity**: medium — a specific email request was blocked; the agent's behavior was exemplary (detected the upstream MCP degradation, switched to a fallback, but the long turn exceeded the Dify-side timeout)

## Report (verbatim or summarized)

The user asked to compose an email (body "Hello test", subject "Hello test ai", to raymond.lai@tvb.com.hk). The chat agent called `hermes_office_task`; the call returned: *"tool invoke error: read tool response failed: request failed: Failed to invoke tool: Error during cleanup: peer closed connection without sending complete message body (incomplete chunked read)"*. The agent — correctly — did **not** auto-retry (to avoid duplicate drafts) and reported the failure honestly. The user titled the bug "cannot open two instances of Outlook" but the transcript and audit show no such conflict occurred.

## Symptom

An email-compose chat turn failed with a **transport-level error**: the sidecar's response stream to Dify closed mid-turn ("peer closed connection without sending complete message body"). Expected: the tool returns a complete verdict (ok/blocked/error). The user interpreted the failure as an Outlook two-instance conflict, but the audit trail shows Outlook was **not running** at all — the agent started it fresh via COM Dispatch.

## Reproduction

The audit trail (2026-11-04 03:32 UTC) reveals the actual chain:

1. **STEP 1** — the agent detected the known upstream MCP args-dropping ("deferred gateway calls to OfficeMCP arrived stripped; canary echoed default twice") and **switched to a direct-SSE fallback** — a new, resourceful behavior not seen in earlier transcripts
2. **STEP 2** — RunningApps check: only Excel running; **Outlook was not running** (the user likely closed it since yesterday's session), so the agent needed to Dispatch Outlook via COM to start it
3. **STEP 3** — (inferred: the agent launched Outlook and composed the draft via the direct-SSE path — the step completed or partially completed before the failure)
4. **STEP 4** — Verification probe: **FAILED — "blocked by the terminal consent gate (timed out without user response; command never ran)"** — the agent tried to verify the draft via a terminal command, hit the gateway's consent gate, and waited until it timed out
5. The accumulated turn time (MCP degradation detection + Outlook Dispatch + consent-gate timeout) **exceeded the Dify→sidecar response timeout**, and Dify reported "peer closed connection without sending complete message body"
6. The sidecar container is healthy (up 18 hours, responding on :28080) — the break was the Dify response stream, not a sidecar crash

## Suspected Code Paths

- **Dify's MCP tool-call timeout** (the platform layer, upstream from this repo): long-running tool calls exceed the response window and the connection drops — this is the proximate cause
- **The terminal consent gate** (`~/.hermes/hermes-agent/`): the agent's verification step tried a terminal command which the gateway's consent system held for interactive approval that the API-server caller can never give — a **known amplifier** (documented in the `officemcp-connection-error` assessment) that adds a timeout to an already-slow turn
- **The upstream MCP args-dropping** (hermes-agent issue #148459): the known defect forced the agent into a slower fallback path, extending the turn duration
- **Not implicated**: the "two instances" Outlook conflict — **Outlook was not running** (RunningApps showed only Excel); no second-instance launch was attempted

## Root Cause Hypothesis

**Medium-high confidence.** Three stacked causes: (1) the known upstream MCP args-dropping forced the agent into a slower fallback path, extending the turn; (2) Outlook was not running and had to be Dispatched (COM cold start is slow); (3) the agent's verification step tried a terminal command that the gateway's consent gate held until timeout — adding a long wait to an already-long turn. The cumulative turn duration exceeded the Dify-side MCP response timeout, and the connection broke mid-response. The agent's behavior was honest and resourceful throughout (detected the degradation, switched fallback, avoided blind retries).

## Proposed Remediation

**Preferred** (three small changes):
1. **Agent-instruction addition**: "do NOT use terminal/shell commands for verification — verify by opening/reading the file through the Office application instead (the terminal consent gate blocks API-server turns)."
2. **Dify-side timeout**: increase the MCP tool-call response timeout in the Dify agent node configuration (the DSL's agent parameters or the Dify console) to accommodate long multi-step Office turns (300–600s).
3. **The upstream MCP fix** (issue #148459) remains the root cure — once arguments flow correctly, the agent's fallback overhead disappears and turns finish faster.

**Alternatives**: none needed — these are instruction + configuration changes, no code restructuring.

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_client.py` (OFFICE_INSTRUCTIONS: the no-terminal-verification rule)
- `dify/AGIAssistant/AGI_Assistant.yml` (if the tool-call timeout is configurable in the DSL)

**Tests to add or update**:
- Instruction text assertion in the tool suite (the no-terminal rule is present)

## Risks & Considerations

- The Dify timeout change may need console-level access (not just DSL), depending on where the timeout lives
- The consent gate is a security feature — the fix is to avoid triggering it (use in-app verification), not to disable it
- The upstream MCP fix will reduce turn durations and make the timeout less likely to fire, but the Dify timeout should still be raised to accommodate legitimate long turns

## Open Questions

- [NEEDS CLARIFICATION: whether the email draft was actually created before the connection broke — the audit shows STEP 2 completed (Outlook Dispatch started) but the connection broke before a verdict was returned; check the Drafts folder manually.]
- [NEEDS CLARIFICATION: where the Dify MCP tool-call timeout is configured — DSL, console, or plugin-level.]
