# Bug Fix: Reliability Monitor now opens via control.exe pageReliabilityView

- **Slug**: show-full-html-report-and-page-reliability-view
- **Fixed**: 2026-11-22
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The reviewed settings launcher for Reliability Monitor now uses `control.exe /name Microsoft.ActionCenter /page pageReliabilityView` instead of `mmc perfmon.msc /rel`, and the health display verification waits for the Control Panel "Reliability Monitor" window. The full-HTML-in-chat request was intentionally not implemented (it conflicts with FR-017 and exposes PII).

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/windows_mcp/open.py` | modified | `perfmon_rel` launch command switched to the Control Panel ActionCenter form. |
| `src/agentic_rag_mcp/mcp_action/service.py` | modified | `show_reliability_monitor()` `WaitFor` now targets `Reliability Monitor` window/title instead of `Performance Monitor`. |
| `tests/unit/test_windows_mcp_applets.py` | updated | `test_reliability_monitor_launch_form` asserts the new control.exe command. |

## Diff Highlights

```python
command = ("Start-Process control.exe -ArgumentList "
           "'/name','Microsoft.ActionCenter','/page','pageReliabilityView'")
```

```python
"window_name": "Reliability Monitor",
...
and "reliability monitor" in text.casefold()
```

## Tests Added or Updated

- `tests/unit/test_windows_mcp_applets.py::test_reliability_monitor_launch_form` — pins the new Control Panel launch command.
- Existing display tests in `tests/unit/test_mcp_action_tool.py` remain green (they mock the display and are launcher-agnostic).

## Local Verification

- `.venv/bin/python -m pytest tests/unit/test_windows_mcp_applets.py tests/unit/test_mcp_action_tool.py -q` → **90 passed**.
- `.venv/bin/ruff check src/agentic_rag_mcp/windows_mcp/open.py src/agentic_rag_mcp/mcp_action/service.py tests/unit/test_windows_mcp_applets.py` → **all checks passed**.
- `git diff --check` → **clean**.
- `RUN_MCP_ACTION_E2E=1 RUN_SYSTEM_HEALTH_CHECK_E2E=1 ... -k health_e04` → **1 passed**; `display=displayed`, `screenshot=captured`, `report=published`.
- `python -m agentic_rag_mcp.deploy redeploy` → **ok: 6 steps**; container recreated, 59 tools.
- Live Dify health draft → context → `yes`: **no honesty failure**, report URL present (43 chars, HTTP 200), Reliability Monitor display text present.

## Deviations from Assessment

- Kept `targets.py` identifier `perfmon.msc` unchanged (the `perfmon_rel` kind is matched first, so the identifier is only a label). Renaming it to reflect the Control Panel page is cosmetic and left as a follow-up.
- `test_health_e13_read_only_invariants_are_preserved` failed on the service-state digest (a Windows service transitioned during the run). This is unrelated to the launcher change and is a pre-existing flake risk of the T040 digest approach, tracked as a follow-up.
- The "show the full HTML report" part was not implemented: FR-017 forbids pasting report HTML and the report contains PII (login, email, IP, serial, SID, password dates).

## Follow-ups

- Make H-E13 service evidence stable by comparing service identity/startup state rather than transient running status, or by re-reading on retry (separate bug).
- Decide at spec level whether the full HTML report should be openable in a browser (it must remain a URL, not chat text).
- Optionally rename the `reliability monitor` target identifier to reflect the Control Panel page.
