# Bug Assessment: kimi-k3 emits the tool call as literal text — `<invoke>` XML leaks into the chat and nothing dispatches

- **Slug**: `hermes-run-command-with-task-not-work`
- **Created**: 2026-11-09T09:35+00:00
- **Source**: pasted text (the user's chat transcript showing two dead-ended asks and the leaked `<invoke>` XML)
- **Verdict**: valid — a new, precisely diagnosable failure shape of the no-emit family: the model constructed the **correct** tool call (right tool, right args) but emitted it as **literal text** (`<invoke name="hermes_run_command">…</invoke>`), so nothing dispatched and the raw XML reached the user's chat. Our layer can detect this exactly and replace it with an honest notice.
- **Severity**: medium — user-visible dead-end on legitimate asks plus raw markup leaking into the chat; clusters on the failure-laden conversation (`e4a98f05` — the same conversation worked end-to-end for ip/hostname/locale in fresh contexts 20 minutes earlier); no data risk (nothing ran).

## Report (verbatim or summarized)

> "show my current system info." → *"I'll check that for you."* — and nothing else.
>
> "show my system locale" → *"I'll check that for you."* followed by the raw text:
> `<invoke name="hermes_run_command"> <parameter name="conversation_id">e4a98f05-…</parameter> <parameter name="task">show my system locale</parameter> </invoke>` visible in the chat.

## Symptom

A user asks for an allowlisted diagnostic; the relay says "I'll check that for you", the model writes the tool invocation as literal text instead of the structured function-calling channel, no call executes, and (in the leak shape) the raw `<invoke>` XML appears in the user's chat. Expected: the call dispatches and the command's real result is relayed — or, failing that, an honest dispatch-failure notice, never dangling text with leaked markup.

## Reproduction (forensically confirmed in conversation `e4a98f05`, 2026-11-09)

1. 09:26:11 "show my current system info." → agent node 3 items (no call); stored text ends at "I'll check that for you." — the **silent no-emit** shape.
2. 09:27:28 "show my system locale" → 3 items (no call); stored text contains the literal `<invoke name="hermes_run_command">` block with **correct args** (conversation_id + task) after "I'll check that for you." — the **leak** shape, exactly what the user pasted.
3. Control: the same asks in fresh conversations emitted structured calls and completed end-to-end minutes earlier (real `ipconfig`, `hostname`, and the locale→`systeminfo` turn with genuine output) — the failure clusters on this conversation's failure-laden history.

## Suspected Code Paths

- `dify/AGIAssistant/AGI_Assistant.yml` — the `honesty_check` code node: currently passes these drafts through (no completion claims match, correctly), which means the user receives the dangling text **plus the leaked XML**. It is the natural place to detect leaked invocation syntax: the literal `<invoke name="hermes_…">` (and close variants) in the visible answer is proof of an undispatched call.
- The `hermes_agent` node's model configuration (`moonshotai/kimi-k3` via OpenRouter): the model's native XML tool-call syntax escaping the structured channel — the provider-side parser either doesn't convert the leaked tags or the model emitted them malformed. Upstream of our code.
- `src/agentic_rag_mcp/hermes_run_gate.py` — not implicated: the gate never saw these turns (no audit rows — nothing reached the sidecar).

## Root Cause Hypothesis

**High confidence (leak shape).** kimi-k3 occasionally falls out of the structured function-calling channel when emitting a tool call: the invocation appears as literal text in the assistant message instead of a parsed tool-call block, so Dify's agent loop treats the turn as text-only and ends it. The model built the correct call — the leaked block contains the right tool name and both arguments — it simply went down the wrong channel. The silent no-emit shape (09:26) is the same failure without the visible tag (either the tags were consumed/unparseable or the generation simply ended), which stays indistinguishable from ordinary text at the answer layer. The trigger correlates with long failure-laden conversation history; fresh contexts emit reliably (three successes today).

## Proposed Remediation

**Preferred**: extend the `honesty_check` code node with a second, precisely-scoped detector: if the visible answer contains a leaked invocation tag naming a hermes tool (`<invoke`, `<function_call`, or `<tool_call` followed by `hermes_` within the tag), the call provably failed to dispatch — replace the answer with an honest dispatch-failure notice: the call did not reach the local agent, nothing was done, the raw command text was a model formatting glitch; re-send the request (and fresh conversations are reliable). This is zero-false-positive detection (no legitimate answer contains that literal), the existing completion-claims logic is untouched, and the notice converts a confusing leak into an honest, actionable message. Harness cases: the two recorded drafts from this incident — the leak shape must be replaced; all seven prior cases unchanged (fabrications block, honest drafts pass, real turns pass).

**Alternatives**:
- Structurally re-dispatching the leaked call (parse the XML in a code node and invoke the MCP tool) — Dify code nodes cannot invoke MCP tools; rejected.
- Provider/model-side fix (OpenRouter/Dify kimi tool-call parser) — upstream, outside our control, same posture as the kimi-k3 pin.

**Files likely to change**:
- `dify/AGIAssistant/AGI_Assistant.yml` (`honesty_check` code node — second detector + notice text)
- `/tmp`-style node harness case files (the two new recorded drafts join the seven existing)

**Tests to add or update**:
- Harness: leak-shape draft (`<invoke name="hermes_run_command">…` visible) → **replaced** with the dispatch-failure notice; silent no-emit draft ("I'll check that for you." alone) → still passes through (indistinguishable from ordinary text; documented residual); all seven prior recorded cases unchanged.

## Risks & Considerations

- The detector must key on the tag + `hermes_` name together (a user legitimately *asking about* `<invoke>` syntax is conceivable but would not carry a hermes tool name inside the tag).
- The silent no-emit shape remains undetectable at the answer layer — it degrades to the honest-but-empty "I'll check…" turn (documented residual from the previous lifecycle); only the model/provider layer can fix the root.
- The notice's advice should stay honest: re-sending in the same failure-laden conversation may repeat the flake — mention that a fresh conversation is the reliable path.
- YAML publish cycle + harness re-validation per the established method.

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the detector's scope (leaked hermes_* invocation tags only, not generic XML) is the conservative default.]
