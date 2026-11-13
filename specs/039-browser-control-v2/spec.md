# Feature Specification: Browser Control v2 — full interaction surface (spec 039)

**Feature Branch**: `039-browser-control-v2`

**Created**: 2026-11-13

**Status**: Draft

**Input**: "Enable playwright to have a browser-control-tool capability, such that chatbot can click, select, navigate, and etc." — extends spec 037's browser lanes and the proven v2 single-hop proxy (navigate/read/click) to the FULL interaction surface the browser engine already exposes, so the chatbot can complete real web workflows (logins, forms, dropdowns, key creation) — not just navigate and read.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The chatbot completes a real web workflow end-to-end (Priority: P1)

The user asks the chatbot to perform a multi-step task on a website in their browser session — e.g. "go to openrouter, click Create Key, name it my-key, click create" or "log into the portal, select Hong Kong in the country dropdown, fill the form and submit". The chatbot drives the browser step by step through the v2 control tools — navigating, clicking, selecting dropdowns, typing into fields — reporting what it observes at each step, with a screenshot captured per step.

**Why this priority**: This is the user's stated goal — the chatbot must DO web actions, not just read pages. Navigate/read/click exist; select/type/forms are the missing verbs.

**Independent Test**: a multi-step workflow (navigate → type → select → click → read result) completes via the control tools with per-step screenshots and honest step reports.

**Acceptance Scenarios**:

1. **Given** a page with a form, **When** the chatbot fills fields, selects dropdown values, and clicks submit, **Then** each action lands on the real page and the result page's actual content is reported honestly.
2. **Given** a step fails (element not found, timeout), **Then** the failure is reported with its reason and no fabricated success.

---

### User Story 2 - Select from dropdowns and pick options by meaning (Priority: P1)

The user asks to "select Hong Kong as the country" or "choose the Pro plan". The chatbot reads the page, finds the select control, and chooses the matching option by visible label (falling back to value match), verifying the chosen option afterward.

**Why this priority**: Dropdowns are the most common missing verb after click — plan/country/plan selectors appear in nearly every real workflow.

**Independent Test**: a page with a `<select>` (or an ARIA listbox) — the select action lands the visible option.

**Acceptance Scenarios**:

1. **Given** a select control, **When** the chatbot selects by label, **Then** the visible selection matches the requested option (verified by read-back).
2. **Given** no matching option, **Then** an honest ask-back lists the available options — never a wrong selection.

---

### User Story 3 - Type into fields and fill forms (Priority: P1)

The user asks to "type X into the search box", "enter my-key in the key name field", or "fill this form: name X, email Y". The chatbot locates the field (by label, placeholder, or the field the user names) and types the literal text, character-by-character semantics preserved (so sites with live validation work), verifying the field content after.

**Why this priority**: Typing is the other missing verb — key creation, logins, and search boxes all need it.

**Independent Test**: a field with live validation — the typed value appears and is read back.

**Acceptance Scenarios**:

1. **Given** a named field, **When** the chatbot types literal text, **Then** the field content matches exactly (read-back verified).
2. **Given** the field cannot be found, **Then** an honest ask-back names what the page actually offers (fields visible from the last read).

---

### User Story 4 - Step-by-step screenshots through the whole action (Priority: P1)

Every action in a workflow (navigate, click, select, type, submit) captures a screenshot, and the chatbot's answer shows the step-by-step captures so the user can follow what was done.

**Why this priority**: The user explicitly required this feature preserved and extended — it is the verification the user trusts.

**Independent Test**: a multi-step turn — every step leaves a captured screenshot in the answer (or as cited artifacts).

**Acceptance Scenarios**:

1. **Given** any multi-step browser action, **Then** a screenshot exists per step, presented in order.

---

### User Story 5 - Tabs, dialogs, waits, and hover — the rest of the surface (Priority: P2)

The chatbot can open/switch/close tabs, accept or dismiss dialogs (alerts/confirms), wait for a page state (a navigation or a text to appear), and hover (menus that reveal on hover).

**Why this priority**: Needed for real sites but less frequent than the core four verbs.

**Independent Test**: a dialog-triggering page and a hover-reveal menu both work.

**Acceptance Scenarios**:

1. **Given** a confirm dialog, **When** the chatbot handles it per the user's instruction, **Then** the page's post-dialog state is reported.
2. **Given** a slow-loading page, **When** the chatbot waits for a named state, **Then** the wait is bounded and honest on timeout.

