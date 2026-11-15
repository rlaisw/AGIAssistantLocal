# Bug Fix: exhausted USER_CONTROL retries now surface as a named deferral — no raw JSON, no misleading schtasks hint

- **Slug**: error-windows-mcp-tool-error
- **Fixed**: 2026-11-14T13:55:00+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — classification + envelope shipped, pinned by fake-session behavioral tests, container rebuilt

## Summary

When the windows-mcp service's desktop-activity deferral (`USER_CONTROL`, `state: user`) outlasts the lane's bounded consent retries, the final response is now classified as a **named deferral** — `blocked: the Windows-MCP service deferred the call while the desktop user is active (USER_CONTROL) — nothing ran; wait a few seconds and ask again` — instead of a generic tool-error with raw JSON, so the chat relays an actionable reason without the misleading "start the Scheduled Task" hint (the service is up). Explicit declines keep their own refusal wording; the wait-retry recovery path is unchanged and pinned.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/windows_mcp/client.py` | modified | `_DEFERRAL` constant + the post-loop classification: still-pending USER_CONTROL → blocked deferral (audited `decision: blocked`), checked before the explicit-refusal and generic-error classes |
| `tests/unit/test_windows_mcp_lane.py` | added tests | `TestUserControlDeferral` (below) |

## Diff Highlights (optional)

```python
if res.isError:
    if _user_control_wait(text) is not None:
        # the retries exhausted with the deferral still pending
        envelope = {"status": "blocked", "reason": _DEFERRAL}
        decision = "blocked"
    elif classify_refusal(text):
        ...  # explicit declines unchanged
```

## Tests Added or Updated

- `test_exhausted_user_control_is_a_named_deferral` — a fake session that returns USER_CONTROL on every attempt → exactly 4 bounded retries → the blocked deferral envelope (no `schtasks`, no raw JSON payload, no `wait_seconds`), audit row `windows-mcp-process` / `decision: blocked`.
- `test_explicit_decline_keeps_the_refusal_wording` — "declined by the user" still yields the "host did not approve execution" refusal (classes don't bleed).
- `test_success_after_two_deferrals` — two deferrals then a quiet desktop → the wait-retry loop recovers and returns ok (the loop's original purpose stays intact).

## Local Verification

- Commands: `pytest tests/unit/test_windows_mcp_lane.py` → **32 passed**; full `pytest tests/unit` → **688 passed, 0 failed**; `ruff check` → clean on touched files; `deploy redeploy` → rebuilt, health ok, tools 55/55.
- Live probe on the rebuilt container (desktop quiet): `windows_mcp_process_list` → **ok**, human-scale table ("CPU% (of machine)") — the deferral envelope itself cannot be forced deterministically (it needs ~30 s of continuous desktop activity) and is pinned by the fake-session test instead.

## Deviations from Assessment

None — the classification, envelope wording, audit class, and both boundary pins match the contract. (One test assertion was self-corrected during development: the envelope deliberately names "(USER_CONTROL)", so the "no raw JSON" pin targets `{"code"`/`wait_seconds`, not the signal's name.)

## Follow-ups

- Watch the audit trail: future `windows-mcp-*` rows with `decision: blocked` and the deferral text are the fix working; any new `error:windows-mcp-tool-error` rows carrying USER_CONTROL JSON would indicate a regression of the classification order.
- The deferral frequency is inherent to the service's desktop-activity guard (upstream): the named envelope plus "ask again" sets the right expectation without long in-turn silent waits.
