# Bug Verification: all three prompts green — device manager opens a new window via direct mmc.exe

- **Slug**: some-success-some-unsuccess-test-open-applets-on-my-desktop-screen
- **Tested**: 2026-11-16T04:20:00+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: **verified** — the owner's exact three-prompt battery passes with window-presence proof for each

## Summary

The silent device-manager failure is gone: "open device manager" now produces a **new Device Manager window** (mmc count 2 → 3, the fix's direct-launch form), the installed programs applet opens its window, and power options opens its window — all through the chat tool path on the rebuilt container, with the suite and lint green and no regressions.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Prompt 1: device manager (the failing case) | `windows_mcp_open_settings("device manager")` + before/after mmc count | **pass** | ok, direct `mmc.exe` form; **mmc 2 → 3 (new window)** — the pre-fix form produced zero windows across three attempts |
| Prompt 2: installed programs applet | `windows_mcp_open_settings("installed programs applet")` + window check | **pass** | ok in 10.0 s; "Programs and Features" window present (count 1) |
| Prompt 3: power options | `windows_mcp_open_settings("power options")` + window check | **pass** | ok in 1.5 s; "Power Options" window present (count 1) |
| New / updated tests | `pytest tests/unit/test_windows_mcp_applets.py` | **pass** | 27 passed incl. the device-manager direct-form pin |
| Regression suite | `pytest tests/unit` (full) | **pass** | 715 passed, 0 failed |
| Lint | `ruff check` (changed files) | **pass** | All checks passed |

## Output Excerpts

```
prompt 1:  ok, "Start-Process mmc.exe -ArgumentList 'devmgmt.msc'" | mmc 2 -> 3 (new window)
prompt 2:  ok 10.0s | Programs and Features window count 1
prompt 3:  ok 1.5s  | Power Options window count 1
pytest tests/unit → 715 passed
```

## Residual Risks

- Two Device Manager windows from the A/B probes remain on the desktop (cannot be closed from WSL — access denied in the owner's console session); close at will.
- The prompt-1 open took 59.6 s wall time — the USER_CONTROL deferral retries while the desktop user is active; the window did open within the extended (~64 s) retry window. Expected behavior, improved by the earlier retry-widening; hands-off-for-10 s remains the practical rhythm.
- The console-session `control.exe → mmc.exe` silent-die quirk is worked around per-host; the upstream service's launch context is unchanged (any future `.msc` inherits the working direct form automatically).

## Recommendation

**Close the bug — verified end-to-end on the owner's exact battery.** All three applets now open visibly with per-window proof, the pin locks the working launch form, and the full suite is green. No follow-up needed beyond closing the probe windows at will.
