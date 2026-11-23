# Bug Fix: Reminder and finished message now live

- **Slug**: no-remind-message
- **Fixed**: 2026-11-23
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The wait reminder and the report-finished line were already present in the working tree but had never been deployed. The sidecar was rebuilt/recreated and both Dify apps were republished by explicit ID; live testing now shows the full HTML report and the reminder.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/mcp_action/service.py` | modified (pre-existing in working tree) | Health draft returns `_HEALTH_WAIT_NOTICE`. |
| `dify/AGIAssistant/AGI_Assistant.yml` | modified (pre-existing in working tree) | Finalizer injects the notice above the exact offer and appends the “System-Self-Check finished…” line after the full report. |
| `tests/unit/test_mcp_action_tool.py` | updated | Asserts the health draft notice. |
| `tests/unit/test_mcp_action_dsl.py` | updated | Asserts notice placement above the offer and the finished line at the end. |
| Sidecar container | redeployed | Recreated with `_HEALTH_WAIT_NOTICE`; 59 tools. |
| Dify apps | republished | `194e1edf-2eba-442c-b10b-231bebb79c37` and `7863fbe2-47f8-48c9-b096-6f7da8536b08`. |

## Tests Added or Updated

- `tests/unit/test_mcp_action_tool.py::test_health_draft_has_no_parameters_and_no_host_effects` — draft returns the wait notice.
- `tests/unit/test_mcp_action_dsl.py::test_offline_honesty_inserts_health_wait_notice_before_offer` — notice appears immediately above the exact offer.
- `tests/unit/test_mcp_action_dsl.py::test_offline_honesty_appends_the_full_html_report_verbatim` — full HTML followed by the finished line.

## Local Verification

- `pytest tests/unit/test_mcp_action_*.py tests/contract/test_mcp_contract.py -q` → **581 passed**.
- `ruff check ...` → **all checks passed**; `git diff --check` → **clean**.
- Sidecar probe → `_HEALTH_WAIT_NOTICE` present.
- Live exports → both apps contain `healthDraftNotice` and `System-Self-Check finished`.
- Live user test → **OK**: full HTML report and reminder message present.

## Deviations from Assessment

None. The assessment correctly identified a deployment-state gap; no additional finalizer logic was required in this pass.

## Follow-ups

- Commit the notice/finish changes when ready.
- If live output later loses the messages, re-check that the sidecar was redeployed **and** both explicit Dify app IDs were republished.
