# Bug Assessment: Chrome weather query — no response (browser test)

- **Slug**: no-response-test-playwright
- **Created**: 2026-11-11T08:12:12Z
- **Source**: pasted text (owner's live test prompt, run ~08:08 UTC today)
- **Verdict**: valid (needs reproduction, but the failure signature is clear)
- **Severity**: high

## Report (verbatim)

> "open chrome browser , type what is hong kong weather today at search bar, display hong kong weather"

## Symptom

A chat request to open Chrome, type a weather search, and display the result produced **no usable response** in the Chat UI. Expected: the dynamic browser lane (spec 037) drives the Playwright MCP / agent and reports the observed weather content.

## Reproduction

1. In the Chat UI, send: *"open chrome browser, type what is hong kong weather today at search bar, display hong kong weather"* (~08:08 UTC, conversation `ef979b00`).
2. Observed: the turn ends without the weather displayed. The audit log shows exactly ONE operation — `skill-search` (executed, 08:08:24) with the full prompt as intent — and **no browser-lane activity of any kind afterward** (`browser-scripted-run`, `browser-status`, `office-task`, launch rows: all absent).
3. [NEEDS CLARIFICATION: what did the Chat UI actually display — a stream error, a silent empty answer, or an answer claiming actions that never ran? The audit+gateway evidence shows the skill search ran and the launch directive reached the Hermes agent (gateway 16:08:27 local), but no downstream tool rows followed in the window.]

## Suspected Code Paths

- `dify/AGIAssistant/AGI_Assistant.yml` — the Hermes-lane routing rules (spec 037's BROWSER LANES block): a mixed prompt ("open chrome browser" + "type … at search bar" + "display") may match the **launch** phrasing (`open chrome`) rather than the browser-lane rules, sending the agent down the desktop-automation path with no followup tools — or the classifier may have dropped the turn after the skill search.
- `src/agentic_rag_mcp/browser_lanes/routing_gate.py` — `gate_browser_intent("open the browser window and click around a bit")` classifies as dynamic, but the **Dify-side classifier** (not this module) makes the real routing decision; the DSL's routing prompt has not been validated against mixed browser+typing prompts.
- `~/.hermes/logs/gateway.log` 16:08:27 — `Launch the program 'chrome' — no arguments — then, as a desktop followup: type w…` — the launch directive DID reach the agent; the silence after it is where the turn died (no followup, no error surfaced to the user).
- `src/agentic_rag_mcp/server.py` (`hermes_launch_app` / `hermes_office_task` handlers) — the mixed prompt likely landed on the launch lane; the "then, as a desktop followup" tail asks the agent for GUI typing, which is exactly the class the DSL routes to desktop automation that then stalls silently.

## Root Cause Hypothesis

The prompt is a **mixed browser+GUI-typing intent** that the Dify classifier routed to the Hermes launch lane (open chrome) with a "type at search bar" desktop followup — the desktop-automation path — instead of spec 037's dynamic browser lane (Playwright). The turn then stalled: Chrome launched (or the directive was sent), the agent had no viable path to "type at the search bar" via desktop automation within the budget, and the failure surfaced as silence rather than an honest error. This is a **routing + honest-failure gap for mixed browser prompts**, the exact class the 037 DSL rules were written for but were never live-tested against (the A2 harness tested injection, not mixed-intent routing). Confidence: **medium** — the audit/gateway evidence pins where the turn died, but the UI-side symptom (error vs silence) is unconfirmed.

## Proposed Remediation

**Preferred**: (1) Reproduce with the exact prompt and capture the full turn: UI answer text, Dify run trace, audit rows. (2) Extend the 037 DSL browser-lane routing rules so "open chrome/browser + type/search X" phrasing routes to the **dynamic browser lane** (the agent types into the page via Playwright), and the launch lane explicitly refuses browser-content followups ("typing at a search bar" is not a program launch). (3) Add the honest-failure guarantee: a turn that routes but produces no tool outcome must end with an explicit error/ask-back, never silence. (4) Pin the routing in the A2/integration harness with mixed-intent cases ("open chrome and type … in the search bar" → dynamic lane, never launch+GUI).

**Alternatives**:
- Keep launch routing but make the "desktop followup" typing flow real (WindowsMCP keyboard automation) — rejected: GUI typing is the anti-pattern 037 exists to replace.
- Treat as user error ("type what is hong kong weather" is ambiguous) — rejected: a helpdesk assistant must handle exactly this phrasing honestly.

**Files likely to change**:
- `dify/AGIAssistant/AGI_Assistant.yml` (routing rules + launch-lane refusal of browser-content followups)
- `tests/integration/test_browser_a2.py` (mixed-intent routing pins)
- possibly `src/agentic_rag_mcp/hermes_launch_gate.py` (browser-content followup refusal)

**Tests to add or update**:
- Mixed browser+typing prompt → dynamic lane (not launch), pinned in the routing harness
- A routed-but-stalled turn surfaces an honest error (no silent empty answer)

## Risks & Considerations

- DSL republish required (deploy window) — routing-rule changes are prompt-level and need a battery pass.
- The launch lane's followup mechanics are shared with non-browser launches; the refusal must be narrow (browser-content followups only) to avoid breaking the legitimate desktop-followup flows (spec 029).
- The 300 s ceiling may be implicated if the turn died mid-followup rather than routing wrong — the run trace (step 1) will decide between the two hypotheses.

## Open Questions

- [NEEDS CLARIFICATION: what did the Chat UI display for the turn — empty answer, error, or a claim without action?]
- [NEEDS CLARIFICATION: did Chrome visibly open on the desktop during the test?]