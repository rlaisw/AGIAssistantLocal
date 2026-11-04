# Bug Assessment: Dify transport timeout — the file WAS created (upstream MCP degradation, known duplicate)

- **Slug**: `office-agent-call-failed`
- **Created**: 2026-11-04
- **Source**: pasted text (chat transcript)
- **Verdict**: valid — but a **known duplicate** of the upstream MCP degradation (`officemcp-connection-error`, issue [#148459](https://github.com/NousResearch/hermes-agent/issues/148459)); this occurrence adds the important nuance that the task **completed successfully** but the Dify→sidecar response stream dropped before the verdict could reach the agent
- **Severity**: low — the user-visible failure is a confusing "no verdict" message, but the underlying task succeeded

## Report (verbatim or summarized)

The user asked to create a PowerPoint named "test-ppt v1" at `c:\temp\test` with text "Hello". The agent called `hermes_office_task`; the Dify→sidecar connection dropped mid-response ("peer closed connection without sending complete message body — incomplete chunked read"). The agent honestly reported the failure without retrying (to avoid duplicate files). **The audit trail and file verification prove the task actually completed**: all steps OK (folder created, deck created with "Hello", verified from disk) — the response was lost in transit, not the work.

## Symptom

The Dify→sidecar MCP response stream dropped after the sidecar completed the task, so the agent received a transport error instead of the success verdict. The user sees "Office agent call failed" with no recovery hint, but the file was actually created. Expected: the verdict reaches the agent and the user sees the honest success report.

## Reproduction

1. The user prompted a PowerPoint creation at 05:55 UTC
2. The sidecar executed the task successfully (audit: 4 steps all OK — folder, deck, text, verified from disk)
3. **The file exists**: `C:\temp\test\test-ppt v1.pptx` with "Hello" on one slide (slide XML verified)
4. The Dify→sidecar response stream dropped before the verdict could be relayed
5. The agent reported the transport error honestly and offered to retry or verify (exemplary behavior)

## Suspected Code Paths

- **Dify's MCP tool-call response timeout**: the turn duration (MCP degradation overhead + folder creation + deck creation + disk verification) exceeded Dify's response window, causing the "peer closed connection" error. This is the same amplifier addressed by the `cannot-open-two-instances-of-outlook` fix (the no-terminal-verification rule and the iterations reduction already deployed).
- **Upstream MCP degradation** (issue #148459): the agent likely spent extra time on MCP session overhead before the direct fallback kicked in, extending the turn.

## Root Cause Hypothesis

**Medium confidence**: the upstream MCP args-dropping forced the agent into slower fallback paths (canary + channel switching), extending the turn duration past Dify's MCP response timeout. The task itself completed on the direct path — only the verdict was lost in transit. The no-terminal-verification rule and the reduced iteration budget (from the previous fix) may not be sufficient to keep all turns within Dify's timeout while the upstream degradation persists.

## Proposed Remediation

**Preferred**: run the recovery and confirm the file to the user. No new code — this is a known upstream defect manifestation. The file already exists.

**Files likely to change**: none (all mitigations already deployed).

## Risks & Considerations

- The "task succeeded but verdict lost" pattern means the agent can't tell the user whether a file was created — the user must check manually or retry (risking a duplicate).
- The Dify MCP response timeout remains the outer boundary that converts any long turn into a transport error; the upstream fix is the cure.

## Open Questions

- [NEEDS CLARIFICATION: none — the file is verified, the root cause is known upstream.]
