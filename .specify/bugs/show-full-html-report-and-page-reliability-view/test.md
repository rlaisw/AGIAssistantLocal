# Bug Verification: Reliability Monitor opens via control.exe pageReliabilityView

- **Slug**: show-full-html-report-and-page-reliability-view
- **Tested**: 2026-11-22
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The Reliability Monitor now opens through `control.exe /name Microsoft.ActionCenter /page pageReliabilityView` and the health display verifies the Control Panel window. A live health check reported `display=displayed`, published the report, and captured a screenshot; no honesty failure and a live Dify confirm retained the report link and Reliability Monitor text.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Launcher reproduction | `tests/unit/test_windows_mcp_applets.py::test_reliability_monitor_launch_form` | pass | Asserts the `control.exe ... pageReliabilityView` command (no longer `mmc perfmon.msc /rel`). |
| Live display E2E | `RUN_MCP_ACTION_E2E=1 RUN_SYSTEM_HEALTH_CHECK_E2E=1 pytest ... -k health_e04` | pass | `status=ok`; `report=published`; `display=displayed`; `screenshot=captured`; report 3809 bytes. |
| Regression suite | `pytest tests/unit/test_windows_mcp_applets.py tests/unit/test_mcp_action_tool.py -q` | pass | 90 passed. |
| Lint / whitespace | `ruff check ...`; `git diff --check` | pass | All checks passed; diff clean. |
| Live Dify health confirm | Draft → context → `yes` (deployed sidecar) | pass | No honesty failure; 43-char report URL (HTTP 200); Reliability Monitor text present. |
| Sidecar deploy | `python -m agentic_rag_mcp.deploy redeploy` | pass | Container recreated; 59 tools. |
| Full HTML in chat | Not implemented | not-run | Intentionally excluded — FR-017 forbids pasting report HTML; the report contains PII. |

## Output Excerpts

```text
Health outcome: status=ok; health=warn:70; report=published; display=displayed; screenshot=captured
Health audit: rows=5; executed=True; summary-only=true; tokens=absent; pii=absent
Health E04: report_source=host-store; report_bytes=3809
Health cleanup: owned_run_artifacts_removed=0; remaining=none; host_settings=unchanged
1 passed, 42 deselected in 27.23s
```

```text
90 passed
All checks passed!
DIFF_CHECK_OK
```

## Residual Risks

- `test_health_e13_read_only_invariants_are_preserved` is flaky on the service-state digest when a Windows service changes state mid-run; this is unrelated to the launcher and is tracked as a separate follow-up.
- The Control Panel window title "Reliability Monitor" was confirmed by the live E04 run; if Windows localizes it, the `WaitFor` condition may need a localized string.
- The "show the full HTML report" request remains unimplemented by design (FR-017 + PII); whether to open it in a browser is a spec decision.

## Recommendation

Close the bug as verified end-to-end. The launcher uses the requested `control.exe ... pageReliabilityView` form and the live health check preserves report, display, and screenshot evidence. Track the H-E13 service-digest flake separately.
