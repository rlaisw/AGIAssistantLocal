# Bug Verification: Reminder and finished message are live

- **Slug**: no-remind-message
- **Tested**: 2026-11-23
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The reminder appears above the health-check offer and the completed answer ends with the report-finished line. The owner’s live test found the full HTML report and the reminder message; the sidecar and both Dify apps contain the deployed code.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | Owner live health-check test | pass | Full HTML report and reminder message found. |
| Deployed sidecar | `docker exec agentic-rag python -c ...` | pass | `_HEALTH_WAIT_NOTICE` present. |
| Live app exports | Export both explicit app IDs | pass | Both contain `healthDraftNotice` and `System-Self-Check finished`. |
| New / updated tests | `pytest tests/unit/test_mcp_action_dsl.py tests/unit/test_mcp_action_tool.py -q` | pass | **177 passed**. |
| Regression suite | `pytest tests/unit/test_mcp_action_*.py tests/contract/test_mcp_contract.py -q` | pass | **581 passed** (fix run). |
| Lint / whitespace | `ruff check ...`; `git diff --check` | pass | All checks passed; diff clean. |

## Output Excerpts

```text
177 passed in 1.87s
sidecar_notice True
194e1edf-2eba-442c-b10b-231bebb79c37 notice True finished True
7863fbe2-47f8-48c9-b096-6f7da8536b08 notice True finished True
All checks passed!
DIFF_CHECK_OK
```

## Residual Risks

- The messages depend on both the sidecar redeploy and republishing both explicit Dify app IDs; a partial deploy can reintroduce the bug.
- No automated CDP assertion for the rendered reminder order was added; the DSL unit test pins the order.
- Windows-MCP control must remain available for the live health execution.

## Recommendation

Close the bug as verified. The owner confirmed the live result, both app exports contain the new logic, and the focused/regression tests pass.
