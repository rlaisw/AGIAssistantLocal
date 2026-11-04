# Bug Assessment: PowerPoint create — upstream MCP args-dropping (9th manifestation)

- **Slug**: `verdict-status-error`
- **Created**: 2026-11-04
- **Source**: pasted text (chat transcript)
- **Verdict**: valid — but the **same upstream defect** (`officemcp-connection-error`, hermes-agent issue [#148459](https://github.com/NousResearch/hermes-agent/issues/148459)); the mitigation fired perfectly
- **Severity**: low — known root cause, known recovery, the mitigation stack did its job

## Report

User asked to create "test-ppt v2" at `c:\temp\test` with text "Hello ver 2". The SESSION-DEGRADATION RULE fired: *"two consecutive calls returned only the default echo, so no document changes were made"*. Honest error, actionable recovery hint, no file created, no fabrication.

## Assessment

This is the 9th documented manifestation of the upstream MCP args-dropping (issue #148459). The transcript shows the mitigation stack working exactly as designed. The recovery procedure (`hermes mcp remove/add + gateway restart`) clears it every time. No new code is needed — the root cause is upstream and filed.

## Recommendation

Close as a manifestation record. Run the recovery and create the file. For future occurrences: file as comments on the upstream issue rather than separate bug slugs — the pattern is fully documented.
