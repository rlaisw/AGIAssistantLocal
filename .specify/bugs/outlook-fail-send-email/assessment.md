# Bug Assessment: Outlook email compose fails — the upstream MCP args-dropping defect (shortening interval)

- **Slug**: `outlook-fail-send-email`
- **Created**: 2026-11-03
- **Source**: pasted text (chat transcript from the deployed Chat UI)
- **Verdict**: valid — but a **manifestation of the known upstream defect** (`officemcp-connection-error`, hermes-agent issue [#148459](https://github.com/NousResearch/hermes-agent/issues/148459)); filed here to document the email-path impact and a worsening data point
- **Severity**: medium — the upstream defect blocked a specific email send; the mitigation worked perfectly (honest, fast, actionable error instead of silence)

## Report (verbatim or summarized)

The user asked: *"send body 'test 123', subject 'abc-test'"*. The chat agent — after initially doubting whether it had the Office tool — correctly called `hermes_office_task`, which failed at **STEP 2: Compose draft** with: *"two consecutive RunPython calls returned only the default echo; the MCP session to OfficeMCP is stale and the code argument was dropped. TASK: FAILED — OfficeMCP session stale"*. The agent relayed this honestly with the recovery hint and corrected its earlier confusion: *"the Office tool is available to me — the blocker is the stale MCP session, not a missing capability."* No draft was created; nothing was sent.

## Symptom

The user's email compose request ("test 123" body, "abc-test" subject, to rlaisw@gmail.com) failed because the gateway→OfficeMCP MCP session had degraded — the same argument-dropping defect documented in `officemcp-connection-error`. The **mitigation** (the SESSION-DEGRADATION RULE) fired perfectly: the agent stopped retrying after 2 empty deliveries and gave an immediate, honest, actionable error with the recovery steps.

## Reproduction

1. The user sent an email request through the chat at ~12:29 UTC
2. The tool's STEP 1 (attach to running Outlook) succeeded — the agent correctly attached to the already-running instance
3. STEP 2 (compose draft via RunPython) failed — the code argument was dropped, the server returned the default echo
4. The SESSION-DEGRADATION RULE fired: the agent stopped retrying and reported `TASK: FAILED — OfficeMCP session stale` with the recovery hint
5. The audit trail confirms both attempts (12:25 and 12:29) failed identically
6. The OfficeMCP service itself was running (HTTP 200) throughout — the defect is in the gateway's MCP client session

**New data point**: the session degraded within **~20 minutes** of the last successful recovery (my "42 in A1" test at ~12:06). The previously observed interval was hours. The failure interval is **shortening**, which means the recovery procedure is becoming less practical as a workaround.

## Suspected Code Paths

- **Upstream** (`~/.hermes/hermes-agent/`): the MCP-over-SSE client's tool-call argument serialization — the same code path as `officemcp-connection-error` (hermes-agent issue #148459)
- **Not implicated**: `office_gate.py` (the gate classified the task correctly), `server.py` (the envelope and audit were honest), `hermes_client.py` (the instructions and the SESSION-DEGRADATION RULE worked as designed)

## Root Cause Hypothesis

**Certain — same as `officemcp-connection-error`**: the hermes-agent's MCP-over-SSE client drops tool-call arguments after a period of session uptime. This occurrence adds a new data point: the failure interval has shortened from hours to **~20 minutes**, making the defect more severe than initially assessed. The upstream issue (#148459) is filed with the evidence chain; the shortening interval should be added as a comment.

## Proposed Remediation

**Preferred**: no new code — this is a **duplicate manifestation** of `officemcp-connection-error`. The existing mitigation (SESSION-DEGRADATION RULE, W0 pre-flight, DEPLOY.md recovery procedure) already handles this case. The action is:
1. **Comment on the upstream issue** (#148459): add the shortening-interval data point (hours → 20 minutes) — this raises the severity upstream
2. **Recover the session** and compose the user's email (the immediate fix)
3. This bug directory closes as a manifestation record — the work item lives upstream

**Alternatives**: none needed — the mitigation is already deployed and functioning correctly.

## Risks & Considerations

- The shortening failure interval means the recovery procedure may soon become impractical (if the interval drops below the time to use the service after recovery)
- If the interval continues shrinking, a **scheduled session refresh** (cron-style re-registration) may become necessary despite its downsides (gateway bounce interrupts in-flight turns)

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the root cause is known and filed upstream; the action is recovery + upstream comment.]
