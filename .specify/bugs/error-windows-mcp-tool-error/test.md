# Bug Verification: exhausted USER_CONTROL retries surface as the named deferral — pinned, shipped, happy path intact

- **Slug**: error-windows-mcp-tool-error
- **Tested**: 2026-11-14T14:05:00+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: **verified** — the classification is pinned by the fake-session behavioral battery, shipped in the running container, and the happy path is live-intact; the exhaustion path itself is verified by the deterministic pin (it cannot be forced live without ~30 s of continuous desktop activity — one opportunistic live attempt fired during a quiet moment and correctly took the happy path instead)

## Summary

The raw-JSON-plus-schtasks-hint envelope can no longer occur: a still-pending USER_CONTROL after the bounded retries is classified as the named deferral (`blocked`, no raw payload, no service-down hint), audited as blocked — pinned by three fake-session tests covering the exhaustion, the explicit-decline boundary, and the recovery path. The rebuilt container ships the classification (verified in-container), the full suite is green, and a live listing on the shipped build answers ok in 0.6 s with the human-scale table.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Deferral battery (the reproduction's automated equivalent) | `pytest tests/unit/test_windows_mcp_lane.py::TestUserControlDeferral` | **pass** | 3 tests: exhausted → named deferral (exactly 4 bounded retries, no `schtasks`, no `{"code"`, audit `blocked`); explicit decline → refusal wording unchanged; two deferrals then quiet → recovery ok |
| Shipped-artifact check | `docker exec … import _DEFERRAL` | **pass** | the running container carries the classification (the fix-phase live probe already ran on this build) |
| Happy path live | `windows_mcp_process_list(sort_by="cpu")` through the container | **pass** | ok in 0.6 s, human-scale table ("CPU% (of machine)", System Idle 97.1%) — the wait-retry machinery didn't disturb the quiet-desktop path |
| Live exhaustion (opportunistic) | the same probe fired while the desktop was (unknowably) quiet | **not-fired** | the service did not defer during the probe — this path is covered by the deterministic pin; forcing it would need ~30 s of continuous desktop activity |
| Regression suite | `pytest tests/unit` (full) | **pass** | 688 passed, 0 failed |
| Lint | `ruff check` (changed files) | **pass** | clean on touched files (the repo-wide unsafe-fix suggestion is pre-existing, untouched) |

## Output Excerpts

```
pytest test_windows_mcp_lane.py → 32 passed (3 new deferral pins)
docker exec … _DEFERRAL → "blocked: the Windows-MCP service deferred the call while the desktop user is active (USER_…
live probe [0.6s] → {"status":"ok","text":"… CPU% (of machine) … System Idle Process 97.1% …"}
pytest tests/unit → 688 passed, 0 failed
```

## Residual Risks

- The live exhaustion envelope has not been observed with a human at the desktop (only pinned deterministically) — the next natural occurrence in chat should show the named deferral verbatim; the audit trail will carry it as `decision: blocked` with the deferral reason.
- The deferral frequency is inherent to the service's desktop-activity guard; the envelope's "wait a few seconds and ask again" is the correct user guidance — the upstream service remains the only place the guard itself could be tuned.

## Recommendation

**Close the bug — verified to the limit the environment allows.** The misclassified envelope is structurally eliminated (classification order + pins), the shipped build carries it, the classes don't bleed (refusal/deferral/recovery all pinned), and the full suite is green. The first real deferral in chat will confirm end-to-end exactly as the pin predicts.
