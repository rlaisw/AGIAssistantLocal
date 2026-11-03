# Feature Specification: Office Save Anywhere — user-named save locations on any folder

**Feature Branch**: `031-office-save-anywhere`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "allow officemcp to save file to any folders" — extended by the design history: bug `no-powerpoint-tool` surfaced the lane-root mismatch ("a PowerPoint at c:\temp\test fits no lane") and surfaced the owner-configurable `office_root` knob; bug `fail-to-save-file` fixed punctuation false refusals. The owner now chooses to remove the location boundary: an Office task may name **any folder** as its save (or read) location, not only the Office work folder.

## Clarifications

### Session 2026-11-03 (defaults chosen — adjustable via `/speckit.clarify`)

- Q: Does "any folders" include protected system locations (e.g. `C:\Windows`, `Program Files`)? → A: **Yes — the operating system's own permission rules are the guardrail.** The lane never elevates privileges; a save into a protected location succeeds or fails exactly as the signed-in user's permissions allow, and the outcome is reported honestly. (The lane adds no artificial system-directory list — the owner's own reach is the policy.)
- Q: May an Office task overwrite an existing file at a user-named location? → A: Yes, **when the user's task names that exact file** (naming an existing file is intent); the answer reports the overwrite honestly. An unsaved-changes conflict in the open application still asks back first (carried from spec 030's edge case).
- Q: Are reads widened too? → A: Yes — consistently: an Office task may name any location to open/read, not only to save.
- Q: What if the task names no location at all? → A: Unnamed saves continue to go to the **default work folder** (`C:\OfficeMCP`, owner-configurable via `office_root`) — the folder becomes a default, no longer a boundary.

## Supersedes

- Spec 030, **FR-003** ("Document operations MUST be confined to the active Office work folder") — **replaced**: document save/read operations MAY target any local location the user's task explicitly names; the work folder remains the default for unnamed tasks. Spec 030's corresponding edge case ("a path outside the work folder is refused with the folder named") is retired with it. This also resolves the "no lane fits" gap documented in bug `no-powerpoint-tool` ("a PowerPoint at c:\temp\test" now simply works). All other spec 030 rules stand unchanged.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Save to any folder the user names (Priority: P1) 🎯 MVP

As a chat user, I ask for a document at a location of my choosing — *"create a PowerPoint with the text 'Hello', file name test1, save to c:\temp\test"* — and the file appears there, with the answer reporting the exact saved location.

**Why this priority**: the owner's literal request, and the exact case that previously fit no lane.

**Independent Test**: send that prompt → `c:\temp\test\test1.pptx` exists with "Hello" in it → the answer names the full saved path → the audit records the full target.

**Acceptance Scenarios**:

