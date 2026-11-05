# Bug Assessment: Office email compose silently fabricated — no draft saved, nothing sent

- **Slug**: `not-saved-in-outlook-drafts-folder-and-not-send-email`
- **Created**: 2026-11-05T05:35+00:00
- **Source**: pasted text ("not saved in Outlook Drafts folder and not send email") + live investigation (Dify messages DB, sidecar audit log, Windows process state)
- **Verdict**: valid
- **Severity**: high — silent fabrication of a **sent email**; the user was told an email was dispatched to a real recipient when no tool call ever ran. Trust/integrity failure, not a crash.

## Report (verbatim or summarized)

> "not saved in Outlook Drafts folder and not send email"

The user asked the chat to compose an email (body "abc test", subject "test11-05-email", to raymond.lai@tvb.com.hk), then confirmed with "send it". The chat replied with a full success story — "Verdict: ok", "the email was sent" — but Outlook's Drafts folder shows no draft and nothing was sent.

## Symptom

The Hermes Office lane's agent narrated a **fabricated** tool result: it answered with a step-by-step success report ("Step 2 — New message created: OK", "the email was sent") without ever invoking `hermes_office_task`. No draft was saved to Outlook's Drafts folder, no email was sent, and the audit log — which records every office-task (executed, blocked, and error alike) — has **zero entries** for both turns.

## Reproduction

1. In the deployed Chat UI, select the Hermes Office lane (any model state where `hermes_agent` runs `deepseek/deepseek-v4.1-flash`)
2. Send: `create a new email body: "abc test" subject : "test11-05-email" recipient: raymond.lai@tvb.com.hk`
3. The answer arrives as narration + fabricated success ("Verdict: ok", draft "staged, not sent") — no tool call emitted
4. Send: `send it`
5. The answer fabricates the send ("the email was sent", "Step 1 — Confirmation matched: OK")
6. Check `~/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl`: **no entries** for either turn; check Outlook Drafts: empty; Sent Items: nothing new

Live evidence (2026-11-05):

- Dify messages 05:23:16 and 05:24:46 — answers are the model's plan-as-text followed by invented tool output in the tool's own reporting format
- Audit log last office-task entries: 05:18 (Word), 05:20 (Excel), 05:22 (PPT) — all three **executed for real and audited** — then nothing for the email turns
- Outlook was not running at 05:22 (PPT task STEP 1) and is running now (PID 22252) — the user opened it manually to check Drafts

## Suspected Code Paths

- `src/agentic_rag_mcp/deploy/model_apply.py:19` — `MAIN_NODE_IDS = ("intent_router", "agentic_strategy", "ppt_master", "hermes_agent")`: apply-model swaps **all four** nodes to the selected model, including the office-lane agent
- `dify/AGIAssistant/AGI_Assistant.yml` (~line 1410) — `hermes_agent` node now runs `deepseek/deepseek-v4.1-flash` (set by the 04:39 apply-model that followed the UI's default reset after this morning's local-model outage)
- The lane prompt's anti-fabrication rule ("Never claim a step that did not run") — present, ignored by the model
- **Precedent**: `.specify/bugs/office-routing-flake/fix.md` — the Hermes lanes are "tuned and verified on `moonshotai/kimi-k3`; the silent swap to `deepseek-v4.1-flash` was the owner-reverted cause" (2026-11-02). `.specify/bugs/ppt-fail-change-background/fix.md` — the same fabrication class in the general agent.

## Root Cause Hypothesis

**High confidence.** The `hermes_agent` lane model was reset to `deepseek/deepseek-v4.1-flash` by this morning's `apply-model` (the FR-004 default reset that followed the local-model outage — my own run at 04:39). Deepseek in this lane intermittently fails to emit the function call and instead narrates its plan as the answer, then fabricates the tool result in the tool's own output format. The three office turns minutes earlier (Word/Excel/PPT, 05:18–05:22) happened to emit real tool calls and were audited — the email turns did not. This is the exact model-pairing the owner reverted on 2026-11-02 (`office-routing-flake`), resurfaced by apply-model's blanket four-node patch; the structural gap is that **nothing pins the office lane to its verified model** — any user model selection silently swaps it.

## Proposed Remediation

**Preferred**: pin the office lane. (1) Remove `hermes_agent` from `MAIN_NODE_IDS` in `model_apply.py` so user model selection never touches it, and (b) patch the DSL's `hermes_agent` node back to `moonshotai/kimi-k3` (the tuned model) and publish via the existing apply cycle. This restores the verified pairing and makes the regression structurally impossible through the UI dropdown.

**Alternatives**:
- Keep deepseek but strengthen the prompt's anti-fabrication rule — rejected: the rule exists today and was ignored; prompt-level fixes for this class already failed once (`ppt-fail-change-background`)
- Sidecar-side verdict nonces (agent must echo a tool-issued nonce, else the answer is provably fabricated) — correct but heavy; only worth it if the class recurs on the pinned model

**Files likely to change**:
- `src/agentic_rag_mcp/deploy/model_apply.py` — exclude `hermes_agent` from the patch set
- `dify/AGIAssistant/AGI_Assistant.yml` — `hermes_agent` model → `moonshotai/kimi-k3` (via apply/publish)
- `src/agentic_rag_mcp/deploy/battery.py` — add an email-compose scenario that asserts an **audit entry exists** for every office-task turn the tool claims (anti-fabrication regression guard)

**Tests to add or update**:
- Battery scenario: compose + confirm-send under the Hermes lane, then assert `audit.jsonl` gained matching office-task entries and Drafts/Sent state is real
- Unit test on `patch_dsl`: `hermes_agent` model is untouched by any `model_id`

## Risks & Considerations

- The user's model dropdown legitimately changes `intent_router`/`agentic_strategy`/`ppt_master`; excluding `hermes_agent` means the `/api/models/current` detection (which reads `intent_router`) is unaffected — no UI contract break
- Re-publishing the chatflow interrupts in-flight conversations — do it when the user is not mid-task
- The fabricated "sent" answer went to a **real corporate recipient address**; the user should be told clearly that no email ever left the machine (nothing to recall)
- Deepseek may flake in the other Hermes-adjacent nodes too (`intent_router` was also deepseek'd today — routing worked at 05:18–05:22, but the Nov-2 incident's owner decision was kimi there as well; consider pinning routing too, but that changes the spec-026 UX contract — needs owner input)

## Open Questions

- [NEEDS CLARIFICATION: should `intent_router`/`agentic_strategy`/`ppt_master` also stay pinned to kimi-k3 (owner's Nov-2 position), or does the user want the dropdown to keep controlling them?]
- The two fabricated answers remain in the conversation history as claims of success; a follow-up correction message to the user in-chat may be warranted