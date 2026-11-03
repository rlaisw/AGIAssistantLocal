# Feature Specification: Hermes Office Task Lane — Prompt-Driven Office Execution

**Feature Branch**: `030-hermes-office-tasks`

**Created**: 2026-11-02

**Status**: Draft

**Input**: User description: "add prompt-driven, end-to-end Office task execution" — extended by the design discussion: a third Hermes capability that lets one chat prompt drive real Office work on the user's Windows machine through the already-installed Office automation service (OfficeMCP v1.0.5, Windows side, work folder `C:\OfficeMCP`, SSE mode available). Chain: prompt → Dify → Hermes agent → Office tool service → **Word, Excel, PowerPoint, Outlook**. Owner's acceptance examples: *"open Excel, input 12345 at cell A1"* and *"Launch Outlook → new email → type 'test Hello World' → send to raymond.lai@tvb.com.hk"*.

## Clarifications

### Session 2026-11-02 (defaults chosen — adjustable via `/speckit.clarify`)

- Q: Who bridges to the Office tool service? → A (owner's stated design): the Hermes local-agent pathway reaches the already-installed Office automation service on the Windows side; the sidecar remains the **single gated, audited entry** for every Office task — Dify never talks to Office tooling directly (preserves the 028/029 architecture). The exact bridge mechanism (agent-native MCP client vs. sidecar proxy) is a plan-phase decision, gated on two live probes: the local agent's tool-client capability and service reachability from the agent host.
- Q: Which applications are in scope? → A: all four named apps — **Word, Excel, PowerPoint, Outlook** — are capability targets; v1 acceptance exercises **Excel** and **Outlook** (the owner's two examples); Word/PowerPoint ride the same pattern.
- Q: Are read operations in scope? → A: Yes for documents (e.g. *"what is in cell B2"*) where the tool supports them; **mailbox reading is deferred with attachments** — v1 email scope is compose + send.
- Q: What about destructive operations? → A: document edits **inside the work folder are the sandbox** — allowed; mailbox-destructive operations (delete mail, purge folders) are out of scope v1.
- Q: Can cell content be executable? → A: No. Cell writes store **literal values**; content that could execute (macros, DDE, external-link formulas, embedded code) is refused or stored inertly as text — never in executable form. The Office code-execution surface is forbidden at every layer.
- Q: How are multi-step tasks handled? → A: a task is a **bounded sequence of steps** (launch → open/create → edit/compose → send/save); every step's outcome is reported honestly; a failed step stops the chain with the state reported as partial — later steps are never claimed done when an earlier one failed.
- Q: When the prompt says "send", does the email leave immediately or wait for confirmation? → A (owner decision, 2026-11-02): **confirm-before-send** — compose immediately, show the draft verbatim (recipient(s), subject, body), and send **only after the user confirms in the chat**; silence or an ambiguous reply is never treated as consent. Rationale: outbound email is the lane's only irreversible external action — spec 029's immediate-execution precedent applied to local, reversible launches, a different risk class. Recorded as the FR-009 policy.
- Q: How long does a pending email draft stay sendable after it is shown for confirmation? → A (owner decision, 2026-11-02): the pending draft lives in the conversation **until resolved** — a confirmation sends it (even turns later), cancelling or a new compose request drops it, and any requested modification re-displays the final draft and requires a fresh confirmation. The draft shown is the draft that sends, unchanged.
- Q: When a follow-up message continues an earlier Office task (e.g. *"also write 'hello' in B2"* after a workbook was just written), does the assistant continue on the same document? → A (owner decision, 2026-11-02, clarify pass 2): yes — the conversation keeps an **active document**: follow-ups without a named file continue on the last document this conversation created/edited, the answer names the file every time; no active file yet → ask-back; naming a different file switches the active document.
- Q: How far should one long multi-step prompt go in a single turn? → A (owner decision, 2026-11-02, clarify pass 2): **no artificial step cap** — attempt the whole task; if the turn budget runs out, stop at the last completed step, report the partial state and the remaining steps honestly, and resume on "continue".
- Q: Does v1 handle formatting (bold, colors, number formats, column widths)? → A (owner decision, 2026-11-02, clarify pass 2): no — v1 writes **literal content only**; formatting requests get an honest out-of-scope notice, and formatting is a named follow-up version.
- Q: After a document task, does the Office application stay open or save-and-close? → A (owner decision, 2026-11-02, clarify pass 2): **leave the app open**, file saved — the user sees the result on screen; the answer names the saved path; closing applications stays out of scope v1 (consistent with the launch lane).

## Supersedes

- Spec 029, Out of Scope ("GUI automation (clicking/typing into windows)", "passing documents or any arguments to a launched app") — **narrowed for the four Office apps**: bounded, typed Office operations (open/read/write cells, text, slides; compose/send email) are now in scope on this lane, including structured parameters. Raw GUI automation of arbitrary (non-Office) applications and general click/keyboard injection remain out of scope everywhere. Spec 028's file lane and FR-009 are untouched.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - "Open Excel, input 12345 at cell A1" (Priority: P1) 🎯 MVP

As a chat user, I type one prompt and the workbook exists afterwards in the Office work folder with the value in the stated cell — verifiable by opening it, and every step is reported honestly.

**Why this priority**: the owner's first acceptance example — document write end-to-end is the core of the feature.

**Independent Test**: send the exact prompt → a workbook appears under the work folder → open it → cell A1 shows `12345` → the answer names the file and each step → the audit trail holds one truthful entry per executed step.

**Acceptance Scenarios**:

1. **Given** I prompt to open Excel and write a value to a cell without naming a workbook, **When** processed, **Then** a new workbook is created inside the work folder, the value is written, the file is saved, Excel is left open showing the result, and the answer names the file's location.
2. **Given** the prompt names an existing workbook, **When** processed, **Then** that workbook is updated and the change is reported.
3. **Given** the prompt names no workbook and this conversation has no active document, **When** processed, **Then** the assistant asks back instead of guessing — a follow-up with an active document continues on it, naming the file.
4. **Given** the prompt points at a document path outside the work folder, **When** processed, **Then** it is refused with the active folder named; nothing is written.
5. **Given** the requested cell content could execute (macro, `=`-external-link formula, script), **When** processed, **Then** it is refused or stored as inert text — never in executable form.

---

### User Story 2 - "Launch Outlook, new email, send it" (Priority: P1) 🎯 MVP

As a chat user, I describe an email in one prompt — recipient, subject, body — and the assistant composes it immediately, shows me the draft, and sends it once I confirm in the chat, reporting each step honestly.

**Why this priority**: the owner's second acceptance example; email is the lane's outbound channel and its highest-risk surface.

**Independent Test**: send the exact example prompt → the email is composed with exactly the dictated content and the draft is shown → I reply to confirm → the message appears in Sent Items → the answer and audit reflect each step truthfully.

**Acceptance Scenarios**:

1. **Given** I prompt to create an email with recipient(s), subject, and body, **When** processed, **Then** the draft contains exactly what I dictated — relayed verbatim, never invented or reworded silently.
2. **Given** the prompt asks to send, **When** processed, **Then** the draft is composed and shown verbatim (recipient, subject, body) and is **sent only after I confirm in the chat** (owner decision: confirm-before-send); each step's outcome — composed, awaiting confirmation, sent — is reported honestly.
3. **Given** the prompt names a recipient only vaguely ("send it to Raymond") with no address given, **When** processed, **Then** the assistant asks back for the exact address — it never guesses from contacts.
4. **Given** any step fails (Outlook unavailable, send rejected), **When** processed, **Then** the state is reported as partial with the failing step named; nothing later is claimed done.

---

### User Story 3 - Dangerous and out-of-policy requests are refused, never executed (Priority: P1)

As the machine's owner, any request for macros, scripts, DDE, executable cell content, documents outside the work folder, mailbox-deletion, or recipients I did not name must be refused with the reason named — nothing executes.

**Why this priority**: this lane touches the user's real Office identity and mail; the refusal matrix is co-equal with the happy path.

**Independent Test**: send the refusal matrix (macro request, DDE formula, out-of-folder path, "delete my emails", recipient not stated by the user) — every one refused with a reason; the audit trail shows refusals and no executions.

**Acceptance Scenarios**:

1. **Given** a prompt requesting macro creation, script execution, DDE, or any Office code-execution feature, **When** processed, **Then** it is refused with the code-execution rule named.
2. **Given** a prompt pointing at documents outside the active work folder, **When** processed, **Then** it is refused with the folder named.
3. **Given** a prompt requesting mailbox-deletion or other destructive mailbox operations, **When** processed, **Then** it is refused as out of v1 scope.
4. **Given** a prompt that would email a recipient the user did not name, **When** processed, **Then** it is refused — recipients come only from the user's prompt (or ask-back).

---

### User Story 4 - Word and PowerPoint ride the same pattern (Priority: P2)

As a chat user, I can create or edit a Word document or a PowerPoint slide with dictated text using the same rules: work-folder containment, literal content, honest step reports, same refusals.

**Why this priority**: completes the four-app promise; adds no new rules — it is the same pattern proven by stories 1–3 applied to two more apps.

**Independent Test**: *"create a Word document called notes.docx with the text 'hello world'"* → the file exists in the work folder with the text; *"add a slide saying 'Q3 results'"* → the deck updates; both reported step-honestly.

**Acceptance Scenarios**:

1. **Given** a prompt to create/edit a Word document or PowerPoint deck with dictated content, **When** processed, **Then** the document is created/updated inside the work folder with the literal content, saved, and reported step by step.
2. **Given** the same refusal matrix applied to Word/PowerPoint targets, **When** processed, **Then** the same refusals apply with the same reasons.

---

## Edge Cases

- Office application missing, unlicensed, or failing to start → honest error naming the app; nothing fabricated.
- The Office automation service is unreachable or not running → honest error with the recovery hint for starting it; the chat stays usable for every other lane.
- The named workbook is already open with unsaved changes → the state is reported honestly and the assistant asks how to proceed; it never silently overwrites.
- A prompt mixes lanes (*"open Excel, write A1, and also create a folder in C:\temp"*) → each lane handles its own part; all verdicts are reported.
- The chat Stop button is pressed mid-task → the visible answer stops; completed steps stand, uncompleted steps are reported as such; the audit trail holds the truth.
- Attachment requests (*"send the file x.xlsx as an attachment"*) → honest out-of-scope notice (v1: no attachments), not a silent ignore.
- Formatting requests (*"make A1 bold"*, *"color the header"*) → honest out-of-scope notice naming formatting as a follow-up version, not a silent ignore.
- I change my mind on a pending draft (cancel) → the email stays unsent, the draft is dropped, and that outcome is reported honestly; the assistant never sends without my explicit confirmation.
- The turn budget runs out mid-task → the chain stops at the last completed step; the answer reports the partial state and the remaining steps; "continue" resumes it (a mid-flight append while a task is running is a new follow-up, handled after the current task reports).
- I confirm several turns later in the same conversation → the draft I was shown (unchanged) is sent — a pending draft lives until resolved; a NEW compose request replaces the pending draft rather than creating a second one.
- I ask to modify the pending draft (*"send it, but to X instead"*) → the assistant re-displays the final draft and requires a fresh confirmation; it never silently amends a shown draft.
- An ambiguous confirmation reply → the assistant re-relays the pending draft and asks again; silence is never consent.
- Vague targets (*"update my report"* with no file named, *"send it to Raymond"* with no address) → ask-back; never guessed — except a document follow-up with an **active document** in the conversation, which continues on it, naming the file.
- A follow-up names a different file (*"now edit report.xlsx instead"*) → the active document switches, and the answer names the switch.
- The active document was moved, renamed, or deleted outside the conversation → honest error naming the file, ask-back for the new target; nothing is silently recreated.
- Cell ranges, multiple cells, or longer dictated text → handled as literal content in one bounded task; anything ambiguous asks back.
- The user is actively using the Office app when a task runs → the assistant reports interference honestly if the task cannot complete.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Prompts recognized as Office tasks (control of Word/Excel/PowerPoint/Outlook: open, read, write, compose, send) MUST route to the Office lane; launch-only prompts keep routing to the launch lane (spec 029); file tasks to the file lane (spec 028); every other lane keeps today's behavior with zero regression.
- **FR-002**: Every Office task MUST pass the same pre-execution gate and append-only audit as the other Hermes lanes — the sidecar remains the single gated, audited entry; Dify MUST NOT reach Office tooling directly.
- **FR-003**: Document operations MUST be confined to the active Office work folder (default `C:\OfficeMCP`); paths outside it are refused with the folder named.
- **FR-004**: The Office code-execution surface — macros, scripts, DDE, external-link formulas, embedded or linked code — MUST be refused (or stored inertly as literal text) at every layer; no prompt content may be stored in executable form.
- **FR-005**: A multi-step task MUST execute as a bounded sequence: each step's outcome is reported honestly; on any step failure the chain stops, the partial state is reported, and later steps MUST NOT be claimed done. There is **no artificial step cap** (owner decision, 2026-11-02): a task of any length is attempted in full; if the turn budget is exhausted mid-task, the chain stops at the last completed step, the remaining steps are reported, and a "continue" request resumes the sequence.
- **FR-006**: The task verdict MUST use the honest envelope: `ok` only when every requested step completed; `error` names the failing step with a recovery hint; `blocked` names the violated rule — never a fabricated result (Constitution IV).
- **FR-007**: Every executed step and every refusal MUST be recorded in the existing append-only audit log (one entry per step: app, operation class, decision, outcome/reason); the log is never rewritten or pruned.
- **FR-008**: Email composition MUST use exactly the recipient(s), subject, and body the user dictated — relayed verbatim, never invented; a missing address MUST trigger an ask-back, never a guess from contacts.
- **FR-009**: Email sending MUST follow the confirm-before-send policy (owner decision, 2026-11-02): composing is immediate — the assistant shows the draft (recipient(s), subject, body) verbatim — and the email is sent **only after the user confirms in the chat**; a "send" instruction alone never dispatches an email in the same turn, and silence or an ambiguous reply is never treated as consent. The pending draft is **conversation-scoped and lives until resolved**: a later confirmation in the same conversation sends the unchanged draft; cancelling or starting a new compose request drops it; any requested modification re-displays the final draft and requires a fresh confirmation. A declined or cancelled confirmation leaves the draft composed-but-unsent, reported honestly.
- **FR-010**: Launching an Office application that is not running MUST be part of the task (the agent starts it via its Office tools — same outcome as the launch lane) — *"open Excel and write…"* does both, reported step by step.
- **FR-011**: If the Office automation service or an Office application is unavailable, the answer MUST report the failure honestly with a recovery hint; the chat MUST remain usable for all other lanes.
- **FR-012**: Existing lanes stay byte-identical in behavior: the file lane (spec 028), the launch lane (spec 029 — *"open Excel"* with no task still just launches), and their contract tests pass unchanged.
- **FR-013**: A follow-up request that names no file MUST continue on the conversation's **active document** (the last document this conversation created/edited), with the file named in the answer; naming a different file switches the active document. An ask-back happens only when no target can be resolved — no file named **and** no active document, no address when one is required, or an unresolvable target; nothing is assumed or executed.

### Key Entities

- **OfficeTask**: one prompt's bounded sequence of steps, targeting one application (plus launching it when needed).
- **TaskStep**: app, operation class (open/create/read/write/compose/send/save), parameters (literal content, cell, address, subject), and outcome — the unit of honest reporting and auditing.
- **OfficePolicy**: the per-app allowed operation set — structural operations allowed; code-execution (macros/DDE/scripts) forbidden; mailbox-destruction out of scope; work-folder containment.
- **AuditEntry**: one append-only record per executed step and per refusal: timestamp, decision, app, operation class, reason/outcome.
- **PendingDraft**: the conversation-scoped email awaiting confirmation — the exact recipient(s)/subject/body shown to the user; it lives until resolved (confirmed → sent; cancelled or replaced → dropped) and is the only thing a confirmation may send.
- **ActiveDocument**: the conversation-scoped document a follow-up continues on (the last one this conversation created/edited); naming a different file switches it; the answer names it on every write.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: *"open Excel, input 12345 at cell A1"* completes end-to-end within the local agent's turn bounds: the workbook exists in the work folder, A1 reads `12345` when opened, and the audit trail holds one truthful entry per step.
- **SC-002**: The Outlook example composes exactly the dictated email; after the user's chat confirmation the message lands in Sent Items — with the step-by-step answer and audit matching reality (composed → confirmed → sent).
- **SC-003**: 100% of the refusal matrix — macros/scripts/DDE, executable cell content, out-of-folder paths, mailbox deletion, uninvented-recipient violations — is refused with a named reason; zero executions on refusals.
- **SC-004**: The existing automated test suite and deploy battery stay green; the 028/029 lanes' probes pass unchanged; the rest of the battery is unaffected.
- **SC-005**: For every test task, the audit log contains exactly one truthful entry per executed step and refusal, and never claims a step that did not happen.

## Out of Scope (v1)

- Email attachments; reading, archiving, or deleting mailbox content (v1 email = compose + send only).
- Calendar, meetings, contacts management.
- Macros, scripts, DDE, and any Office code-execution feature — permanently, not just v1.
- GUI automation of non-Office applications (mouse/keyboard injection) — spec 029's exclusion stands outside this lane.
- Bulk/mass email generation (recipient sets beyond what the user explicitly names).
- Formatting (bold, fonts, colors, number formats, column widths) — deferred to a named follow-up version; v1 writes literal content only.
- Closing/quitting Office applications — consistent with the launch lane's v1 exclusion; the file is saved and the app stays open.
- Multi-application chained workflows beyond one task's bounded steps (e.g. "read Excel, chart it, paste into PowerPoint, mail it" — a named follow-up candidate).

## Assumptions

- The Office automation service (OfficeMCP v1.0.5) is already installed on the Windows side with work folder `C:\OfficeMCP` and offers a network mode (SSE) the local-agent pathway can reach; reachability and the agent's tool-client capability are plan-phase research items (they decide the bridge mechanism, not the capability).
- The Office suite is installed and licensed on the machine; WSL interop remains enabled (spec 029 prerequisite).
- The trusted single-owner security model of specs 028/029 continues: the caller is the machine's owner; containment (work folder), the code-execution ban, and the append-only audit are the guardrails.
- The exact operation set exposed by the installed service is discovered at plan time and mapped onto these capability classes; the spec's policy rules hold regardless of the mapping.
- The email-send policy (FR-009) is resolved: **confirm-before-send** (owner decision, 2026-11-02); every other default above is adjustable at `/speckit.clarify`.
