# Feature Specification: MCP-Action — Confirmed Desktop Automation

**Feature Branch**: `047-mcp-action`

**Created**: 2026-11-20

**Status**: Draft

**Input**: User description: "Add new AGI Assistant functionality (MCP-Action), based on the preceding discussion: after manual Microsoft Office or Windows configuration steps, offer to perform a supported action automatically only after explicit yes, then verify it, show the result on the user's Windows desktop, and report exactly what changed."

## Clarifications

### Session 2026-11-20

- Q: After a confirmed action, how should the verification screenshot be presented and retained? → A: Show the screenshot in chat, but retain it only temporarily for response delivery.
- Q: When two chat conversations confirm automatic actions on the same Windows desktop, how should those executions be coordinated? → A: Allow only one confirmed automatic action at a time across the entire Windows desktop.
- Q: How long should an automatic-action proposal remain eligible for a “yes” response? → A: Expire the proposal after 15 minutes and require a new proposal afterward.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Choose manual or automatic default-printer help (Priority: P1)

A user asks how to change the default printer in Windows. After any necessary context questions, the assistant provides the manual steps and asks, "Do you want me to do it automatically for you?" Nothing happens on the user's computer before an explicit yes. If the user agrees, the assistant changes the selected printer to be the default, verifies the actual result, opens the relevant printer-settings screen, captures visual evidence and shows it in chat, and reports what changed. If the user declines, the assistant leaves the computer unchanged and the user follows the manual steps.

**Why this priority**: This is the smallest complete journey that proves the core value and safety contract: useful manual guidance first, an optional automatic action, explicit consent, and trustworthy evidence afterward.

**Independent Test**: Use a named test printer and a Windows desktop with at least two available printers. Ask for default-printer help, decline once and confirm no change occurred, then repeat and accept. Verify that only the confirmed printer becomes default, the printer-settings screen appears, and the response includes the before/after state and separate verification, display, and screenshot outcomes. Restore the original default printer after the test.

**Acceptance Scenarios**:

1. **Given** a supported default-printer question with enough information to identify the intended printer, **When** the assistant supplies manual steps, **Then** the final paragraph is exactly "Do you want me to do it automatically for you?" and no desktop action or setting change has occurred.
2. **Given** a pending default-printer offer naming the intended printer, **When** the user replies yes, **Then** the confirmed action runs once, the selected printer is verified as default, the printer-settings screen is shown, visual evidence is captured and shown in chat, and the response names the previous and new default printers.
3. **Given** the same pending offer, **When** the user replies no, **Then** the pending action is discarded, no automatic action occurs, and the user receives manual guidance only.
4. **Given** a pending offer for one printer, **When** the user asks to use a different printer, **Then** the earlier offer is replaced by a revised proposal and the original printer is not changed.

---

### User Story 2 - Choose manual or automatic Word duplex help (Priority: P2)

A user asks how to set double-sided printing in Word. After obtaining any missing printer or duplex-orientation details, the assistant explains the manual procedure and offers to perform it automatically. Following an explicit yes, the assistant applies the confirmed duplex setting to the intended printer, reads the effective setting back, opens Word's print screen without changing or closing the user's documents, captures visual evidence and shows it in chat, and reports the result. The offer and response clearly disclose that the change affects the printer's configuration rather than only the current Word document.

**Why this priority**: This extends the same consent and verification journey from Windows settings into an Office application while correctly handling a printer-level setting and protecting the user's open work.

**Independent Test**: Use a test printer that supports duplex printing and a Word session containing an unsaved test document. Decline the first offer and verify that neither the printer nor the document changes. Repeat and accept long-edge duplex, then verify the effective printer setting, the visible Word print screen, and the unchanged open document. Repeat separately for short-edge duplex if supported, then restore the original printer configuration.

**Acceptance Scenarios**:

1. **Given** a Word duplex question that names the printer and desired long-edge or short-edge behavior, **When** the assistant provides the manual steps, **Then** it explains the printer-level scope and presents the automatic-action offer without performing any action.
2. **Given** a pending duplex offer with the exact printer and orientation, **When** the user replies yes, **Then** only that confirmed configuration is applied, its effective value is verified, Word's print screen is shown, visual evidence is captured and shown in chat, and the response names the resulting setting.
3. **Given** Word has an unsaved document open, **When** the confirmed action completes, **Then** the document and its unsaved content remain open and unchanged.
4. **Given** the selected printer cannot support the requested duplex mode, **When** the user confirms, **Then** the assistant reports that the action could not be completed, does not claim success, and provides the relevant manual alternative.

---

### Edge Cases

