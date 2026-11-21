# Bug Verification: Default-printer yes-turn confirmation and sanitized honesty fallback

- **Slug**: blocked-because-no-verified-windows-default-printer-execution
- **Tested**: 2026-11-21
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original failure path no longer reproduces. A newline-bearing reply followed by `yes, help to do it` now executes the stored default-printer confirmation, displays Settings, and returns no raw `Honesty check:` diagnostic or replacement draft. Focused regressions and lint pass.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | `RUN_MCP_ACTION_DIFY_CONTRACT=1 .venv/bin/python -m pytest tests/integration/test_mcp_action_dify_contract.py -q -s -k raw_query_with_newline` | pass | Exact newline reply and yes phrase; 1 passed in 71.32s |
| New / updated tests | `.venv/bin/python -m pytest tests/unit/test_mcp_action_state.py tests/unit/test_mcp_action_tool.py tests/unit/test_mcp_action_dsl.py -q` | pass | 247 passed before the broader focused run |
| Regression suite | `.venv/bin/python -m pytest tests/unit/test_mcp_action_state.py tests/unit/test_mcp_action_tool.py tests/unit/test_mcp_action_dsl.py tests/unit/test_mcp_action_concurrency.py tests/contract/test_mcp_contract.py tests/contract/test_mcp_action_screenshot_route.py -q` | pass | 271 passed, 10 pre-existing warnings in 36.77s |
| Lint | `.venv/bin/python -m ruff check src/agentic_rag_mcp/mcp_action/state.py src/agentic_rag_mcp/mcp_action/service.py tests/unit/test_mcp_action_state.py tests/unit/test_mcp_action_tool.py tests/unit/test_mcp_action_dsl.py tests/integration/test_mcp_action_dify_contract.py` | pass | All checks passed |

Manual post-check: the live test targeted the already-active default printer, so the machine state remained unchanged. Final default plain-report check returned `Brother HL-L2375DW series (redirected 1)`. The temporary screenshot from the live test was removed; the container screenshot store reports 0 artifacts.

## Output Excerpts

```text
tests/unit/... + contract...:
271 passed, 10 warnings in 36.77s

live reproduction:
1 passed, 2 deselected in 71.32s (0:01:11)

ruff:
All checks passed!

container cleanup:
{'test_artifacts_removed': 1, 'remaining': 0}

final default:
Brother HL-L2375DW series (redirected 1)
```

## Residual Risks

- The live reproduction uses an already-active default, so it verifies confirmation/display honesty and no-change handling without exercising a setting mutation. Mutation performance and restoration were covered previously by the 20-sample benchmark and CDP acceptance runs.
- The fix narrows the sanitized fallback to the `windows_default_printer` path; Word-specific raw honesty text remains documented follow-up work.
- The full 1,233-test suite was not rerun in this verification step. The 271 focused tests cover every changed module and the adjacent contracts; the previously recorded full suite had only the three known baseline failures.
- Dify model wording remains probabilistic. The server-side affirmative classifier and confirm hint reduce reliance on prompt compliance, but live behavior should still be observed after any model or Dify upgrade.

## Recommendation

Close the bug — verified end-to-end for the reported failure path. Keep the Word fallback wording and full-suite baseline cleanup as separate follow-ups.
