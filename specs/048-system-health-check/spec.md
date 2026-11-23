# Feature Specification: System Health Check — Read-Only Desktop Diagnosis

**Feature Branch**: `048-system-health-check`

**Created**: 2026-11-22

**Status**: Draft

**Input**: User description: "Add a system health check feature based on the preceding discussion. When the user reports that their Windows 11 desktop is unstable—freezing, hanging, applications crashing, or showing BSODs—the assistant should provide diagnostic guidance, offer to run a read-only health check automatically, return the complete HTML report in the chat answer (and write it to %LOCALAPPDATA%\Temp\selfcheck.html), serve a temporary report URL, and open Reliability Monitor. It must not repair the system; repairs require HelpDesk. The report may display login, email, IP address, hardware, password-expiry, event-log, and crash data; the owner explicitly approved showing those fields."

## Clarifications

### Session 2026-11-22

- Q: When the health check finds problems that need repair, should the assistant only refer the user to HelpDesk, or also offer an automatic HelpDesk handoff? → A: Refer the user to HelpDesk with guidance; no automatic HelpDesk request or repair.
- Q: How long should the health-check report URL remain accessible after it is generated? → A: Expire after 15 minutes.
- Q: Should a direct request such as “run a system health check” be eligible for the automatic action even when the user has not described desktop instability? → A: Direct requests are eligible; give concise guidance, then the exact offer.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run an approved read-only health check (Priority: P1)

A user reports that their Windows 11 desktop is unstable, for example with freezes, hangs, application crashes, or BSODs, and asks for help identifying the cause, or explicitly asks to run a system health check. After any necessary context questions, the assistant gives practical manual diagnostic guidance, or a concise explanation for an explicit check request, including opening Reliability Monitor where relevant. It then asks whether the user wants the health check run automatically. Only after an explicit yes does it run the read-only diagnostic, provide a temporary report URL in chat, open Reliability Monitor on the desktop, and summarize the overall result.

**Why this priority**: This is the core diagnostic journey. It provides immediate value for an unstable desktop while keeping the system unchanged and leaving the existing consent and evidence rules intact.

**Independent Test**: On a Windows 11 test machine, describe a reproducible instability symptom. Decline once and verify no report or desktop action occurs. Repeat, accept, and verify the report link opens, Reliability Monitor becomes visible, the summary matches the report, and no system setting, application, or repair is changed.

**Acceptance Scenarios**:

1. **Given** a user reports desktop instability with missing critical context, **When** the assistant needs symptom timing, affected applications, or error details, **Then** it asks one or two targeted questions and ends that turn without running the health check or presenting generic steps.
2. **Given** enough diagnostic context, **When** the assistant provides manual guidance, **Then** the final paragraph is exactly "Do you want me to do it automatically for you?" and no diagnostic execution or desktop change has occurred.
3. **Given** a pending health-check offer, **When** the user replies plain yes, **Then** the read-only check runs once, a temporary report URL is displayed in chat, exactly one Reliability Monitor window is shown, and the response summarizes overall status, score, pass/warn/fail counts, and reliability findings.
4. **Given** the report contains warnings or failures, **When** the result is delivered, **Then** the assistant identifies the repair areas and directs the user to HelpDesk without attempting a repair.
5. **Given** an explicit request to run a system health check, **When** the assistant responds, **Then** it gives concise guidance about the read-only check, ends with the exact offer, and performs no diagnostic or desktop action before a confirmed yes.

---

### User Story 2 - Decline automation and use manual diagnosis (Priority: P2)

A user prefers to deal with the unstable desktop manually or does not want the assistant to run diagnostics. The assistant preserves the manual guidance, performs no automatic action, and makes clear that repairs are handled through HelpDesk rather than automatic changes.

**Why this priority**: The feature must remain optional and safe even when the user declines or when the requested follow-up is a repair rather than a diagnostic.

**Independent Test**: Decline the health-check offer and verify that no report URL, Reliability Monitor launch, screenshot, or system change occurs. Then ask for a repair and verify the assistant explains the diagnostic boundary and refers the repair to HelpDesk.

**Acceptance Scenarios**:

1. **Given** a pending health-check offer, **When** the user replies no, **Then** the pending action is discarded, no health check runs, and the user receives manual diagnostic guidance only.
2. **Given** the user asks the assistant to repair the instability, **When** the request is processed, **Then** the assistant explains that the feature only diagnoses and directs the repair request to HelpDesk without executing a repair.
3. **Given** an unsupported operating system or a request outside desktop-instability diagnosis or an explicit health-check request, **When** the user asks for help, **Then** no automatic health-check offer is presented.

