# Bug Assessment: Raw honesty diagnostic blocks a valid default-printer confirmation

- **Slug**: blocked-because-no-verified-windows-default-printer-execution
- **Created**: 2026-11-21
- **Source**: Pasted text
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

> "Honesty check: MCP-ACTION display claims were blocked because no verified windows_default_printer execution returned display.status=displayed this turn."

The same message was found in live Dify data for conversation `46fcc668-9f26-40fc-998b-b0cc388b91d4` at `2026-11-21 05:59:46`. The preceding assistant turn presented manual default-printer steps and the exact offer. The user then replied:

> "yes, help to do it"

The assistant answer was the raw honesty diagnostic above instead of a result. Sidecar audit for that conversation contains a `windows_default_printer` `pending-confirmation` proposal followed by a blocked confirmation.

## Symptom

After the user accepts a stored default-printer proposal, no verified `windows_default_printer` execution reaches the honesty node. The model's visible answer is then replaced with an internal `Honesty check:` diagnostic rather than an actionable user response.

Expected: a plain confirm when the proposal is pending and unexpired, followed by the verified before/after, display, and screenshot result; or, if confirmation truly cannot run, a user-facing explanation that no change was made.

## Reproduction

1. Ask: “how to change my default printer to Microsoft Print to PDF on Windows 11”.
2. The assistant gives manual steps and ends with `Do you want me to do it automatically for you?`; a pending proposal exists.
3. Reply exactly: `yes, help to do it`.
4. The confirm call is not recognized as a verified execution; a visible display claim is blocked.
5. The final answer is the raw honesty diagnostic.

Current live reproduction with an already-active printer target also remains unreliable:

- One “yes” turn created another draft/offer instead of confirming the existing proposal.
- Confirm attempts returned `error`/`blocked` in the current conversation lifecycle, and the honesty node produced a related raw default-printer diagnostic.

## Suspected Code Paths

- `dify/AGIAssistant/AGI_Assistant.yml:2002` — the `honesty_check` JavaScript returns the literal `Honesty check:` strings, including the reported display-block message, as the final answer.
- `src/agentic_rag_mcp/mcp_action/service.py:348` — `McpActionService.handle` dispatches confirm/cancel and returns structured blocked/error results.
- `src/agentic_rag_mcp/mcp_action/service.py:725` — `_write_audit` records blocked/error outcomes, but the Dify-visible fallback is only the internal honesty diagnostic.
- `src/agentic_rag_mcp/mcp_action/state.py:83` — `resolve` enforces the immediately-following `N+1` turn and invalidates malformed or stale confirmations.
- `dify/AGIAssistant/AGI_Assistant.yml` — the MCP-ACTION prompt now states that a pending proposal must be confirmed on the next plain yes, but the agent still sometimes drafts again or submits an invalid confirmation.

## Root Cause Hypothesis

**Confidence: high for the observed guard symptom; medium-high for the exact upstream confirm failure.**

The honesty guard is doing its intended safety job: it refuses to certify a display claim when no verified `windows_default_printer` execution returned `display.status="displayed"` in the same turn. The defect is that the guard’s internal diagnostic is returned as the user-visible answer, and the preceding confirmation path was not reliable enough to produce a valid verified execution.

At `05:59:46`, the conversation had a pending proposal, but the follow-up confirmation was blocked. The earlier Dify tool-binding defect (raw template values inside a JSON-serialized tool list) could produce malformed runtime arguments and blocked confirmations; that root crash was fixed separately. However, the current reproduction still shows a yes-turn that can create a new draft rather than confirm, so the visible failure can recur even though the original string crash is gone.

## Proposed Remediation

**Preferred**: Keep the strict honesty protection, but never expose raw `Honesty check:` internals as the final answer.

1. In `honesty_check`, when a display claim is detected without verified display evidence:
   - If a real blocked/error `mcp_action` result exists, replace the model prose with a sanitized user-facing outcome from that result: “No automatic change was verified. The request was not executed. The manual steps remain available.”
   - If no execution occurred and no pending proposal exists, state that no change or display was verified and do not claim Settings was opened.
   - Keep the raw diagnostic available only in audit/logs, not in the chat answer.
2. Strengthen the confirmation-turn instruction in `AGI_Assistant.yml`: if the immediately preceding assistant answer ended with the exact MCP-Action offer, a plain affirmative such as “yes, help to do it” MUST call `mcp_action` with `phase="confirm"` and the stored conversation/turn, never `phase="draft"`. A new draft is allowed only for an explicit modified request.
3. Preserve the already-fixed Dify auto variable bindings (`auto: 0`, nested variable selectors); do not reintroduce template constants.
4. Add a live regression using the exact user phrase and an already-active test printer so no hardware setting changes.

**Alternatives**:
- Add a deterministic pre-router that maps an affirmative reply after a pending offer directly to `confirm`. This is more reliable but a larger topology change and was previously outside the approved scope.
- Return only a generic “not executed” message for all honesty failures. Simpler but loses useful partial/error information.

**Files likely to change**:
- `dify/AGIAssistant/AGI_Assistant.yml`
- `tests/unit/test_mcp_action_dsl.py`
- `tests/integration/test_mcp_action_dify_contract.py`

**Tests to add or update**:
- Offline honesty tests proving raw `Honesty check:` strings are never the final user answer and that blocked/error/partial evidence produces a sanitized actionable message.
- Live regression: initial default-printer how-to followed by exact `yes, help to do it`; assert a confirm call, no new draft, no raw honesty diagnostic, and already-active target remains unchanged.
- Regression for the newline/JSON binding bug remains required: `test_raw_query_with_newline_reaches_agent_without_tool_json_crash`.

## Risks & Considerations

- Changing the fallback wording must not allow fabricated display claims; only the user-facing representation changes, not the evidence gate.
- Prompt-side confirmation rules can conflict with generic “Want me to…?” follow-ups; scope them to a pending MCP-Action offer.
- Live confirmation tests must use an already-active printer or restore the original default in `finally`, and must never print a test page.
- Audit/logs must continue to exclude screenshot URLs, tokens, paths, bytes, and desktop text.

## Open Questions

- [NEEDS CLARIFICATION: The exact confirm inputs from the 05:59:46 run were not retained; whether it was blocked by malformed/expired turn arguments or by a missing proposal is inferred from the audit and the current reproduction.]
- [NEEDS CLARIFICATION: Decide whether the user-facing fallback should include the classification of the failed stage (verification/display/capture) or remain a shorter “not executed, manual steps only” message.]
