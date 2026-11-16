# Bug Fix: per-host-process launch forms — device manager opens via direct mmc.exe

- **Slug**: some-success-some-unsuccess-test-open-applets-on-my-desktop-screen
- **Fixed**: 2026-11-16T04:10:00+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — the change was made during the assessment's live A/B diagnosis (documented there as a deviation); this phase verifies, formalizes, and re-runs the owner's exact three-prompt battery

## Summary

The launcher now uses three per-host-process command forms: `.msc` targets (device manager, the only one) launch via direct `Start-Process mmc.exe -ArgumentList '<msc>'` — the form proven live to put the window in the visible session — while `.cpl` applets keep the proven `cmd /c control` form and Settings pages keep the proven `cmd /c start ms-settings:` form. The old `cmd /c control` indirection made mmc.exe die silently in the service's context on the console session, so "open device manager" reported executed with no window ever appearing.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/windows_mcp/open.py` | modified | the three-form launcher: `.msc` → `Start-Process mmc.exe -ArgumentList '<msc>'`; `.cpl` → `Start-Process cmd.exe -ArgumentList '/c','control','<id>'`; Settings → `cmd /c start ms-settings:<page>`; each labeled with the live evidence |
| `tests/unit/test_windows_mcp_applets.py` | updated pin | `test_launcher_executes_identifier_only` — device manager pins the direct mmc.exe form |

## Diff Highlights (optional)

```python
identifier = target["identifier"]
if identifier.endswith(".msc"):
    command = f"Start-Process mmc.exe -ArgumentList '{identifier}'"
elif target["kind"] == "cpl":
    command = (f"Start-Process cmd.exe -ArgumentList '/c','control',"
               f"'{identifier}'")
else:
    command = (f"Start-Process cmd.exe -ArgumentList '/c','start',"
               f"'ms-settings:{identifier}'")
```

## Tests Added or Updated

- `test_launcher_executes_identifier_only` — the device-manager case pins `Start-Process mmc.exe -ArgumentList 'devmgmt.msc'` (regression pin for the silent-die form); the other-target pins unchanged (their forms proven).

## Local Verification

- Commands run: `pytest tests/unit/test_windows_mcp_applets.py` → **27 passed**; full `pytest tests/unit` → **715 passed, 0 failed**; `ruff check` → clean; `deploy redeploy` → rebuilt (58 tools).
- **Live A/B evidence (assessment phase)**: `cmd /c control devmgmt.msc` via the service → success at the PowerShell layer, zero mmc processes; `Start-Process explorer.exe devmgmt.msc` → same, no window; `Start-Process mmc.exe -ArgumentList 'devmgmt.msc'` → mmc in session 1, window "Device Manager".
- **Post-fix live verify through the chat tool**: `windows_mcp_open_settings(target="device manager")` → **ok in 1.4 s**, new "Device Manager" window (PID 24392, session 1) confirmed on screen.

## Deviations from Assessment

- The code change was applied during the assessment phase rather than this one — the live A/B that isolated the root cause was itself the fix's validation. Documented in the assessment; no further deviation: the change matches the preferred remediation exactly.

## Follow-ups

- `/speckit.bug.test` should re-run the owner's exact three-prompt battery (device manager / installed programs applet / power options) — all three expected green now.
- The residual probe windows (two Device Manager mmc instances from the A/B) close at will.
- Future `.msc` additions to the target list inherit the working form automatically; `.cpl`/Settings forms untouched.
