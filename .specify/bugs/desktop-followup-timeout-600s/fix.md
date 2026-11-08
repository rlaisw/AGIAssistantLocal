# Bug Fix: 540-second honest envelope on the launch lane — the sidecar's verdict now always precedes the daemon's silent kill

- **Slug**: `desktop-followup-timeout-600s`
- **Fixed**: 2026-11-08T09:00+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — live-verified on the exact failing request

## Summary

The launch lane's Hermes budget is capped at **540 s** (90% of the Dify plugin-daemon's ~600 s tool-kill timer) via a `timeout_s` override threaded from the tool through `run_task` to the httpx call — so a too-long desktop-followup turn now ends with the sidecar's honest, auditable "Hermes did not finish within 540s — try a smaller task" instead of the daemon's silent mid-flight kill (no verdict, no audit). LAUNCH_INSTRUCTIONS additionally gained the FASTEST-PATH NAVIGATION rule to steer the agent away from click-walking toward the cap.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | `run_task(..., timeout_s=None)` override: budget = override or `cfg.hermes_timeout_s`; the honest timeout error reports the effective budget; LAUNCH_INSTRUCTIONS + FASTEST-PATH NAVIGATION rule (direct routes via consent-gated desktop actions beat click-walking; end honestly if no fast path is visible within two snapshots) |
| `src/agentic_rag_mcp/server.py` | modified | `hermes_launch_app` passes `timeout_s=540.0` to `run_task` and `budget=540.0` to the keepalive wrapper (why-comment included) |
| `tests/unit/test_hermes_launch_tool.py` | +3 tests | budget-is-under-kill-timer (source pin), `run_task` override reaching the error message (mocked timeout), instruction guard for the fastest-path text |

## Diff Highlights (optional)

```python
# server.py — the launch lane:
outcome = await _await_with_keepalive(
    lambda: _hermes_run_task(cfg, launch_directive,
                              instructions=_HERMES_LAUNCH_INSTRUCTIONS,
                              timeout_s=540.0), ctx, budget=540.0)
# hermes_client.py — honest error reports the effective budget:
except httpx.TimeoutException:
    return {"ok": False, "error": f"error:Hermes did not finish within "
            f"{budget:.0f}s — try a smaller task"}
```

## Tests Added or Updated

- `test_launch_lane_budget_is_under_daemon_kill_timer`, `test_run_task_accepts_timeout_override`, `test_launch_instructions_pin_fastest_path_guidance` — 51 launch-suite tests pass; full suite **354 passed**; `ruff` — only the 5 pre-existing I001s

## Local Verification

- `deploy redeploy` → ok
- **Live (08:47–08:56): the exact 08:17 failing request** — `open windows control panel , display my network adapter` → at **540 s** the turn returned `status: error` with the honest verdict *"Hermes did not finish within 540s — try a smaller task"* and a **full audit entry** (08:56:55, decision=error). Pre-fix, this identical request died at 601.9 s with `PluginDaemonInternalServerError`, an empty answer, and **no audit trail** — the honest envelope now closes first, exactly as designed.

## Deviations from Assessment

- None on the mechanism. One honest observation: this particular navigation still consumed the full budget (the agent found no fast path this turn) — the honest 540 s verdict is the *designed outcome* for such turns; the fastest-path guidance's effect on turn duration will show across natural turns, and the user can always split requests ("open control panel", then "display my adapter") which the guidance now recommends explicitly when it can't find a fast route.

## Follow-ups

- Watch natural desktop-followup turns: the guidance should pull most under the cap; if 540 s verdicts recur on a common phrasing, that's a navigation-quality finding (extend the known-direct-routes hints), not a budget problem
- The same daemon-kill race exists for the office lane (600 s Hermes budget) — no kills observed there yet; if one appears, thread the same `timeout_s` override through `hermes_office_task`/`hermes_file_task` (the mechanism now exists; it's a two-line change per lane)
- WindowsMCP's slow UIA captures (20–26 s snapshots) are the biggest turn-time sink; `WINDOWS_MCP_EXCLUDE_PROCESSES` is the knob if a pathological app is ever identified