### Edge Cases

- Some checks cannot run without elevation or supported hardware; the report must mark them as skipped and must not imply complete coverage.
- Report generation fails: no report URL or fabricated findings may be returned; any available result and the failure must be stated honestly.
- The health check succeeds but the report cannot be published or the temporary URL cannot be created: the summary and reliability findings remain available, and the report failure is reported separately.
- Reliability Monitor cannot be opened or verified: the report remains available, and the display failure is reported separately without claiming the screen was shown.
- The check exceeds its allowed time: it stops or reports a timeout honestly and must not continue indefinitely.
- Reliability Records are unavailable or empty: the report says so rather than inventing recent crashes.
- The temporary report link is accessed after expiry or with an invalid token: no report content is returned and no hidden metadata is exposed.
- The user says yes when no health-check proposal is pending, repeats yes, or modifies the request: the confirmation fails closed or requires a new proposal.
- The Windows desktop is active, locked, or otherwise unable to accept the Reliability Monitor display: the result is partial and identifies the display limitation.
- The account is non-domain, workgroup-joined, or lacks some permission: checks degrade to explicit skip/info results without fabricated pass findings.
- The user asks for a repair, not a diagnosis: no repair action is created or executed; HelpDesk guidance is provided.
- A second health check is requested while one is queued or running: the existing single-desktop execution rule applies, and duplicate execution is prevented.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST treat a request as eligible for automatic health-check support when the user reports Windows 11 desktop instability such as freezes, hangs, application crashes, or BSODs and asks for help diagnosing it, or explicitly requests a system health check.
- **FR-002**: The system MUST preserve the existing ask-first behavior by requesting one or two targeted context questions when critical symptom details are missing, and MUST NOT run the check in that ask-back turn.
- **FR-003**: Before offering the automatic check, the system MUST provide tailored manual diagnostic guidance for an instability report, including how the user can open and review Reliability Monitor, or concise guidance about the read-only check for an explicit health-check request.
- **FR-004**: For every eligible health-check procedure, the assistant MUST end its manual-guidance answer with the standalone exact question "Do you want me to do it automatically for you?"
- **FR-005**: Before presenting the offer, the system MUST store an exact read-only health-check proposal tied to that conversation; storing and presenting the proposal MUST NOT run the diagnostic, change a setting, control an application, or capture a screenshot.
- **FR-006**: The system MUST NOT run the health check before an explicit affirmative response to the pending proposal.
- **FR-007**: On an explicit yes on the immediately following dialogue turn, the system MUST execute only the stored health-check proposal and MUST NOT accept replacement commands, scripts, targets, or model-authored instructions in the confirmation.
- **FR-008**: The health check MUST be strictly read-only. It MUST NOT repair, reconfigure, restart, install, uninstall, delete, or otherwise modify the system.
- **FR-009**: The diagnostic MUST collect a health summary including an overall status, a score, pass/warn/fail/info/skip counts, computer/user/hardware inventory, individual checks, and recent reliability evidence.
- **FR-010**: The diagnostic MUST report recent application and Windows reliability records, including a recent-failure summary and a daily failure/informational timeline when that information is available.
- **FR-011**: On successful completion, the system MUST produce a human-readable HTML diagnostic report and make it available through a temporary report URL in the chat response.
- **FR-012**: The report URL MUST be temporary, unguessable, and non-cached; it MUST expire after 15 minutes without becoming a permanent report archive.
- **FR-013**: The report MAY display the fields approved by the owner, including user login, email address, IP address, hardware and serial details, password-expiry status, event-log entries, and crash/reliability details. These fields MUST NOT be redacted from the report.
- **FR-014**: The full report contents MUST NOT be copied into the persistent audit record; the audit MUST retain only the action outcome, overall status, score, counts, and sanitized timing/result metadata.
- **FR-015**: On a successful check, the system MUST attempt to display and verify Reliability Monitor on the user's Windows desktop, showing it exactly once.
- **FR-016**: The system MUST attempt to capture visual evidence of the Reliability Monitor result; failure to display or capture it MUST be reported separately from the health-check result.
- **FR-017**: The chat response MUST summarize the overall health status, score, counts, and the most relevant reliability findings, and MUST also return the complete HTML report verbatim in `report.html` (owner override 2026-11-22). The same complete report MUST be written to `%LOCALAPPDATA%\Temp\selfcheck.html`; when written, that path MUST be the visible report reference and the temporary `/mcp-action/reports/` URL MUST NOT appear in the answer.
- **FR-018**: When the report indicates warnings, failures, or recurring crashes, the response MUST identify the affected areas and direct the user to HelpDesk for repairs; the system MUST NOT perform a repair or create an automatic HelpDesk request.
- **FR-019**: The health check MUST complete within a fixed 180-second action budget, including the diagnostic run, report publication, display verification, and capture attempt, unless a larger budget is explicitly approved and documented.
- **FR-020**: Missing, restricted, or unavailable checks MUST appear as explicit skip/info outcomes; the system MUST NOT fabricate a passing result or claim complete coverage.
- **FR-021**: Failure to execute the diagnostic, generate the report, publish the report URL, or display Reliability Monitor MUST be surfaced honestly as an error or partial result without inventing evidence.
- **FR-022**: Existing reviewed-action consent, expiry, conversation isolation, desktop-wide serialization, duplicate-confirmation protection, and unrelated-request invalidation rules MUST continue to apply to this action.
- **FR-023**: The health-check action MUST be available only in the same approved assistant lanes as the existing reviewed-action capability and MUST NOT alter General-local, PPT-Master, or unrelated Office/Windows behavior.
- **FR-024**: The user's request for a repair MUST be routed to HelpDesk guidance only; the system MUST NOT create an automatic HelpDesk request, route an automatic repair action, or modify the system.
- **FR-025**: No password, MFA code, access token, client secret, or other credential may be requested, collected, placed in the report, or stored by the health-check action.

