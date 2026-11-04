# Bug Assessment: Email draft failed — the upstream MCP args-dropping returned (Nth manifestation)

- **Slug**: `local-office-agent-failed`
- **Created**: 2026-11-04
- **Source**: pasted text ("The email draft could not be created — the local Office agent failed")
- **Verdict**: valid — but a **known duplicate**: the upstream MCP args-dropping defect (`officemcp-connection-error`, hermes-agent issue [#148459](https://github.com/NousResearch/hermes-agent/issues/148459)), now with new evidence that **all tool parameters** are dropped, not just RunPython's code
- **Severity**: medium — the same upstream blocker; the mitigation worked (honest, fast errors, no transport break)

## Report (verbatim or summarized)

User report: *"The email draft could not be created — the local Office agent failed"*. The audit trail shows two email attempts (04:54 and 04:56 UTC) both failing at the MCP session layer. This is the **same upstream defect** that has now manifested **7 times** across two days. The user tested successfully at ~04:16 UTC; the session degraded again by 04:54 — a ~38-minute healthy interval, consistent with the shortening pattern documented in the upstream escalation comment.

## Symptom

The email compose failed because the gateway→OfficeMCP MCP session degraded (the known upstream args-dropping). This occurrence adds a **new evidence point**: not only is `RunPython`'s `code` argument dropped, but `Launch`'s `app_name` parameter is also dropped — *"Launch calls returned success but the app_name parameter was dropped by the stale session (defaulted to Word)"*. The agent asked for Outlook, the server launched Word. This confirms the defect affects **all tool-call parameters**, not just code strings.

## Reproduction

1. At ~04:16 UTC the user tested email send successfully (healthy session)
2. At 04:54 UTC, an email compose attempt failed:
   - STEP 1 (RunningApps): succeeded — only Excel running, Outlook not running
   - STEP 2 (Launch Outlook): **FAILED** — *"Launch calls returned success but the app_name parameter was dropped by the stale session (defaulted to Word)"* — **new evidence: non-code parameters are also dropped**
   - STEP 3 (Compose draft): **FAILED** — *"2 consecutive RunPython calls returned only the default echo"*
3. At 04:56 UTC, a second attempt also failed with the same pattern
4. The OfficeMCP service was running (HTTP 200) and the sidecar was healthy throughout — the defect is exclusively in the gateway's MCP client session
5. The **mitigation worked perfectly**: honest errors, no transport break, actionable recovery hint

## Suspected Code Paths

- **Upstream** (`~/.hermes/hermes-agent/`): the MCP-over-SSE client — the same code path as `officemcp-connection-error` (issue #148459)
- **New evidence**: the `app_name` parameter of `Launch` was also dropped (the server received the default value "Word" instead of "Outlook") — confirming the defect is in the **argument serialization layer**, not specific to code strings

## Root Cause Hypothesis

**Certain — same as issue #148459**: the hermes-agent MCP client drops tool-call arguments after a period of session uptime. This is the **7th occurrence** across 2 days. New evidence: the defect affects all parameters (code strings AND named parameters like app_name), confirming it's a serialization-layer failure, not a content-specific one. The healthy interval between recovery and degradation remains irregular (~38 minutes in this case).

## Proposed Remediation

**Preferred**: no new code — this is the **same upstream defect**. The action is:
1. Run the recovery procedure (clears it every time so far)
2. Add this occurrence's new evidence (app_name also dropped) as a comment on the upstream issue — strengthens the serialization-layer hypothesis
3. Close this bug as a manifestation record of the known upstream defect

## Risks & Considerations

- The shortening failure intervals make the recovery procedure increasingly impractical as a long-term workaround
- The upstream fix is the only cure; our mitigation stack (detection, honest errors, recovery procedure) makes each occurrence fast and recoverable but cannot prevent the next one

## Open Questions

- [NEEDS CLARIFICATION: none — the root cause is known, filed, and escalated upstream with the worsening-interval data.]