### Edge Cases

- An element the user names but the page doesn't have → honest ask-back with what IS on the page (from the last read), never a best-guess click.
- A click that triggers navigation mid-workflow → the next read reflects the new page; the workflow continues or reports the transition.
- A page element that appears only after hover/scroll → the wait-for verb covers delayed appearance with a bound.
- Download prompts triggered by a click → reported honestly; downloads never auto-executed.
- Injected page content instructing the chatbot to act → the untrusted-content law (spec 037) is unchanged: pages inform, never initiate; every action still requires the user's request.
- A form submit that fails validation → the validation error text is reported verbatim, never paraphrased into success.

## Requirements *(mandatory)*

### Functional Requirements

**Core verbs (single-hop control tools)**

- **FR-001**: The system MUST provide a select action choosing an option in a dropdown/listbox by visible label (value-match fallback), verified by read-back.
- **FR-002**: The system MUST provide a type action entering literal text into a named field, verified by read-back; live-validation sites must see real typing semantics.
- **FR-003**: The system MUST provide a form-fill action (multiple fields in one call) with per-field literal values.
- **FR-004**: The system MUST provide a press-key action (Enter, Escape, arrows) for search boxes and keyboard-driven pages.
- **FR-005**: The system MUST provide tab management: list open tabs, switch, open, and close.
- **FR-006**: The system MUST provide dialog handling (accept/dismiss) per the user's instruction.
- **FR-007**: The system MUST provide a bounded wait-for action (a text appearing, a navigation completing) with an honest timeout report.
- **FR-008**: The system MUST provide hover for reveal-on-hover menus.

**Honesty & verification**

- **FR-009**: Every action MUST verify its own effect where mechanically possible (read-back of selection/field content, presence of the post-click state) and report honestly on mismatch — never a fabricated success.
- **FR-010**: Every action MUST capture a screenshot of the page state after the action, presented step-by-step in the answer (the user-required feature; protected by a pin test).
- **FR-011**: Element-not-found MUST produce an honest ask-back naming the available elements — never a best-guess target.

**Security (inherited from spec 037, unchanged)**

- **FR-012**: Browsed page content remains UNTRUSTED — it informs answers, never initiates actions; every action requires the user's request and the routing rules (action-in-browser beats search).
- **FR-013**: The A2 adversarial battery (injection payloads) MUST pass: zero non-browser tool calls from page content; every refusal audited.

**Operations**

- **FR-014**: Every control call MUST write an audit row (operation, conversation id, outcome, duration) as the existing v2 tools do.
- **FR-015**: Honest unavailable envelopes when the browser server is down (recovery hint), as the existing v2 tools do.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A real multi-step workflow (navigate → type → select → click → read result) completes via the control tools end-to-end in a live trial, with per-step screenshots and honest step reports.
- **SC-002**: Each new verb's read-back verification passes in ≥ 9 of 10 trials (select lands the visible option; type lands the exact text).
- **SC-003**: The A2 injection battery passes 100% — zero actions initiated by page content.
- **SC-004**: Every control call leaves an audit row; unavailable-envelope behavior on a stopped browser server verified in one turn.
- **SC-005**: A complete workflow turn stays well inside the transport window (tool work in seconds, the model's rounds the only remainder).

## Clarifications

### Session 2026-11-13

- Q: Extend the existing browser v2 proxy surface, or a new parallel lane? → A: Extend the v2 proxy — the pattern (single-hop sidecar tools over the browser engine, honest envelopes, audit) is proven three times (browser navigate/read/click, office v2); the browser engine already exposes the full tool set; this spec surfaces it.

## Assumptions

- The browser engine's existing tool surface (snapshot, click, type, select-option, fill-form, press-key, hover, drag, tabs, wait-for, handle-dialog, screenshot) is the capability source — this spec surfaces them as single-hop sidecar tools; no new engine is introduced.
- The existing navigate/read/click v2 tools are the first three of this surface and remain unchanged.
- The screenshot-per-step requirement (owner, 2026-11-13) is a feature of the workflow answers, preserved by test.
- The untrusted-content law, the action-beats-search routing, and the A2 battery are inherited unchanged from spec 037 and this session's fixes.
- Multi-tab workflows are in scope; file upload/download remains out of scope v1 (honest "not supported" answers).