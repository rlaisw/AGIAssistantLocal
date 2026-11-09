# Bug Verification: plugin-library env vars present but insufficient — the ~300 s cut persists; the real knob is the daemon's DIFY_BACKWARDS_INVOCATION_READ_TIMEOUT

- **Slug**: `the-local-agent-hit-a-transport-error`
- **Tested**: 2026-11-09T01:55+00:00 (second test cycle; supersedes the first-cycle test.md — git preserves it)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: **failed** — with decisive new evidence for the next fix cycle

## Summary

The fix's env vars are demonstrably live (both at 600 in the daemon AND inherited by the plugin processes, verified via `/proc/<pid>/environ`), and the pipeline works under the old ceiling (a 238 s chat turn delivered the full adapter configuration). But the deliberately-slow >300 s sample reproduced the cut **again at exactly 300.000 s** (sidecar log: POST 01:32:21.957 → terminated 01:37:21.917) — the fix removed the wrong 300. The test's own investigation located the binding one: the daemon Go binary exposes **`DIFY_BACKWARDS_INVOCATION_READ_TIMEOUT` / `DIFY_BACKWARDS_INVOCATION_WRITE_TIMEOUT`** (`strings /app/main` envconfig list) — the back-invocation relay's read deadline, plausibly defaulting to 300 s, untouched by everything changed so far.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Fix's env live in daemon | `docker exec … env` | **pass** | MAX_REQUEST_TIMEOUT=600, MAX_INVOCATION_TIMEOUT=600 present after the recreate |
| Env inherited by plugin processes | `/proc/33/environ` (agent plugin) | **pass** | The plugin subprocess carries both at 600 — the fix's mechanism was correctly deployed |
| Reproduction, sub-ceiling sample | chat turn "open control panel , show me network adapter configuration…" (01:26–01:30) | **pass (below ceiling)** | 238 s, `status=normal`, no transport error, full IP config delivered — proves the pipeline healthy under 300 s |
| Reproduction, >300 s sample (the decisive one) | chat turn "open device manager , show me the properties of every disk drive and USB controller one by one…" (01:32–01:37) | **FAIL — symptom reproduced** | Sidecar stream terminated at **exactly +300.000 s**; the turn relayed "peer closed connection without sending complete message body"; the agent honestly declined to retry (01:37:26, `status=normal` for the relay itself) |
| Binding-knob discovery (test-phase investigation) | `strings /app/main \| grep envconfig` | **finding** | `DIFY_BACKWARDS_INVOCATION_READ_TIMEOUT` + `…WRITE_TIMEOUT` exist as daemon env knobs — the back-invocation relay's HTTP deadline; never set in the daemon env (checked) — this is the remaining 300 and the next fix's target |
| Regression suite | `pytest tests/unit` | **pass** | 354 passed |

## Output Excerpts

```
sidecar (cut sample): 01:32:21.957 POST /mcp 200 → 01:37:21.917 Terminating (=300.000s)
plugin env (PID 33): MAX_REQUEST_TIMEOUT=600, MAX_INVOCATION_TIMEOUT=600  (fix deployed)
daemon strings: envconfig:"DIFY_BACKWARDS_INVOCATION_READ_TIMEOUT"      (unset → ~300 default)
pytest tests/unit → 354 passed
```

## Residual Risks

- Everything the fix did remains correct (row 600, library env 600 — all must stay above the 540 s envelope) but none of it was binding
- The no-retry rule + honest relays kept the failed sample truthful (the user gets an accurate message, never a silent kill)
- One chat turn per test consumed real desktop actions (Control Panel/dialogs open on the desktop — close at will)

## Recommendation

**Reopen the root cause once more — but the hunt is now one knob wide.** Re-run `/speckit.bug.assess` (or directly `/speckit.bug.fix`, since the assessment's mechanism section only needs this amendment): set `DIFY_BACKWARDS_INVOCATION_READ_TIMEOUT=600` and `DIFY_BACKWARDS_INVOCATION_WRITE_TIMEOUT=600` in the daemon environment (compose + `.env`, same pattern as the last cycle), recreate the daemon, and re-run the >300 s sample. Expected: the stream survives past 300 s to the sidecar's honest 540 s verdict or a real completion. The evidence chain is now complete: every other 300 has been raised and verified live; this is the last one in the hop sequence (api → daemon → plugin → **daemon relay** → api → sidecar).