1. **Given** I prompt an Office task naming a save location outside the work folder, **When** processed, **Then** the document is created at exactly that location and the answer names it.
2. **Given** the prompt names no location, **When** processed, **Then** the save goes to the default work folder as today.
3. **Given** the prompt names a location on another drive (`D:\projects\`), **When** processed, **Then** the save works there if the user's permissions allow, or fails honestly with the operating system's error.

---

### User Story 2 - Overwrite an existing file the user names (Priority: P1)

As a chat user, when I explicitly name an existing file as the save target — *"update D:\docs\report.docx with …"* — the update is applied and the answer says the existing file was replaced; if the file has unsaved changes open in the application, the assistant asks before proceeding.

**Why this priority**: writes outside the sandbox make overwrites the one irreversible risk class; the rule must be explicit from day one.

**Independent Test**: create a file at a named location, then prompt an update naming that exact file → content updated, answer reports the overwrite; a file with unsaved interactive changes → ask-back, nothing written.

**Acceptance Scenarios**:

1. **Given** the task names an existing file as the target and the application holds no unsaved interactive changes for it, **When** processed, **Then** the file is updated and the answer states that an existing file was replaced.
2. **Given** the application has the named file open with unsaved changes, **When** processed, **Then** the assistant asks back before writing; it never silently discards the user's open edits.
3. **Given** the task does NOT name the file but the assistant would have to pick one (ambiguous target), **When** processed, **Then** it asks back — it never guess-overwrites.

---

### User Story 3 - Everything else stays exactly as it was (Priority: P1)

As the machine's owner, widening save locations changes **nothing else**: the code-execution ban, literal-content and formatting rules, email confirm-before-send, the launch lane, and the file lane all behave byte-identically; protected-location failures answer honestly with the operating system's own error.

**Why this priority**: a scope-widening change must prove it widened one thing only.

**Independent Test**: run the existing regression battery + the refusal matrix (macros, DDE, formatting, email rules) — all outcomes identical to pre-031 behavior; a save into a permission-protected location returns the honest OS error.

**Acceptance Scenarios**:

1. **Given** any previously-refused request class (macro, script, DDE, formatting, unconfirmed send, out-of-scope mailbox ops), **When** processed, **Then** it is refused exactly as before, with the same reasons.
2. **Given** a save into a location the signed-in user cannot write, **When** processed, **Then** the answer reports the operating system's error honestly; the lane never elevates privileges.
3. **Given** file-lane and launch-lane prompts, **When** processed, **Then** their behavior and tests are unchanged.

---

## Edge Cases

- The named location does not exist (a deep path whose parents are missing) → the parents are created as needed, or the failure is reported honestly; the answer names the exact location either way.
- The named location is the same file already open in the application with unsaved changes → ask-back (US2/AC2).
- A save to a removable/network drive that is not present → honest failure naming the location.
- The named path carries sentence punctuation (`D:\docs\.`) → normalized per the `fail-to-save-file` fix — punctuation never changes the location's meaning.
- Two locations in one task ("save to both X and Y") → both are legitimate named targets now; each is reported honestly (this was previously impossible).
- The default-folder behavior for unnamed tasks is unchanged — the work folder remains where unspecified saves land.
- A named read of a file that does not exist → honest error naming the location; nothing fabricated.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: An Office task MAY explicitly name any local save or read location (any drive, any folder); the operation MUST execute at exactly that location, and the answer MUST name the full saved/read path.
- **FR-002** (supersedes spec 030 FR-003): the work-folder containment restriction is REMOVED for locations the user's task explicitly names. The work folder (`C:\OfficeMCP` default, owner-configurable) remains the DEFAULT for tasks that name no location; it is no longer a boundary, and the out-of-folder refusal class is retired.
- **FR-003**: Overwriting an existing file is permitted ONLY when the user's task names that exact file as the target; the answer MUST state that an existing file was replaced. An open-file unsaved-changes conflict MUST ask back before writing. An ambiguous target (no file named) MUST ask back — never a guess-overwrite.
- **FR-004**: The lane MUST NOT elevate privileges. A write into a location the signed-in user cannot access MUST fail honestly with the operating system's error, and the answer MUST relay it.
- **FR-005**: All other gate rules are UNCHANGED: the code-execution ban (macros/VBA/DDE/external-link formulas/scripts), literal-content and v1 formatting refusal, email compose-confirm-send, the launch lane, and the file lane keep their exact current behavior and contract tests.
- **FR-006**: Every save and read attempt MUST record the FULL target location in the append-only audit log; the log never prunes (carried from spec 030 FR-007-equivalent; the audit's location field now carries the actual target, not a root).
- **FR-007**: Path normalization tolerances (trailing punctuation, mixed separators, drive-letter case) apply to all named locations (the `fail-to-save-file` behavior, now location-agnostic).
- **FR-008**: The routing classifier, node instructions, and tool descriptions MUST be updated so location-bearing Office tasks route and relay as before — no new misroute classes, and the retired out-of-folder refusal text is removed from the tool description.

### Key Entities

- **SaveTarget**: a location the user's task explicitly names — any drive/folder; the answer and audit carry the full path.
- **DefaultFolder**: the owner-configurable default (`office_root`) for unnamed tasks — a default, no longer a boundary.
- **OverwriteDecision**: named-existing-file → proceed with honest "replaced" report; unsaved-conflict or ambiguous → ask-back.
- **AuditEntry**: unchanged shape; the location field now records the actual target (named) or the default folder (unnamed).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The previously impossible request — *"create a PowerPoint with 'Hello', file test1, save to c:\temp\test"* — completes end-to-end: the file exists at the named location with the dictated content, the answer names the full path, and the audit records the target.
- **SC-002**: A save to a location outside the work folder (`c:\temp\test` — verified live in the battery's S1 probe) and a read of a user-named file elsewhere both complete honestly; a save into a permission-protected location (`C:\Windows\System32`) returns the operating system's error, never a fabricated success, and a save to a nonexistent drive (`Q:\nowhere`) fails honestly naming the location. (Amended 2026-11-03, analyze finding U1: this machine has a single drive — the original "second drive" phrasing was unreachable; the probes above cover the same acceptance: any named location + the honest OS-error paths.)
- **SC-003**: An overwrite of a user-named existing file reports "replaced" honestly; an unsaved-changes conflict asks back and writes nothing.
- **SC-004**: The existing automated suites and the deploy battery stay green, and the refusal matrix (macros/DDE/formatting/email) is byte-identical — the file lane and launch lane tests pass unchanged.
- **SC-005**: The audit contains one truthful entry per save/read attempt, each carrying the full actual target location.

## Out of Scope (v1)

- Elevated-privilege writes — the lane never elevates; what the signed-in user cannot write, fails honestly.
- Network/remote locations (UNC paths, SharePoint) — deferred; local drives only for now.
- Automatic location *selection* (the assistant choosing where to save when the user did not say) — unnamed tasks use the default folder, never a guess.
- Any change to the file lane's root or the launch lane's rules.
- The code-execution and formatting bans — permanently unchanged, independent of location.

## Assumptions

- The trusted single-owner model (specs 028–030) extends to save locations: the caller is the machine's owner, naming locations on their own machine.
- The operating system's permission rules are the guardrail for protected locations; the assistant runs as the signed-in user without elevation.
- `office_root` remains the owner-configurable default folder; unnamed saves continue to land there.
- Every prior gate behavior not related to location (content rules, email rules, step protocol, audit) carries forward unchanged.
- The deployed Dify/agent tooling needs only wording updates (the retired refusal text); no new nodes or routing classes.
