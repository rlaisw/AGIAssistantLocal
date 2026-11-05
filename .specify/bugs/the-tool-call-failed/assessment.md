# Bug Assessment: "Failed to invoke tool" — deploy severed the in-flight stream; the strip window is time-based and the recovery hint re-arms it

- **Slug**: `the-tool-call-failed`
- **Created**: 2026-11-05T07:12+00:00
- **Source**: pasted text (chat transcript of the failing email request + the agent's reasoning/answer)
- **Verdict**: valid — two stacked, fully evidenced causes behind one user-visible turn
- **Severity**: high — the email lane is still unusable, the standard recovery hint is actively harmful, and the transport-level error misdirects the user toward exactly the actions that make things worse

## Report (verbatim or summarized)

> "The tool call failed with an error. The error is a connection issue: 'Failed to invoke tool: Error during cleanup: peer closed connection without sending complete message body (incomplete chunked read)'"

The user asked the chat to compose an email (body "test abc v3", subject "hello test v3", to raymond.lai@tvb.com.hk). Attempt 1 died at the Dify-plugin→sidecar transport layer with the incomplete-chunked-read error; the agent's retry (attempt 2) came back `status: error` — "Launching Outlook failed (Launch returned false), and the fallback attach/compose attempts also failed… No draft was created and nothing was sent."

## Symptom

An email compose turn fails twice in different ways: first with a mid-stream transport error from the Dify MCP plugin, then — after a full stack reset — with the gateway argument-strip again, plus a false `Launch Outlook` on bad RunningApps data. Expected: one tool call that composes the draft.

## Reproduction (all steps evidenced from logs, 2026-11-05 UTC)

1. 06:56:54 — the **sidecar container was gracefully stopped** (`StreamableHTTP session manager shutting down … Finished server process [1]`) and **recreated at 07:00:01** (`docker inspect`: RestartCount 0, ExitCode 0) — a `deploy redeploy`-style reset ran in this window
2. 07:01:01 — **OfficeMCP restarted** (PID 9096, started 15:01:01 local — stdout goes to `/tmp/agi-assistant-officemcp.log`, the reboot.sh redirect) and the **gateway restarted at 07:01:23** with a **fresh OfficeMCP registration** — i.e. `./reboot.sh` ran at ~07:01
3. The chat's attempt 1 was in flight when the sidecar went down → the plugin's chunked read died mid-body → *"peer closed connection without sending complete message body"* (the deploy cut the user's own request)
4. Attempt 2 (audit 07:05:06): the cold-window canary warm-up ran **8/8 stripped**, a delegated subagent **8/8 stripped**, the direct-SSE fallback blocked by the consent gate → honest stale error
5. Audit 07:05:59: RunningApps reported *"no Outlook instance running"* — **bad data** (OUTLOOK.EXE PID 19116 was up since 06:59:12) → `Launch Outlook` → **"Launch returned false"** (second-instance block; no dialog this time) → subsequent RunPython calls echoed the default
6. 07:10 probe (mine): still **8/8 stripped**, 9 minutes post-reset — consistent with a **time-based strip window** (both earlier resets today self-healed at ~14 minutes: 05:40→05:54 working; 06:29→06:43 working), not a call-count window

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_client.py` — `OFFICE_INSTRUCTIONS`: the SESSION-DEGRADATION RULE's recovery hint (`hermes mcp remove … then gateway restart`) **re-arms the strip window** every time it is followed; the 8-attempt canary warm-up (added 2026-11-05) cannot outrun a ~15-minute time window and lengthens turns toward plugin timeouts
- `src/agentic_rag_mcp/server.py` — the office-task envelope relays the agent's stale text verbatim, so the harmful hint reaches the user with authority
- Upstream (`~/.hermes/hermes-agent/`, issue #148459) — the argument strip itself: now evidenced as **time-gated after (re)registration** (fresh gateway or fresh server registration strips argument-carrying calls for ~10–15 minutes; args-free tools work throughout; `C:\temp\officemcp_calls.log` shows byte-level default-schema payloads arriving)
- `deploy redeploy` / `reboot.sh` (ops) — stopping the sidecar at 06:56:54 severed an in-flight chat request mid-body; nothing drains in-flight MCP streams before shutdown
- OfficeMCP `RunningApps` — returned "no Outlook" while OUTLOOK.EXE ran (recurring corruption signature; the process probe in the instructions is the reliable source)

## Root Cause Hypothesis

**High confidence on both components.** (1) Attempt 1's transport error is the sidecar's 06:56:54 graceful shutdown during an in-flight request — whoever ran the deploy reset cut the user's own turn mid-stream; httpx reported the severed chunked body to the Dify plugin. (2) Attempt 2's failure is the upstream #148459 strip in its real shape: a **~10–15-minute time window after any gateway restart or MCP re-registration** during which argument-carrying tool calls arrive with empty payloads. This model explains everything previously unexplained: recovery "no longer clearing" today (recovery **re-creates** the window), the "intermittent within minutes" flips (window edges), and today's call-count observations (5, 8, 14 stripped — all just how many calls fit inside the window).

## Proposed Remediation

**Preferred**: stop recommending the reset, teach the wait. (1) Replace the SESSION-DEGRADATION RULE's recovery hint in `OFFICE_INSTRUCTIONS` (and the matching DEPLOY.md row) with: the strip window is **time-based after a gateway restart or MCP re-registration**; argument delivery self-heals in **~10–15 minutes**; do NOT re-register, restart the gateway, or restart OfficeMCP — wait and retry once. (2) Shorten the canary warm-up from 8 attempts to 2–3 (a time window cannot be canary-punched; the long loop only burns the turn budget and invites plugin timeouts), then report the wait guidance with the window ETA. (3) Extend the Outlook rule: RunningApps is unreliable — **process-probe outlook.exe before any Launch**, never Launch on a probe hit (this turn's "Launch returned false" was fully avoidable). (4) Add the time-window model to upstream issue #148459 (draft exists in the sibling bug dir).

**Alternatives**:
- Fix the client-side strip locally in hermes-agent (editable install) — the durable fix, but it is upstream's serialization code and today's evidence (time-gated, registration-correlated) still doesn't point at a specific line; a local fix risks drift when upstream updates
- Deploy-time stream draining (finish in-flight MCP requests before shutdown) — worthwhile but a separate, lower-severity ops issue; note it, don't bundle it here

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_client.py` — wait-based rule text, shortened warm-up, process-probe-before-Launch
- `DEPLOY.md` — the known-defect row's recovery column (currently recommends the harmful reset)
- `tests/unit/test_hermes_office_tool.py` — instruction-guard updates

**Tests to add or update**:
- Extend `test_office_instructions_contain_attach_failure_protocol` (or add a sibling) asserting: the wait-based hint, the absence of the `hermes mcp remove` reset recommendation, the 2–3-attempt warm-up cap, and the process-probe-before-Launch rule

## Risks & Considerations

- The ~10–15-minute window is measured from two data points today plus one from 05:40→05:54; treat it as approximate — the guidance should say "about 15 minutes"
- Removing the reset recommendation changes long-documented runbook behavior (DEPLOY.md, older bug lifecycles) — those docs describe the old "hours of uptime" pattern; they should be annotated, not silently rewritten
- The sidecar-shutdown-mid-request issue remains: a deploy during active chat use will keep severing streams — the honest error text can at least name the cause
- The gateway restart by reboot.sh at every boot means office tasks may be strip-blocked for the first ~15 minutes after any machine reboot — the reboot.sh output should warn about this

## Open Questions

- [NEEDS CLARIFICATION: who ran the deploy reset at ~06:57 and reboot.sh at ~07:01 — the user following the recovery hint? If scripted, the script needs the same wait-based fix]
- [NEEDS CLARIFICATION: is Outlook's COM state healthy after the 06:59 restart (PID 19116)? The 07:05 turn never reached attach — untested since the restart]
