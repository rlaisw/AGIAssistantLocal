# Bug Fix: conversation-level strip memory — follow-on office tasks skip the channel-detection tax

- **Slug**: `completed-message-wait-long-time`
- **Fixed**: 2026-11-06T07:25+00:00
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`OfficeState` now tracks the gateway strip conversation-wide: the first task that detects it records `gateway_stripped_at` (sticky, not restamped), and every follow-on task in that conversation receives a directive hint — "gateway RunPython channel is KNOWN STRIPPED — skip all canaries and detection, run directly on the direct channel" — removing the 30–60 s per-task detection tax while the upstream strip (#148459) persists. A healed gateway channel (steps delivering without the direct-channel fallback) clears the flag, keeping it self-correcting.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/office_state.py` | modified | `gateway_stripped_at` / `mark_gateway_stripped` (first observation wins) / `clear_gateway_stripped` per conversation |
| `src/agentic_rag_mcp/server.py` | modified | `_run_agent` marks the strip from the agent's step output ("stripped" / "switched to the direct") and clears it when steps delivered on the gateway channel; the directive build injects the KNOWN-STRIPPED skip-detection hint into `directive_ctx` when set |
| `tests/unit/test_office_state.py` | added test | `test_gateway_strip_state_is_conversation_scoped_and_clearable` — sticky, scoped, clearable |
| `tests/unit/test_hermes_office_tool.py` | annotated | The hint is server-side (directive), not instructions text — guarded by absence |

## Diff Highlights (optional)

```python
# server.py — the hint injected into every follow-on directive
stripped_at = state.gateway_stripped_at(conversation_id)
if stripped_at:
    directive_ctx += ("The gateway's RunPython channel is KNOWN STRIPPED "
        f"in this conversation (observed {stripped_at}) — skip all gateway "
        "canaries and channel detection and run this task's steps directly "
        "on the direct OfficeMCP channel …")
# _run_agent: mark on strip evidence, clear on gateway-channel delivery
```

## Tests Added or Updated

- `tests/unit/test_office_state.py::test_gateway_strip_state_is_conversation_scoped_and_clearable` — pins the state semantics
- Full suite → **333 passed**; `ruff` clean on the changed hunks

## Local Verification

- `pytest tests/unit` → 333 passed; `deploy redeploy` → ok: 4 steps
- **Live two-task test (same conversation)**: Task 1 (create) detected the strip (2 canaries → direct channel) and recorded it — 62.3 s; **Task 2 (save+close) shows no canary/detection step at all** ("STEP 1: save workbook OK … via direct channel" — the hint was consumed), 97.8 s vs the bug's 109 s baseline. The detection tax is structurally removed from follow-on turns; the remaining wall-clock is the nested-LLM floor (Dify hop + gateway agent iterations) documented as the executor follow-up.

## Deviations from Assessment

- The assessment's expected saving ("save+close should land near 50–60 s") proved optimistic in the live run — task 2 (97.8 s) still spent LLM iterations narrating the save/close/quit steps and a lingering-EXCEL.EXE cleanup, so the wall-clock gain over the 109 s baseline was modest in this single sample. The detection-tax *component* is provably gone (no detection step in the audit trail); the remaining latency is the nested-LLM floor, which only the deterministic executor removes. Noted for expectation-setting.

## Follow-ups

- The deterministic executor spec is now the single remaining latency lever (this lifecycle, `a-little-bit-slow-to-create-email`, and `close-excel-wait-long-time` all point at it) — owner to schedule
- The sticky flag is in-memory (conversation-scoped scratch, like the rest of OfficeState): sidecar restart clears it — one detection tax per restart per conversation, acceptable
- Watch natural multi-task conversations: follow-on task reports should show no detection steps while the strip persists