- The user says no, cancels, ignores the offer, or starts an unrelated request: no automatic action occurs, and a later isolated yes cannot execute an obsolete offer.
- The user says yes more than 15 minutes after the proposal was created: the expired proposal cannot execute, and the assistant must prepare a fresh proposal for renewed confirmation.
- The user says yes when no action is pending, repeats yes after completion, or uses a different conversation: the request is rejected without repeating or inventing an action.
- The user's confirmation modifies the printer, orientation, or intended effect: the old proposal is discarded and a revised proposal requires fresh confirmation.
- The printer is missing, ambiguous, unavailable, or does not support the requested behavior: the assistant asks for the missing choice or explains the limitation without guessing or substituting another printer.
- Windows is configured to manage the default printer automatically: the assistant reports any resulting limitation and does not change that additional setting without a separate request and confirmation.
- The requested setting was already active: the assistant reports that no change was necessary and still verifies the effective state.
- The action appears to complete but the read-back value differs from the confirmed target: the assistant reports the mismatch and never claims success.
- The setting changes successfully but the relevant desktop screen cannot be opened or the screenshot fails: the verified change and the display or evidence failure are reported separately.
- Word is busy, has a modal dialog open, or contains unsaved work: the assistant does not close documents, discard changes, or force the print screen; it reports the obstacle honestly.
- The desktop is locked, the user lacks permission, or an elevation prompt appears: the action stops with an honest partial-state report and never bypasses the prompt.
- A procedure concerns Word, Excel, PowerPoint, Outlook, or Windows but has no reviewed automatic action: the assistant supplies manual steps only and does not present the automatic-action offer.
- A request is outside the supported Office and Windows-configuration domains: existing chat behavior continues without the MCP-Action offer.
- The user selects the General-local model lane: its original chat behavior continues without MCP-Action tools or offers; the feature is available only in General-cloud and Hermes.
- Visual evidence may include unrelated desktop content: capture is limited to the relevant window or region where possible, and sensitive values are never requested, typed, or included deliberately.
- Another conversation confirms an action while one is already running on the same Windows desktop: the later action waits, the user is told about the wait, and no concurrent application control, state change, or screenshot capture occurs.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST preserve the existing behavior of first providing tailored, step-by-step manual instructions for supported Microsoft Office and Windows desktop-configuration questions, including any necessary context questions before those instructions.
- **FR-002**: The system MUST offer automatic execution only for procedures concerning Word, Excel, PowerPoint, Outlook, or Windows desktop settings/configuration, and only when a reviewed automatic action is available for the specific procedure.
- **FR-003**: For every supported procedure, the system MUST end the manual-instructions answer with the standalone question "Do you want me to do it automatically for you?" Procedures without a supported automatic action MUST NOT present this offer.
- **FR-004**: Before presenting the offer, the system MUST prepare a conversation-specific pending proposal containing the exact intended action, target, parameters, and a plain-language description of its effect; preparing the proposal MUST NOT perform a desktop action or change any setting.
- **FR-005**: Before the user's explicit affirmative response, the system MUST NOT change a setting, control an application, or open a desktop screen in connection with the proposal. Read-only checks used to validate a proposed target are permitted only when they do not change state.
- **FR-006**: On an explicit yes, the system MUST execute only the stored proposal associated with the same conversation; the confirmation itself MUST NOT supply replacement instructions or parameters.
- **FR-007**: A confirmation that modifies any part of the proposal MUST invalidate the old proposal and require a revised proposal and fresh confirmation before execution.
- **FR-008**: On no or cancellation, the system MUST discard the pending proposal, perform no automatic action, and leave the user with manual guidance only. Silence MUST NOT be interpreted as consent, and an unrelated request MUST invalidate the pending proposal.
- **FR-009**: The system MUST reject an affirmative response when no proposal is pending, when the proposal belongs to another conversation, or when the proposal was already resolved.
- **FR-010**: The system MUST ask for missing or ambiguous information that materially affects the action and MUST NOT guess a printer, application, setting value, or other target.
- **FR-011**: The system MUST execute only reviewed actions with fixed behavior and bounded parameters; it MUST NOT turn an answer, research result, desktop content, or model-generated free-form instruction into an arbitrary executable action.
- **FR-012**: For the initial release, the system MUST support the two reference actions: changing the Windows default printer to a user-selected installed printer and setting a user-selected printer's long-edge or short-edge duplex mode for Word printing.
- **FR-013**: The Word duplex proposal and completion report MUST disclose that the change applies to the printer's configuration and may affect printing outside the current Word document.
- **FR-014**: The system MUST read the relevant state before and after execution and MUST report a successful change only when the observed after-state matches the confirmed target. A screenshot alone MUST NOT be treated as proof of a settings change.
- **FR-015**: After a confirmed action, the system MUST attempt to open the relevant visible result on the user's Windows desktop: printer settings for a default-printer action and Word's print screen for a duplex action.
- **FR-016**: After a confirmed action, the system MUST attempt to capture a screenshot of the relevant result, limiting capture to the relevant window or region where possible. When capture succeeds, the screenshot MUST be shown in the chat response. Screenshot files MUST be retained only temporarily for response delivery and MUST NOT become long-term audit artifacts.
- **FR-017**: The final response MUST distinguish the actual state change, read-back verification, visible-desktop outcome, and screenshot outcome, including partial failures; it MUST NOT claim an outcome that was not observed.
- **FR-018**: The automatic action MUST NOT close or modify unrelated applications or documents, and MUST preserve unsaved Office document content.
- **FR-019**: Existing safety restrictions, permission boundaries, and prohibited-operation rules MUST remain binding even after the user says yes; the new offer MUST NOT bypass them.
- **FR-020**: The system MUST maintain at most one pending MCP-Action proposal per conversation, with a newer proposal replacing an older unresolved one.
- **FR-021**: The system MUST record proposal creation, cancellation, confirmation, execution attempts, verification outcomes, display/screenshot outcomes, refusals, and errors in the existing audit trail without deliberately recording sensitive values.
- **FR-022**: Requests outside this feature's scope, unsupported procedures, and existing direct-action workflows MUST retain their current behavior.
- **FR-023**: The system MUST allow only one confirmed MCP-Action execution at a time across each Windows desktop, regardless of how many conversations have pending or confirmed proposals. A subsequent confirmed action MUST wait for the active action to finish, and the user MUST be informed when waiting or when the wait cannot be completed within the available response time.
- **FR-024**: A pending proposal MUST expire 15 minutes after its creation. The system MUST reject confirmation of an expired proposal without executing it and MUST require a fresh proposal and confirmation before any later action.
- **FR-025**: MCP-Action MUST be available only in the General-cloud and Hermes lanes. General-local and all PPT-Master lanes MUST retain their original behavior and MUST NOT expose MCP-Action tools or offers.