### Key Entities

- **HealthCheckProposal**: The conversation-specific pending request to run the read-only diagnostic, with its exact action identity, creation turn, expiry, and unresolved state.
- **HealthCheckResult**: The diagnostic outcome, overall status, score, check counts, computer/user/hardware inventory, individual check outcomes, reliability records, timeline, and remediation recommendations.
- **DiagnosticReport**: The temporary HTML report generated from the health-check result, including the owner-approved system and reliability details, with a 15-minute access URL.
- **ReliabilityEvidence**: The recent crash/hang/Windows-failure records and daily timeline used to correlate symptoms with system events.
- **HelpDeskReferral**: The guidance shown to the user when repair is needed; it is not an automatic repair action.
- **AuditEvent**: A summary-only record of the proposal, decision, execution, verification, display/capture, refusal, timeout, and error outcomes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the acceptance suite, 100% of eligible health-check answers present the exact automatic-action offer only after manual guidance, and 0% of ineligible or out-of-scope answers present that offer.
- **SC-002**: Across no, cancellation, modified, orphaned, repeated, and expired-confirmation cases, 100% result in no health-check execution and no system change.
- **SC-003**: At least 95% of successful checks on the target Windows 11 environment deliver a report URL and a verified Reliability Monitor display within 180 seconds.
- **SC-004**: 100% of successful health-check summaries report the overall status, score, pass/warn/fail counts, and reliability summary, the complete HTML report is present in the answer, the `%LOCALAPPDATA%\Temp\selfcheck.html` file exists, the visible report reference is that file path, and the temporary report URL (internal fallback) resolves before expiry.
- **SC-005**: 100% of results containing warning, failure, or recurring-crash findings direct the user to HelpDesk for repair, perform no repair automatically, and create no automatic HelpDesk request.
- **SC-006**: 100% of report URLs stop serving content after expiry, and persistent audit records contain no full report, user login, email, IP address, hardware serial, password-expiry detail, event text, or crash text.
- **SC-007**: At least 90% of user-acceptance participants can identify the overall desktop health result, the most important reliability finding, and the next step (HelpDesk or no action needed) from the chat summary and report link.

## Assumptions

- The user has an interactive Windows 11 desktop and an authorized single-user local deployment.
- The agreed read-only diagnostic routine and its generated report are the implementation basis; the routine remains read-only and is invoked as a fixed reviewed action rather than arbitrary model-authored code.
- The owner explicitly approved displaying the potentially identifying system and reliability fields in the report. Those fields are not considered a blocker to showing the report in this deployment.
- Repairs and system changes are outside this feature and are handled through HelpDesk guidance only; no automatic HelpDesk request is created.
- The health-check result and the Reliability Monitor display are separate outcomes; a display or screenshot failure does not undo or invalidate a completed read-only diagnostic.
- The report URL is a temporary 15-minute access mechanism, not a durable report store or audit artifact.
- Existing reviewed-action timing, consent, expiry, serialization, and audit-summary behavior applies to this action.
- The action is available only in the same approved assistant lanes as the existing reviewed-action capability; General-local and PPT-Master remain unchanged.
- Explicit requests to run the system health check are eligible even without a detailed instability narrative.
- Fixed diagnostic defaults are used; the user is not asked to supply internal logging, event-window, or reliability-record parameters.
