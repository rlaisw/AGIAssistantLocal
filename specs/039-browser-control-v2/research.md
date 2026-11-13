# Research: Browser Control v2 (spec 039)

**Spec**: 039 | **Date**: 2026-11-13 | **Status**: resolved (all decisions inherit the proven v2 pattern)

## R1: The engine inventory (live-verified)

- **Decision**: the six new verbs map 1:1 onto existing engine tools, verified against the live `/tools/list`: select → `browser_select_option`, type → `browser_type`, form → `browser_fill_form`, press-key → `browser_press_key`, tabs → `browser_tabs`, wait → `browser_wait_for`. Screenshot → `browser_take_screenshot`. Hover and dialog handling are available for the P2 surface (`browser_hover`, `browser_handle_dialog`) but are not in the six core tools (spec P2; ride the existing click + wait if needed v1).
- **Rationale**: zero new engine capability required — the spec surfaces what exists.
- **Alternatives**: none needed — the inventory was enumerated live.

## R2: Element naming — how a verb finds its target

- **Decision**: the verbs take a human target description (the field label, placeholder, or the name the user used, e.g. "the key name field") plus the last-read page context; the engine's own tools resolve text-matched elements. The proxy passes the user-visible name through; when resolution fails the tool returns the engine's error and the handler converts it to the FR-011 ask-back listing available elements (from the most recent read).
- **Rationale**: the engine's click already accepts element+ref semantics; inventing a selector mini-language in the proxy would duplicate the engine's job and drift.
- **Alternatives**: CSS/XPath selectors exposed to the model (rejected: selector-crafting is exactly the LLM-fragile work the v2 pattern removes).

## R3: Read-back verification per verb

- **Decision**: select verifies via the option's visible state (re-snapshot the control's chosen label); type/form verify field content via a bounded `browser_evaluate` read-back of the named field's value (the doc_write_v2 discipline); press-key and tabs verify by the engine's own result text.
- **Rationale**: FR-009; the same verify-in-code pattern proven in office v2 (including the numeric lesson: compare what the page DISPLAYS, not internal representation).
- **Alternatives**: trust the engine's success ack (rejected: the spec demands read-back).

## R4: The screenshot-per-step requirement

- **Decision**: a shared `_screenshot_after_action()` helper in the proxy fires `browser_take_screenshot` after every verb call (best-effort, never fails the action), and each tool's return carries the screenshot artifact reference so the answer presents the steps in order.
- **Rationale**: the owner-required feature (pinned by `test_intent_router_rules.py` + FR-010/SC-001 here); screenshots are transient artifacts the engine already produces.
- **Alternatives**: screenshot only in the workflow answer (rejected — the owner wants per-step capture during the action).

## R5: Sensitive fields

- **Decision**: type/form enter user-provided values into any field including passwords (clarified); password inputs display masked, so the screenshot artifact never shows the secret; no value is written to the audit log (the existing tools log outcomes/summaries — the values must be excluded from `outcome` text).
- **Rationale**: the user's request is the authority; the audit-log exclusion prevents the secret from landing in the JSONL.
- **Alternatives**: refuse sensitive fields (rejected by the clarify answer).

**All NEEDS CLARIFICATION resolved; none remain.**