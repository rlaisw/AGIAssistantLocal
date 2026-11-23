# Bug Fix: Health answer uses the saved report file path instead of the temporary URL

- **Slug**: wrong-report-url-correct-is-temp-selfcheck-html
- **Fixed**: 2026-11-22
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The health result now makes `C:\Temp\selfcheck.html` the visible report reference when the host file is written. The finalizer substitutes that path for the temporary `/mcp-action/reports/` URL, suppresses the URL append, and keeps the complete HTML report.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/mcp_action/service.py` | modified | `report.usage` now instructs the assistant to present `report.host_path` and not a `/mcp-action/reports/` URL when the host file is written. |
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | HEALTH RESULT prompt and tool description prefer the host path; finalizer replaces the exact temporary URL (and markdown link) with the path and does not re-append the URL. |
| `tests/unit/test_mcp_action_dsl.py` | updated | Prompt now requires `report.host_path`; finalizer tests assert the path appears once and the temporary URL is absent. Added publication-failed path fallback coverage. |
| `AGENTS.md`, `README.md`, `ai-chat-landing/AGENTS.md`, `specs/048-system-health-check/{spec.md,data-model.md,contracts/system-health-check.md,test-report.md}` | modified | Documented the path-first visible reference and internal URL fallback. |

## Diff Highlights

```python
"usage": (
    "When report.host_path_status is 'written', present "
    "report.host_path once as 'Complete report file: <path>' "
    "and do not include a /mcp-action/reports/ URL. "
    ...
)
```

```js
if (healthReportHostPath && healthReportUrl) {
  var healthLink = '[Open the system health report](' + healthReportUrl + ')';
  answer = String(answer).split(healthLink).join('Complete report file: ' + healthReportHostPath);
  answer = String(answer).split(healthReportUrl).join(healthReportHostPath);
  visible = String(answer);
}
```

## Tests Added or Updated

- `tests/unit/test_mcp_action_dsl.py::test_offline_honesty_appends_a_missing_report_file_path` — path is appended once; URL absent.
- `test_offline_honesty_accepts_warn_overall_with_count_labels` / `..._fail_...` — count-bearing summaries use the path, not the URL.
- `test_offline_honesty_blocks_a_forged_health_report_url` — forged URL removed; path shown.
- `test_offline_honesty_blocks_a_report_url_when_publication_failed` — path fallback when publication failed but the host file exists.
- `test_health_check_prompt_requires_real_report_link_evidence` — now also requires `report.host_path` and forbids the URL when written.

## Local Verification

- `pytest tests/unit/test_mcp_action_dsl.py -q` → **115 passed**.
- `pytest tests/unit/test_mcp_action_*.py tests/contract/test_mcp_contract.py -q` → **579 passed**.
- `ruff check ...` → **all checks passed**; `git diff --check` → **clean**.
- Sidecar redeployed (59 tools); both Dify apps republished by explicit ID.
- Live Dify draft → `yes`: `confirm=ok`, answer contains `C:\Temp\selfcheck.html`, **zero** `/mcp-action/reports/` URLs, one complete `<!DOCTYPE html>…</html>` report.
- Host file: `C:\Temp\selfcheck.html`, **3,806 bytes**, timestamp refreshed.

## Deviations from Assessment

- The temporary URL remains in the internal tool result as a fallback; only the visible answer is path-first. This matches the assessment's preferred alternative.
- The first live confirm attempt failed with “malformed health data” after ~36s; a retry after the host settled passed. This was transient host execution latency, not the path change.
- No E2E harness test currently renders the Dify finalizer; the finalizer is covered by the DSL unit tests and the live chat check.

## Follow-ups

- Decide whether to remove the temporary URL from the tool result entirely (assessment open question).
- Add a CDP or live-chat assertion that the final rendered answer contains no `/mcp-action/reports/` URL.
- Keep the host-path fallback honest when `host_path_status` is not `written`.
