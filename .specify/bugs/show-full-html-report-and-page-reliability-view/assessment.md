# Bug Assessment: Reliability Monitor should open via control.exe pageReliabilityView

- **Slug**: show-full-html-report-and-page-reliability-view
- **Created**: 2026-11-22
- **Source**: pasted text
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

The user pasted the full HTML health report and a screenshot of the Control Panel **Reliability Monitor** page, then asked for two things:

> "not full html report and add this command
> Start-Process control.exe -ArgumentList '/name','Microsoft.ActionCenter','/page','pageReliabilityView'"

The health check currently opens Reliability Monitor through `mmc perfmon.msc /rel`; the user wants the Control Panel ActionCenter `pageReliabilityView` surface opened instead, and expects the full HTML report to be shown.

## Symptom

- The chat reply does not include the full HTML report content (only a summary plus a report URL and screenshot).
- Reliability Monitor is opened, but via the Performance Monitor console path rather than the requested `control.exe ... Microsoft.ActionCenter ... pageReliabilityView` page.
- Expected: open the exact Control Panel Reliability Monitor page with the command the user supplied, and (per the user) show the full report.

## Reproduction

1. Run a health check and confirm it.
2. Observe the Reliability Monitor launch command (audit/outcome) is `Start-Process mmc.exe -ArgumentList 'perfmon.msc','/rel'`.
3. Expected per request: `Start-Process control.exe -ArgumentList '/name','Microsoft.ActionCenter','/page','pageReliabilityView'`.

[NEEDS CLARIFICATION: the "not full html report" part conflicts with spec FR-017, which forbids dumping the full HTML report as chat text; see below.]

## Suspected Code Paths

- `src/agentic_rag_mcp/windows_mcp/targets.py:47-49` — `"reliability monitor"`/`"reliability history"`/`"stability monitor"` map to kind `perfmon_rel` / identifier `perfmon.msc`.
- `src/agentic_rag_mcp/windows_mcp/open.py:42-44` — the `perfmon_rel` branch builds `Start-Process mmc.exe -ArgumentList 'perfmon.msc','/rel'`; this is the launcher to replace.
- `src/agentic_rag_mcp/mcp_action/service.py:171-192` — `show_reliability_monitor()` verifies the window via `WaitFor` with `window_name: "Performance Monitor"` and text `"performance monitor"`; the Control Panel page title differs, so verification must be updated with the launcher change.
- `tests/unit/test_windows_mcp_applets.py:43-54` — `test_reliability_monitor_launch_form` pins the current `mmc.exe perfmon.msc /rel` command.

## Root Cause Hypothesis

Confidence: **high**. The reviewed settings launcher chooses the `perfmon_rel` launch form that was live-proven for the service context (spec 042 research R1: plain `perfmon /rel` silently exits). It is not the surface the user asked for. The health-check display verification then waits for a "Performance Monitor" window that matches the mmc console, not the Control Panel `Security and Maintenance > Reliability Monitor` page. Changing the launch form requires changing both the command and the verification window/title.

## Proposed Remediation

**Preferred**: Replace the `perfmon_rel` launch command in `open.py` with the user-supplied Control Panel form:

```powershell
Start-Process control.exe -ArgumentList '/name','Microsoft.ActionCenter','/page','pageReliabilityView'
```

Then update `show_reliability_monitor()` verification to wait for the Control Panel Reliability Monitor window (e.g. `window_name: "Reliability Monitor"` and text `"Reliability Monitor"` or `"Security and Maintenance"`) instead of `"Performance Monitor"`. Update `tests/unit/test_windows_mcp_applets.py` to assert the new command. Confirm the exact window title live before pinning it, and run the owner-present H-E15 display E2E to verify the Control Panel page appears.

**Alternatives**:
- Keep `perfmon.msc` but add a second reviewed target/kind for the Control Panel page. Cleaner separation but adds a new target and more test surface.
- Open the HTML report in the default browser as an additional display step. Useful, but separate from this bug and does not satisfy the user's "show full report" wording (the report stays a URL, not chat text).

**Files likely to change**:
- `src/agentic_rag_mcp/windows_mcp/open.py`
- `src/agentic_rag_mcp/mcp_action/service.py`
- `tests/unit/test_windows_mcp_applets.py`
- possibly `tests/unit/test_mcp_action_tool.py` / integration health display assertions

**Tests to add or update**:
- Update `test_reliability_monitor_launch_form` expected command to the `control.exe ... pageReliabilityView` form.
- Update any service-level display test that expects the `WaitFor "Performance Monitor"` window/text.
- Add an assertion that the health display outcome references the Control Panel Reliability Monitor window.

## Risks & Considerations

- **Do NOT paste the full HTML report into chat.** FR-017 forbids it, and the pasted report contains PII (login, email, IP, serial number, SID, password-expiry dates). Dumping it into chat would violate FR-014/SC-006 (audit/log privacy) and expose sensitive data in the transcript.
- The `control.exe ... /page pageReliabilityView` form opens the Control Panel page; its window title must be confirmed live before pinning the `WaitFor` condition. A wrong title makes the display outcome `unverified` or `attempted-but-failed`.
- Changing the launch form is a reviewed desktop action; it must remain read-only and must not alter the system.
- If the Control Panel form does not open reliably from the service context (mirrored-network/console-session caveats), it may need an `App switch`/foreground step; the E2E must confirm.

## Open Questions

- [NEEDS CLARIFICATION: is "show the full HTML report" a request to paste it in chat (which FR-017 forbids), or to open the report URL in a browser?]
- [NEEDS CLARIFICATION: exact window title of the Control Panel Reliability Monitor page on the target machine.]
