# Bug Verification: Health status honesty parser accepts count-bearing WARN/FAIL summaries

- **Slug**: no-html-report-and-no-reliability-monitor-applet
- **Tested**: 2026-11-22
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The checked-in and freshly republished `honesty_check` no longer replaces the reported WARN summary: a live Dify health check returned the original answer, a 43-character report URL, and Reliability Monitor display evidence. The report and screenshot links both resolve.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | Executed the checked-in `honesty_check` with `health.status=warn`, score 72, and `Overall health: WARN ... Pass: 8 ...` | pass | No honesty replacement; answer retained; report link appended once. |
| New / updated tests | `.venv/bin/python -m pytest tests/unit/test_mcp_action_dsl.py -k 'offline_honesty' -q` | pass | 50 passed. |
| Regression suite | `.venv/bin/python -m pytest tests/unit/test_mcp_action_dsl.py -q` | pass | 113 passed. |
| Regression suite | `.venv/bin/python -m pytest tests/unit/test_mcp_action_*.py -q` | pass | 571 passed. |
| Lint / whitespace | `.venv/bin/ruff check tests/unit/test_mcp_action_dsl.py`; `git diff --check` | pass | All checks passed; diff clean. |
| Live Dify deploy | Exported both explicit app IDs after draft update + publish | pass | Both live apps now contain the new adjacent-status parser. |
| Live Dify health draft → confirm | Real Dify chat: health draft, then plain `yes` | pass | No honesty failure; `health.status=warn`, score 70; report URL present; Reliability Monitor display evidence present. |
| Report link | `curl` the returned report URL | pass | HTTP 200. |
| Screenshot link | `curl` the returned screenshot URL | pass | HTTP 200. |
| Reliability Monitor visual confirmation | Desktop observation | skipped | The tool reported `display.status=displayed`; no independent visual observation was made. |

## Output Excerpts

```text
Overall health: WARN. Score: 72. Pass: 8, Warn: 3, Fail: 1, Info: 2, Skip: 2. Disk and Reliability need review; HelpDesk can help with repairs. Reliability Monitor is open. Screenshot: captured. [Open the system health report](http://sidecar:8080/mcp-action/reports/HHH...)
REPRODUCTION_PASS
```

```text
DRAFT_ANSWER: ... Do you want me to do it automatically for you?
CONFIRM_ANSWER: ... Overall status warn; Score 70; 3 pass, 6 warn ... Reliability Monitor display: displayed ... [Open the system health report](http://localhost:28080/mcp-action/reports/52zJO2DY-Z-y08gaZ6YgA9zlKMt4DKVJpcFB9j8J-Wo)
HONESTY_FAILURE: False
REPORT_URLS: ['/mcp-action/reports/52zJO2DY-Z-y08gaZ6YgA9zlKMt4DKVJpcFB9j8J-Wo']
HAS_MONITOR_TEXT: True
report_http=200
screenshot_http=200
```

```text
50 passed, 63 deselected
113 passed
571 passed
All checks passed!
DIFF_CHECK_OK
```

## Residual Risks

- The live answer stream included raw `<​think>` reasoning text; this is separate from the honesty bug and may need a display/render follow-up.
- The report is temporary and expires after 15 minutes; the live proof is time-bound.
- Whether the Reliability Monitor window was independently observed remains unconfirmed; the tool reported `display.status=displayed` and the answer/guard path preserved that evidence.
- Other unrecognized summary formats could still be over-blocked; the parser now declines to guess when no explicit overall status is adjacent.

## Recommendation

Close the reported bug as verified end-to-end: the fixed parser is live on both apps, the original WARN summary survives, and the report/screenshot links resolve. Track the leaked `<​think>` text as a separate issue if it is visible in the chat UI.
