# Bug Assessment: Stop doesn't halt the desktop agent — the control notice kept flashing for minutes after the user pressed Stop, with no chat response

- **Slug**: `repeated-show-ai-is-controlling-this-computer-many-times`
- **Created**: 2026-11-09T03:20+00:00
- **Source**: pasted text ("repeated show 'AI is controlling this computer' many times, and wait long times, no response") + full log reconstruction of the two failing turns
- **Verdict**: valid — one NEW defect (stop does not propagate to the running gateway agent) compounding two known limits (the ~300 s chat ceiling and the slow-desktop latency floor)
- **Severity**: high — after the user presses Stop, the AI keeps controlling the desktop for minutes; the autonomy contract of the Stop button (spec 027) is broken at its deepest layer

## Report (verbatim or summarized)

> "repeated show 'AI is controlling this computer' many times, and wait long times, no response"

The user re-sent "help to open chrome browser , type hong kong temperature today" twice after an earlier identical request had completed (audit 02:44:01: Chrome activated, query typed). Both retries failed the same visible way: the WindowsMCP control notice flashed repeatedly on the desktop, the chat showed only the first-iteration announcement ("I'll open Chrome and type the search query for you."), nothing further arrived, and after a long wait the user stopped / the stream cut.

## Symptom

During a desktop-followup turn, the "AI is controlling this computer" notice re-arms on every gated action (by design, each shows it; the spec-032 patch clears each in ~3 s — hence "repeated show many times"), the chat streams no progress for minutes, and — critically — **the desktop control continues long after the user presses Stop**. Expected: Stop halts the desktop work.

## Reproduction (reconstructed from three log layers, 2026-11-09 UTC)

1. Turn 1 (created 02:57:45): the chat streamed the agent's first-iteration announcement, then silence. The user pressed **Stop at ~136 s** (workflow status `stopped`, elapsed 135.7 s). **The gateway agent kept running**: inbound 02:57:49, `response ready` only at **03:07:28** (570 s total — over 7 minutes of continued desktop work *after* the stop, flashing the notice on every gated action). No audit entry for this turn's tool verdict ever reached the log tail examined.
2. Turn 2 (created 03:00:37): same shape — workflow `stopped` at 301 s (the documented Dify-daemon ceiling cut), gateway `response ready` at 03:08:00 (440 s). Again: desktop work continued past the cut.
3. The stop chain today: UI Stop → `/api/chat/stop` → Dify `/chat-messages/{taskId}/stop` — which halts the **Dify workflow** (message finalized `stopped`, no more answer events → "no response") but does **not** reach the plugin invocation running in the daemon, whose back-invocation keeps the **gateway agent session** alive until its own completion.
4. Both turns' answers contain only the first-iteration narration — everything after the stop/cut was never delivered, and the desktop kept working visibly.

## Suspected Code Paths

- `ai-chat-landing/app/api/chat/stop/route.ts` — the stop proxy ends at Dify's workflow stop; nothing addresses the gateway-side agent turn (and cannot: the Dify `taskId` is not a gateway turn id).
- `src/agentic_rag_mcp/server.py` (`hermes_launch_app`/`_await_with_keepalive`) — the sidecar's blocking POST to the gateway `/v1/responses` has no cancellation handle; nothing links the Dify invocation to the gateway session for stopping.
- The hermes gateway — has a control socket (`~/.hermes/gateway.sock`); whether it exposes per-turn cancellation is unknown — the fix phase must investigate (it exists, 2 WindowsMCP processes running, socket present).
- Known limits compounding the experience: the ~300 s chat-side ceiling (`the-local-agent-hit-a-transport-error`, closed as a Dify-daemon hard limit — these turns ran 440–570 s gateway-side, so they could never complete through the chat), and the desktop latency floor (WindowsMCP UIA captures 20–26 s per snapshot; a Chrome launch+type ran ~10 minutes gateway-side).

## Root Cause Hypothesis

**High confidence.** The user-visible compound: (1) **NEW**: pressing Stop (or the ceiling cut) severs the *chat* but not the *agent* — the Dify stop halts the workflow while the plugin invocation and its gateway session continue executing desktop actions until natural completion, re-arming the control notice each time; the notice flashing "many times" after the stop is the agent still working, and "no response" is the stopped workflow delivering nothing. (2) The long waits are the known slow-desktop floor, and these particular turns' durations (440–570 s) exceed the chat ceiling, so even without the stop they would have ended in the honest ceiling relay.

## Proposed Remediation

**Preferred**: make Stop reach the agent. (1) Investigate the gateway's control-socket/API for per-session or per-turn cancellation (`gateway.sock`; the `hermes` CLI may expose a stop command — `hermes gateway`/agent session management). (2) Wire the chain: the sidecar registers each in-flight `run_task` with its conversation id and a cancellation handle; a new sidecar endpoint (or the existing stop flow extended) lets the Chat UI's stop route call the sidecar to cancel the gateway turn for that conversation. Minimal shape: `stop/route.ts` → sidecar `/cancel?conversation=…` → gateway cancel (or httpx-abort of the pending POST, which frees the sidecar; whether the *gateway* aborts its agent on client disconnect must be tested — the probe evidence of continued work after the *Dify* cut suggests the gateway turn runs to completion regardless of consumers, so client-side abort may not suffice; the control socket is the likely lever). (3) In the same pass, the FASTEST-PATH guidance gains a hard wall-clock check: the agent should end honestly by ~540 s (its envelope) — it did (570 s ≈ within the 540 s + overhead), so this is working as designed; no change.

**Alternatives**:
- Do nothing to stop-propagation and rely on the WindowsMCP takeover (Ctrl+Alt+Shift+Backspace / mouse move seizes input control) — insufficient: seizing input stops *typing* but the turn (and notice re-arming from non-input actions like screenshots) continues; and the Stop button's contract stays broken.
- Reduce durations below the ceiling (deterministic executor / lighter tasks) so stops are rarely needed — the long-term floor fix, but orthogonal to the stop contract.

**Files likely to change**:
- `ai-chat-landing/app/api/chat/stop/route.ts` — chain extension (sidecar cancel call)
- `src/agentic_rag_mcp/server.py` — in-flight task registry + cancel endpoint; wire `run_task` cancellation
- `src/agentic_rag_mcp/hermes_client.py` — gateway cancellation call (pending the control-socket investigation)
- Tests: sidecar registry/cancel unit tests; UI stop-route test (the route-test pattern now exists)

**Tests to add or update**:
- Sidecar: a registered in-flight task is cancellable via the new endpoint; cancel aborts the pending httpx call and returns promptly
- Route: stop now calls both Dify and the sidecar (order tolerant; sidecar unreachable is non-fatal)
- Live: a desktop turn stopped mid-work must stop the desktop actions within seconds (notice stops re-arming)

## Risks & Considerations

- The gateway's cancellation surface is unproven — the fix phase must first confirm the control socket or API can abort an agent session; if it cannot, the fallback is documenting the limit and relying on the takeover + honest envelope
- The sidecar↔conversation mapping must be per-conversation (multiple in-flight turns across conversations); the registry must clean up on completion (no leaks)
- The stop route gains a second network call — keep it fire-and-forget with a short timeout (the UI must never block on it); idempotent on no-active-task
- Turn durations above the ceiling remain un-deliverable through the chat regardless — the known-limit posture (split requests) still applies

## Open Questions

- [NEEDS CLARIFICATION: does the hermes gateway control socket (or CLI) expose agent-session cancellation? — the first fix-phase task; everything downstream depends on it]
- [NEEDS CLARIFICATION: none on the UI layer — the stop route and sidecar shapes are conventional]
