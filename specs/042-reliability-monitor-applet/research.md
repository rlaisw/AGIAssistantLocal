# Research: Reliability Monitor applet (042)

Created: 2026-11-16. All findings verified LIVE during planning.

## R1: perfmon.exe is the new silent-die case — the mmc-hosted form is the fix

**Decision**: the reliability-monitor target launches via `Start-Process mmc.exe -ArgumentList 'perfmon.msc','/rel'` (the per-host launch form added to the tier-1 launcher alongside the `.msc` direct form).

**Live evidence (A/B, 2026-11-16)**:
- `Start-Process perfmon.exe -ArgumentList '/rel'` → **ok at the PowerShell layer, process exits instantly** (`HasExited: True`, no crash event in the Application log, no window). The same silent-die class as the `.msc`-via-control case — plain perfmon too (`Start-Process perfmon.exe -PassThru` → exits: True). This is OS-level behavior on this build (26200): `perfmon.exe` is a thin launcher that hands off to mmc and self-exits; from the service's context the handoff loses the window.
- `Start-Process mmc.exe -ArgumentList 'perfmon.msc','/rel'` from interop → **"Performance Monitor" mmc windows confirmed in session 1** (Reliability Monitor is perfmon.msc's `/rel` view).
- The same mmc form through the **service's PowerShell tool → executed**, and interop confirms a new "Performance Monitor" mmc window (PID 21896, session 1) on screen — the service-context form works.
- The earlier `cmd /c perfmon /rel` probe was blocked by the desktop-activity deferral (the honest envelope), not the launch form — discarded.

**Alternatives considered**: the plain `perfmon /rel` the owner named — verified dead in this context (silent-die); the cmd/control indirection — same class of failure as the device-manager case. The mmc-hosted form is the third proven per-host form (after `.msc` direct and the cpl forms).

## R2: Scope decision confirmed (clarify, Option A)

**Decision**: a new target on the existing `windows_mcp_open_settings` surface — one entry ("reliability monitor") plus synonyms ("reliability history", "stability monitor") in the reviewed inventory; the launcher gains the per-host `perfmon.msc /rel` form; everything else (ask-back, audit class `windows-mcp-open`, honest envelopes, hands-off guidance) inherited unchanged.

## R3: Verification method

**Decision**: window-presence proof mirrors the applet sweeps — after the open, a "Performance Monitor" titled mmc window must be present in session 1 (title check via the service's own PowerShell path or interop). The chart-fills-later behavior is documented (the window opens before the reliability chart computes; the relay never claims data readiness).

**Note on naming**: perfmon.msc's window titles as "Performance Monitor" even with `/rel` (the Reliability view is a page within it) — the target's display name stays "reliability monitor"; the window check matches `Performance` in the title.
