# Bug Verification: Health answer uses C:\Temp\selfcheck.html, not the temporary report URL

- **Slug**: wrong-report-url-correct-is-temp-selfcheck-html
- **Tested**: 2026-11-22
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

A valid published report URL in the answer is now replaced by `C:\Temp\selfcheck.html`; the visible answer contains no `/mcp-action/reports/` URL and still includes the full HTML report. The live Dify confirm passed with `confirm=ok`.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | Ran the checked-in `honesty_check` with the real published `report_url` in `Report(...)` | pass | Output `Report(C:\Temp\selfcheck.html)`; no `/mcp-action/reports/`; full HTML retained. |
| Live reproduction | Dify health draft → `yes` on the deployed sidecar | pass | `confirm=ok`; path present; **0** report URLs; one complete HTML document; no honesty replacement. |
| New / updated tests | `.venv/bin/python -m pytest tests/unit/test_mcp_action_dsl.py -q` | pass | 115 passed. |
| Regression suite | `.venv/bin/python -m pytest tests/unit/test_mcp_action_*.py tests/contract/test_mcp_contract.py -q` | pass | 579 passed. |
| Lint / whitespace | `ruff check ...`; `git diff --check` | pass | All checks passed; diff clean. |
| Host report file | `stat /mnt/c/Temp/selfcheck.html` | pass | 3,806 bytes, refreshed. |

## Output Excerpts

```text
Overall: WARN. Report(C:\Temp\selfcheck.html). HelpDesk can help with repairs.

<!DOCTYPE html><html><body>FULL</body></html>
HAS_PATH True
HAS_URL False
HAS_FULL_HTML True
REPRODUCTION_PASS
```

```text
calls [('confirm', 'ok')]
len 9847 honesty False
path True urls []
doctype True closing True
```

```text
115 passed
579 passed
All checks passed!
DIFF_CHECK_OK
```

## Residual Risks

- The temporary URL remains in the internal tool result as a fallback; the visible answer is path-first. Removing it from the result entirely is still an open assessment question.
- Two earlier live confirm attempts failed with “malformed health data” after ~36s of host latency; a retry passed. That is an unrelated host-latency flake, not the path change.
- No CDP/live rendered-answer assertion was added; the live chat check inspected the streamed answer directly.
- The host file path is Windows-specific; the chat UI must show it as text.

## Recommendation

Close the bug as verified: the visible report reference is now `C:\Temp\selfcheck.html`, the temporary URL is absent from the answer, and the full HTML remains. Track the internal-URL fallback and host-latency flake separately if desired.
