# Bug Assessment: Word file — transport error on first attempt, retry succeeded (14th manifestation, positive outcome)

- **Slug**: `the-tool-returned-an-invoke-error`
- **Created**: 2026-11-04
- **Source**: pasted text (chat transcript)
- **Verdict**: valid — but a **transient manifestation** of the upstream MCP degradation (issue [#148459](https://github.com/NousResearch/hermes-agent/issues/148459); this one **self-recovered**: the agent's single retry succeeded
- **Severity**: low — the file was created; the agent's retry logic worked

## Report

User asked for "MS word test ver 11" at `c:\temp\test` with "abc hello". The first invocation hit a Dify transport drop ("peer closed connection — incomplete chunked read"). The agent correctly reasoned: transport error ≠ blocked refusal → retried once. **The retry succeeded**: canary OK, attached to running Word (the file existed as the session's active document, updated in place), literal text written, saved, verified from disk (13,444 bytes, reads back "abc hello"). The agent reported both the first failure and the success honestly.

## Assessment

14th manifestation, but a **positive** one — no recovery procedure was needed, the retry self-healed the transient failure. The agent's judgment (retry a transport error once, don't retry a blocked refusal) was correct. The file is at `C:\temp\test\MS word test ver 11.docx`, verified.

## Recommendation

File created and verified. Close as a manifestation record. This occurrence shows the mitigation stack's resilience: not every degradation requires the full recovery — a single agent-initiated retry sometimes suffices.
