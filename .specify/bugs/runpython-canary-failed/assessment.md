# Bug Assessment: RunPython canary — upstream MCP args-dropping (13th manifestation)

- **Slug**: `runpython-canary-failed`
- **Created**: 2026-11-04
- **Source**: pasted text (chat transcript)
- **Verdict**: valid — but the **same upstream MCP degradation** (issue [#148459](https://github.com/NousResearch/hermes-agent/issues/148459)); the canary detected the stale session and the SESSION-DEGRADATION RULE fired correctly
- **Severity**: low — known root cause, mitigation worked perfectly

## Report

User asked for "ms-ppt-test v9" at `c:\temp\test` with "hello word". The agent's canary detected the args-dropping (3 consecutive default echoes), stopped immediately, and reported TASK: FAILED with the recovery hint. No file was created (the session was degraded before any work executed). The mitigation stack handled this perfectly — the fastest path to completion is the recovery procedure + retry.

## Assessment

13th manifestation of the upstream defect. The canary (a pre-task probe the agent improvised during this session's degradation events) caught the issue before any wasted work. No new code needed — run the recovery and retry.
