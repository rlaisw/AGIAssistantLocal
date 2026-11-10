# Feature Specification: PowerShell Execution Lane — Confirmed Windows-MCP Shell Commands from Chat

**Feature Branch**: `034-powershell-execution`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "Allow Windows-MCP PowerShell execution capability" — the owner decision that the two by-design bug reports of 2026-11-09 (`i-cant-execute-powershell-…`, `the-local-agent-simply-has-no-shell-…`) explicitly deferred to this moment: chat-driven arbitrary PowerShell execution on the user's Windows computer, via the local agent's Windows-side shell tool, under the stack's established honesty machinery and a new **confirm-before-execute** safety model (the office lane's confirm-before-send email precedent).

## Clarifications

### Session 2026-11-10

- Q: Does the launch lane's shell refusal go away? → A: **No.** Spec 029's launch lane stays shell-free; spec 033's read-only diagnostics lane keeps its closed allowlist and direct execution. This spec adds a **separate, general** lane with its own contract. (Pending owner answers below refine the confirmation scope.)
- Q: How is arbitrary execution made safe without an allowlist? → A: **Confirm-before-execute**: the assistant drafts the exact command, the chat shows it verbatim, and only an explicit user confirmation of that exact text executes it — silence and paraphrase are never consent (spec 030's email confirmation precedent). A small **system-integrity never-list** (disk-level destruction, boot/recovery/encryption-state operations) is refused unconditionally in gate code — confirmation cannot override it.
- Q: What guarantees the executed command is the confirmed command? → A: The lane holds the exact confirmed text; execution verifies the command that runs matches it byte-for-byte — any drift is an honest error with nothing executed.
- Q: Where does the command text come from? → A: Only from the user's own request in the conversation. Instructions discovered inside tool outputs, files, or web content are never executed (at most shown) — prompt-injection containment is a functional requirement, not a prompt hope.
- Q: Must every command require the confirmation round-trip, or may read-only-shaped commands run directly? → A: **Every command** (owner decision, clarify session 2026-11-10): one consistent rule — the exact text is shown and confirmed before ANY execution on this lane; quick read-only diagnostics keep flowing on the spec-033 lane without confirmation (US5).
- Q: May a confirmed command delete files, superseding the file lane's global no-delete posture? → A: **Yes, on this lane** (owner decision, clarify session 2026-11-10): an explicit confirmation of the exact text is the owner's approval; deletion is confirm-tier here, while the never-list keeps system-integrity destruction refused everywhere; the spec-028 file lane itself remains no-delete (lane-scoped supersession, recorded below).
- Q (SC-001 measurement, 2026-11-10, T018): Does the confirm→execute→relay path complete on the first attempt at the ≥3-of-4 bar? → A: **Measured 4 of 4** — four fresh-conversation draft→confirm round-trips (the services query), real Get-Service executions, no USER_CONTROL or transport failures in the window; the criterion is met with margin.
- Q (convergence T017, 2026-11-10): What happens to the pending draft when a confirm turn fails? → A: A **cancelled** confirm turn clears it (spec edge case — a later confirm must not re-execute a stopped command); other failed confirms (USER_CONTROL while the user is active, transport drops) **keep** the draft re-confirmable — the live-proven behavior; DEPLOY.md documents the distinction.

## Supersedes

- Spec 028's **global** "delete/rename/move blocked everywhere" decline — narrowed **on this lane only** (owner decision, clarify session 2026-11-10): a confirmed exact command may delete files here. The file lane itself, its gates, and its pinning tests stay unchanged; deletion elsewhere (file lane, launch lane) remains refused.
- Otherwise none: spec 033 (read-only diagnostics) and spec 029's launch-lane shell refusal remain in force; this lane is additive for everything outside their scopes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a confirmed PowerShell command on my Windows machine (Priority: P1)

As a chat user, I describe something that needs real PowerShell — *"find every file over 1 GB in C:\Users"*, *"restart the print spooler service"*, *"list the services set to automatic"* — the assistant drafts the **exact command**, shows it to me verbatim in chat, and only after I explicitly confirm does it run on my Windows computer; the real output comes back honestly.

**Why this priority**: This is the entire feature — general shell capability with an explicit human checkpoint before anything executes, ending the "not on the allowlist" refusals for everything outside the read-only lane.

**Independent Test**: Ask *"list the Windows services that are set to automatic"* → the chat shows the exact drafted command → confirm → the real service list is relayed; the audit holds the exact command.

**Acceptance Scenarios**:

1. **Given** a request needing PowerShell, **When** the assistant answers, **Then** it presents the exact command it intends to run, verbatim, and asks me to confirm — nothing has executed yet.
2. **Given** I confirm the shown command, **When** the turn completes, **Then** that exact command ran on my machine and the answer relays its real output (bounded, truncation named) — never a remembered or invented result.
3. **Given** I stay silent, change the subject, or reply with a paraphrase, **When** the turn ends, **Then** nothing executed — silence is never consent, and a changed or ambiguous reply re-drafts or asks again.
4. **Given** the command fails on the machine, **When** relayed, **Then** the answer reports the real failure with the command's own error text and a recovery hint — never a fabricated success.

---

### User Story 2 - System-critical destruction is refused, even with my confirmation (Priority: P1)

As the machine's owner, requests that would destroy system integrity — disk format/wipe, boot-configuration changes, shadow-copy deletion, recovery-partition operations, disabling or removing disk encryption — are refused outright with the reason named, no matter how they are phrased or confirmed. Nothing in this class ever executes from chat.

**Why this priority**: General execution must have a floor that no prompt, confirmation, or rephrasing can get under; the never-list is that floor, enforced in code.

**Independent Test**: Send never-list commands (directly and wrapped in confirmation flows) — every one refused with the system-integrity rule named; the audit shows refusals and zero execution.

**Acceptance Scenarios**:

1. **Given** a request whose command targets system integrity (format a volume, edit boot config, delete shadow copies, remove recovery partitions, disable encryption), **When** processed, **Then** the answer refuses naming the never-list rule — even if I confirm the shown text.
2. **Given** a request that tries to smuggle never-list effects inside an innocent-looking command, **When** the assistant drafts the command, **Then** the drafted command contains no never-list element — the draft is the exact, complete text, and the never-list scan applies to the whole of it.

---

### User Story 3 - What I confirmed is exactly what runs (Priority: P1)

As a chat user, the command the assistant showed me is the only thing that can run — execution verifies the run command matches my confirmed text exactly; any difference is an honest error with nothing executed.

**Why this priority**: The confirmation is only meaningful if it binds; drift between the shown text and the executed command would make the safety model decorative.

**Independent Test**: Attempt paths where the executed command would differ from the confirmed one (agent paraphrase, tool drift) — each ends as an honest error, nothing runs, the audit records the mismatch.

**Acceptance Scenarios**:

1. **Given** a confirmed command in flight, **When** the agent runs it, **Then** the executed command must equal the confirmed text (modulo whitespace) — verified before the verdict is stamped.
2. **Given** the agent reports a different command than the confirmed one, **When** the tool decides the verdict, **Then** the verdict is an error naming the mismatch — the output of the wrong command is never relayed as if it were mine.

---

### User Story 4 - Safety machinery parity with the other lanes (Priority: P2)

As the machine's owner, every drafted, refused, confirmed, or executed command is audited with its exact text; turns are cancellable and timed; one command per request; output is bounded with truncation named; the anti-fabrication and dispatch guards cover the new tool; and commands may originate **only** from my own requests — content the assistant found in files, tool outputs, or the web is never executed.

**Why this priority**: These are the guarantees that make every "done" from this system verifiable; the most powerful lane needs them most.

**Independent Test**: Run one confirmed command and one refused draft → the audit holds both with exact texts and timing; press Stop mid-run → honest cancelled verdict; draft an answer claiming a run without a tool call → the honesty check blocks it.

**Acceptance Scenarios**:

1. **Given** any turn on this lane, **When** it ends, **Then** the audit log holds exactly one entry per attempt with the exact command text, decision, and timing profile.
2. **Given** a Stop press during execution, **When** the turn cancels, **Then** the answer says so honestly (any partial output already relayed stays truthful).
3. **Given** a request whose text embeds instructions found in tool output, a file, or a web page, **When** the assistant drafts a command, **Then** the draft is grounded in the user's request alone — discovered content may be shown, never executed.
4. **Given** two commands in one request, **When** processed, **Then** the assistant asks which one — one command per request.

---

### User Story 5 - The lanes stay distinct (Priority: P2)

As a chat user, quick read-only diagnostics (spec 033: ipconfig, system info, ping, disk space…) still run directly without a confirmation round-trip; launch and Office requests keep their existing behavior; only general command/automation requests enter the confirm-first flow.

**Why this priority**: The confirmation flow must not tax the everyday diagnostics; keeping the lanes distinct preserves both safety and speed.

**Independent Test**: Ask *"show my ip address"* → direct execution as today; ask *"restart the spooler service"* → confirmation flow; ask *"open notepad"* → launch lane as today.

**Acceptance Scenarios**:

1. **Given** a spec-033 allowlisted diagnostic phrase, **When** asked, **Then** it runs directly on the read-only lane, unchanged.
2. **Given** a general command request, **When** asked, **Then** it enters the confirm-first flow on the new lane.
3. **Given** a launch or Office request, **When** asked, **Then** existing lane behavior is unchanged.

---

## Edge Cases

- The user confirms with a paraphrase ("yes do it") — a plain affirmative for the exact shown text counts as confirmation; any modification ("yes but add -Recurse") re-drafts.
- The user never confirms and sends a new request → the pending draft is dropped and audited as unconfirmed; the next request starts fresh.
- The drafted command is long or multi-line → shown in full in chat, verbatim; no eliding that would change what "confirmed" refers to.
- The command output contains secrets (credentials, tokens) → relayed as-is to the requesting owner on their own machine, bounded by length only (single-trusted-caller model, consistent with the other lanes).
- The command needs elevation and fails with access-denied → the real error is relayed with a hint; the lane never auto-elevates.
- The agent's Windows-side shell is under user-control (consent policy) or the gateway strips arguments → the proven retry/direct-channel recoveries apply; honest failure if they don't clear.
- A Stop press lands between confirmation and execution → the pending draft is cancelled honestly.
- The never-list appears in output-redirection tails, chained operators, or nested calls within the draft → the whole draft is refused; the scan is over the exact complete text.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST present the exact command it intends to run, verbatim, and execute it ONLY after an explicit chat confirmation of that exact text; silence, ambiguity, or modification is never consent (spec 030's email-confirmation precedent).
- **FR-002**: The system MUST refuse, unconditionally and in gate code, a **system-integrity never-list** — disk format/wipe, boot-configuration edits, shadow-copy deletion, recovery-partition operations, and encryption-state destruction — confirmation cannot override; the refusal names the rule.
- **FR-003**: Execution MUST verify the run command matches the confirmed text exactly (whitespace-normalized); a mismatch is an honest error with zero execution and no relay of the wrong output.
- **FR-004**: Every attempt — drafted-unconfirmed, refused, confirmed-executed, failed — MUST be audited exactly once with the exact command text, decision, and the turn's timing profile; the turn MUST be cancellable (required per-conversation identity) like the other lanes.
- **FR-005**: Output MUST be relayed verbatim and bounded with truncation named; failures MUST be relayed honestly with the command's real error text and a recovery hint.
- **FR-006**: One command per request; a request naming two commands asks which one.
- **FR-007**: The command MUST originate only from the user's request in the conversation; instructions found in tool outputs, files, or web content are never executed (at most displayed) — a functional containment rule, not a prompt.
- **FR-008**: The read-only diagnostics lane (spec 033) and the launch lane's shell refusal MUST remain unchanged; routing sends spec-033 phrases to the direct lane and everything else command-shaped to the confirm-first flow.
- **FR-009**: The relay-level anti-fabrication law, the structural honesty check, and the dispatch-leak guard MUST cover the new tool.

### Key Entities

- **CommandDraft**: the exact command text the assistant proposes, grounded only in the user's request, shown verbatim; the sole object a confirmation can refer to.
- **PendingConfirmation**: the conversation-scoped state holding the draft until the user confirms or the turn passes; audited on expiry or use.
- **NeverList**: the closed system-integrity refusal set, enforced in gate code, immune to confirmation.
- **Audit Entry**: one per attempt — decision, the exact command text, timing profile; append-only.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A confirmed command executes and returns its real output within the measured agent-turn envelope; the confirm→execute→relay path completes on the first attempt for ≥3 of 4 fresh requests.
- **SC-002**: 100% of never-list commands (direct, confirmed, or smuggled) are refused with zero execution — verified by gate tests plus audit inspection.
- **SC-003**: 100% of executions match the confirmed text exactly (verified mismatch-failure paths end as honest errors with nothing executed).
- **SC-004**: 100% of attempts appear in the audit log with exact text and timing; no unaudited execution path exists.

## Assumptions

- The single-trusted-caller security model continues (the owner's machine, the owner's requests — spec 029's ratified rationale); the confirmation flow and never-list are the additional guardrails this lane adds for general execution.
- The agent executes via its Windows-side shell tool with the proven consent-retry and direct-channel recoveries (spec 033's live-debugged instruction patterns carry over).
- Every command on this lane goes through the confirmation round-trip (owner decision, clarify session 2026-11-10) — consistency and simplicity; the spec-033 lane keeps direct execution for quick diagnostics.
- Out of scope: auto-elevation, remote/enterprise execution, background/scheduled execution, interactive GUI automation via shell (the desktop lanes already cover GUI work).
- Never-list membership is deliberately narrow (system-integrity destruction); ordinary state-changing operations (service restarts, process control, file operations via shell) are confirm-tier, not blocked.