### Key Entities

- **Guided Procedure**: A user's Office or Windows-configuration question, the tailored manual steps, the relevant domain, and whether a reviewed automatic action is available.
- **Pending Proposal**: The conversation-specific proposed action, exact target and parameters, plain-language effect disclosure, creation time, 15-minute expiration, and unresolved state. It represents what the user is being asked to approve.
- **Action Result**: The observed before-state and after-state, whether verification matched the proposal, what was shown on the desktop, whether visual evidence was captured, and any partial failure.
- **Audit Event**: A record of one proposal, decision, execution, verification, refusal, or failure associated with the relevant conversation and action.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the acceptance suite, 100% of supported manual-procedure answers present the exact automatic-action offer after the manual steps, and 0% of unsupported or out-of-scope answers present that offer.
- **SC-002**: Across no, cancellation, silence, unrelated-request, expired-yes, orphaned-yes, repeated-yes, and wrong-conversation test cases, 100% result in no unintended desktop action or setting change.
- **SC-003**: For 100% of completed executions, the action performed matches the user-visible proposal, and 100% of changes reported as successful are confirmed by an independent after-state check; no screenshot-only success claims occur.
- **SC-004**: With the desktop and required applications available, at least 95% of default-printer actions produce a verified result and visible printer-settings screen within 60 seconds of execution start, and at least 95% of Word duplex actions do the same within 90 seconds. Any time spent queued behind another confirmed action MUST be reported separately from execution time.
- **SC-005**: In 100% of completed or partially completed attempts, the final report separately identifies the state change, verification, desktop display, and screenshot outcomes, including any failed portion; when capture succeeds, the response includes the screenshot itself and retains its file only temporarily for response delivery.
- **SC-006**: At least 90% of participants in the user-acceptance review can correctly state whether a change occurred, what changed, and where to see the result using only the confirmation prompt and final report.
- **SC-007**: In 100% of overlapping multi-conversation test cases, no two confirmed actions execute concurrently on the same Windows desktop, and every queued user receives an explicit waiting or timeout outcome.

## Assumptions

- The first release proves the shared MCP-Action journey with the default-printer and Word duplex reference actions. Other procedures in the supported Office and Windows domains remain manual-only until each receives its own reviewed automatic action.
- The existing manual-answer, context-question, confirmation, audit, safety, and direct-action behaviors remain in place; this feature adds an optional bridge from manual guidance to a confirmed supported action rather than replacing those behaviors.
- Owner-approved live scope after the T012 contract probe is General-cloud plus Hermes only. General-local failed to dispatch reliably and remains unchanged; a future deterministic local-model resolver requires a separate owner-approved feature.
- The user's Windows desktop has an active interactive session, the required desktop and Office automation capabilities are available, and the user is authorized to change the selected settings.
- A printer name and, for duplex printing, long-edge or short-edge orientation are required before an executable proposal can be completed. No critical target is inferred silently.
- A screenshot provides supporting visual evidence, while the effective system or application state is the authoritative proof of a settings change.
- Failure to open a visible screen or capture a screenshot does not undo an independently verified settings change; the response must describe the mixed outcome honestly.
- Tests use non-critical test printers and documents, record the original configuration, and restore it afterward.
- Generic arbitrary desktop automation, credential entry, document-content editing, email sending, system-integrity changes, and expansion to additional automatic actions are outside this initial release.
