# Bug Assessment: Word file v2 — created on the first attempt, verdict lost, retry blocked by stale session (12th manifestation)

- **Slug**: `the-tool-call-failed-with-an-infrastructure-error`
- **Created**: 2026-11-04
- **Source**: pasted text (chat transcript)
- **Verdict**: valid — but the **same upstream MCP degradation** (issue [#148459](https://github.com/NousResearch/hermes-agent/issues/148459)); the file was **created on the first attempt** (transport dropped the response), then the retry correctly hit the SESSION-DEGRADATION RULE
- **Severity**: low — the file exists with the correct content

## Report

User asked for "test ms word ver2" at `c:\temp\test` with "aaa hello". First attempt: Dify transport dropped ("peer closed connection — incomplete chunked read"), but **the task actually completed** — the file is at `C:\temp\test\test ms word ver2.docx` with "aaa hello" verified. The agent's retry (reasonable for a transport error) correctly got the SESSION-DEGRADATION RULE error ("RunPython returned only the default echo; stale MCP session") — the first long turn had degraded the session. The agent honestly reported both failures and didn't claim the file existed (correct — it couldn't verify).

## Assessment

12th manifestation of the upstream defect. Both error layers (transport drop + session degradation) fired in sequence, both honestly. The file is created and verified. No new code needed.
