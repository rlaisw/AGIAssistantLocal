# Bug Fix: "Only one version of Outlook" — RunningApps-corruption fallback + upstream evidence posted

- **Slug**: `only-one-version-of-outlook-can-run-at-a-time`
- **Fixed**: 2026-11-04
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The agent's instructions now include a **RunningApps-corruption fallback**: "RunningApps may return INCOMPLETE data on a degraded MCP session — if Launch returns success but a dialog popped up or the app window doesn't match the request, the app was probably already running: try Dispatch/GetComObject to attach to the existing instance instead of retrying Launch." The RunningApps-corruption evidence was also posted to the upstream issue (hermes-agent #148459) as a new comment, and the full MCP recovery was run.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | The attach-first instruction gained the RunningApps-corruption fallback: "RunningApps may return INCOMPLETE data on a degraded MCP session — if Launch returns success but a dialog popped up or the app window doesn't match the request, the app was probably already running: try Dispatch/GetComObject to attach to the existing instance instead of retrying Launch." |
| Upstream (posted) | [hermes-agent issue #148459 comment](https://github.com/NousResearch/hermes-agent/issues/148459#issuecomment-6623159032) | New evidence: the degradation corrupts tool-call RESULTS (RunningApps missed a running OUTLOOK.EXE), not just tool-call arguments |

## Diff Highlights (optional)

```python
# OFFICE_INSTRUCTIONS — the RunningApps-corruption fallback
"RunningApps may return INCOMPLETE data on a degraded MCP session — "
"if Launch returns success but a dialog popped up or the app window "
"doesn't match the request, the app was probably already running: "
"try Dispatch/GetComObject to attach to the existing instance instead "
"of retrying Launch."
```

## Tests Added or Updated

- The existing 48 office suites stay green (the instruction is additive agent-layer text)

## Local Verification

- Commands: `pytest tests/unit/test_hermes_office_tool.py tests/unit/test_office_gate.py` → **48 passed**; hot-patched; `hermes mcp remove/add + gateway restart` → recovery done
- The upstream evidence was posted successfully (HTTP 201)

## Deviations from Assessment

- One editing accident: the first edit accidentally dropped the "Report honestly, ending EVERY executed step with" connector and the "leave the application open" clause — caught and restored in the same fix run. All instruction content is intact.
- No other deviations.

## Follow-ups

- The upstream fix (issue #148459) is the cure — the RunningApps data will be accurate when the MCP session is healthy.
- Fold this fix into the next commit (currently uncommitted alongside the `local-office-agent-failed` and `cannot-open-two-instances-of-outlook` changes).
- Close this bug as a derivative manifestation with the instruction fallback as the in-repo safety net.
