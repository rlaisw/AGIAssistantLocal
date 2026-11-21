# Bug Fix: Default-printer yes-turn confirmation and sanitized honesty fallback

- **Slug**: blocked-because-no-verified-windows-default-printer-execution
- **Fixed**: 2026-11-21
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

A plain yes such as `yes, help to do it` is now recognized as confirmation, a yes-turn that incorrectly calls `draft` gets a non-mutating confirm hint instead of replacing the proposal, and default-printer display/execution honesty failures now return a user-facing no-change message rather than raw `Honesty check:` internals.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/mcp_action/state.py` | modified | Added `yes, help to do it` and equivalent short affirmatives to the bounded classifier; added non-consuming `peek()` and `is_affirmative()` APIs. |
| `src/agentic_rag_mcp/mcp_action/service.py` | modified | A plain-yes `draft` call with a next-turn pending proposal now returns a blocked `phase='confirm'` hint and leaves the proposal intact. |
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | Added `CONFIRMATION PRIORITY` to both approved prompts; replaced default-printer display/execution raw guard diagnostics with sanitized actionable text. |
| `tests/unit/test_mcp_action_state.py` | added cases | Pins the extended affirmative family while retaining modified-response rejection. |
| `tests/unit/test_mcp_action_tool.py` | added test | Pins non-mutating confirm hint and preservation of the stored proposal. |
| `tests/unit/test_mcp_action_dsl.py` | updated/added tests | Pins confirmation-priority prompt, sanitized default-printer fallbacks, and corrected the Word-with-default-evidence fixture. |
| `tests/integration/test_mcp_action_dify_contract.py` | updated test | Exact newline reply plus `yes, help to do it` must confirm an already-active default and never emit `Honesty check:` or a new pending draft. |

## Diff Highlights

```python
# state.py
if normalized in _AFFIRMATIVE or _AFFIRMATIVE_PHRASE.fullmatch(normalized):
    return "confirm"
```

```python
# service.py
if pending and dialogue_count == pending.created_dialogue_count + 1 and self.store.is_affirmative(query):
    return {"status": "blocked", "reason": "A proposal is pending. Call mcp_action with phase='confirm' ..."}
```

```javascript
// honesty_check, default-printer display fallback
return {result: 'No automatic change was verified. I did not change your default printer or open Windows printer settings. The manual steps above remain available; ask me if you want a fresh proposal.'};
```

## Tests Added or Updated

- `tests/unit/test_mcp_action_state.py::test_plain_affirmative_vocabulary_reserves` — now includes `yes, help to do it`, `yes, please do it`, `yes, go ahead`, `okay, do it`, and `sure, please do it`.
- `tests/unit/test_mcp_action_tool.py::test_plain_yes_draft_with_pending_returns_confirm_hint_and_keeps_proposal` — no host effect, no proposal replacement.
- `tests/unit/test_mcp_action_dsl.py::test_confirmation_priority_prevents_redraft_on_plain_yes` — both approved agents.
- `tests/unit/test_mcp_action_dsl.py::test_offline_honesty_ignores_hidden_think_claims_but_blocks_visible_claims` — default-printer fallbacks are sanitized user messages.
- `tests/integration/test_mcp_action_dify_contract.py::test_raw_query_with_newline_reaches_agent_without_tool_json_crash` — exact newline reply and yes phrase produce a verified confirm with Settings displayed.

## Local Verification

- Commands run: `.venv/bin/python -m pytest tests/unit/test_mcp_action_state.py tests/unit/test_mcp_action_tool.py tests/unit/test_mcp_action_dsl.py -q` → **247 passed**.
- Commands run: `.venv/bin/python -m pytest tests/unit/test_mcp_action_state.py tests/unit/test_mcp_action_tool.py tests/unit/test_mcp_action_dsl.py tests/unit/test_mcp_action_concurrency.py tests/contract/test_mcp_contract.py tests/contract/test_mcp_action_screenshot_route.py -q` → **271 passed, 10 warnings**.
- Ruff on changed state/service/tests → **all checks passed**.
- Deployment: `agentic_rag_mcp.deploy redeploy` → build/recreate/health/sync-tools all OK, **59 tools**.
- Dify: both explicit app IDs published with the updated DSL.
- Live regression: `RUN_MCP_ACTION_DIFY_CONTRACT=1 ... -k raw_query_with_newline` → **1 passed in 104.62s**.
- Manual/evidence check: already-active default remained unchanged; Settings was displayed; no `Honesty check:` answer; no replacement draft; temporary screenshot removed from the container store afterward.
- `ccc index`: 1,058 files listed, 0 errors, 28,531 chunks.
- Graphify manual guarded refresh: 10,996 nodes / 17,639 edges / 942 communities; aggregated HTML exported.

## Deviations from Assessment

The assessment focused on the prompt and honesty wording. Live reproduction exposed an additional root cause in scope: the server classifier did not recognize `yes, help to do it`, so even a correct confirm call would be blocked. The fix therefore expanded into `state.py` and `service.py` (the assessment's Files Likely list did not include them). The non-mutating draft hint was added to prevent the observed yes-turn re-draft behavior. Word-specific raw honesty fallbacks were intentionally left unchanged because this bug's failing path was `windows_default_printer`; generalizing Word fallback wording is follow-up work.

## Follow-ups

- Add `/speckit.bug.test` coverage for the exact yes phrase and sanitized fallback.
- Consider applying the same user-facing fallback wording to Word-specific display/execution honesty branches.
- Keep Dify auto-bound variable selectors (`auto: 0`, nested `type: variable`); never restore template constants.
- Re-run the live draft/cancel contract after any future Dify upgrade.
