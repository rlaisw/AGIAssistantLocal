# Feature Specification: Hermes Program Launch Lane — Windows Apps from Chat

**Feature Branch**: `029-hermes-launch-programs`

**Created**: 2026-11-01

**Status**: Draft

**Input**: User description: "add Hermes MCP tool can launch any program capability" — extended by the design discussion: a second Hermes lane that lets a chat prompt start an application (e.g. *"launch Outlook"*, *"open Excel"*, *"run C:\tools\mytool.exe"*) on the user's Windows computer, riding the same security architecture as the file lane (spec 028): gate before execution, honest verdicts, append-only audit.

## Clarifications

### Session 2026-11-01

- Q: Should the launch lane accept only applications from a pre-approved allowlist, or any executable the prompt names? → A: **No allowlist** (owner decision, clarify session 2026-11-01): any executable identified by application name **or full executable path** ("B2"). Launch arguments and shell/PowerShell phrasing stay refused. The identity-allowlist rationale originally drafted for this spec was rejected by the owner; the security model rests on the single trusted caller (see Assumptions).
- Q: May a prompt pass arguments, documents, or shell commands to the launch? → A: No. v1 launches by application name or full executable path only; argument strings, command lines, and shell/PowerShell phrasing in prompts are refused with a reason. *"Open report.xlsx in Excel"* is deliberately deferred (Out of Scope).
- Q: What happens to spec 028's program-execution decline? → A: Superseded for app launches by name or path: *"open notepad"* now launches Notepad instead of being declined. Spec 028's shell-command decline (*"run a PowerShell command…"*) remains in force, and the file lane itself stays file-only and byte-identical (Constitution I).
- Q: Where does the launch execute? → A: Through the same local Hermes agent pathway as file tasks, after the same pre-execution gating; the verdict (launched / blocked / error) is relayed to the chat honestly, with every attempt audited like file tasks.
- Q: What if the app is already running when asked to launch it? → A: Whatever the launcher actually observed is reported honestly (activated / second instance); the assistant never claims a fresh start it cannot verify.
- Q: Should scripts and Windows shortcuts count as launchable full-path targets? → A: No — real program executables only (.exe and equivalents); scripts (.bat/.cmd/.ps1) and shortcut (.lnk) paths are refused with the executables-only rule named.
- Q: Should a launch execute immediately or ask for confirmation in chat first? → A: Immediately — no confirmation round-trip; the verdict is relayed in the answer, consistent with the file lane.
- Q (implementation amendment): How is the honest `ok` verdict enforced when the executor is an agent whose prose the tool cannot parse? → A: The launch system prompt requires a final attestation line — exactly `LAUNCH: SUCCESS` or `LAUNCH: FAILED: <reason>` — and the tool stamps `ok` ONLY on an explicit SUCCESS marker; a failure report or a missing marker is `status: error`, audited truthfully. (Found live: the first probe stamped `ok`/`executed` for a launch the agent could not perform — WSL interop was disabled — a FR-007 violation fixed by this marker protocol.)
- Q (measurement amendment — performance targets are measured, not assumed): Is the 60-second launch budget realistic? → A: No — the verdict is dominated by the local agent's reasoning turn (measured 71 s cold, 230 s warm on this host). SC-001 is amended to the agent-turn bound: the verdict arrives within the configured Hermes call timeout (300 s default); the sidecar's gate-plus-relay adds under 2 s.
- Q (host prerequisite, discovered live): The user's WSL had interop disabled (`/etc/wsl.conf [interop] enabled=false`) and the WSL–Windows vsock channel down — no WSL-side executor can start Windows programs. → A: Interop is a hard prerequisite of this feature on this host; enabling it (flip the conf, then `wsl --shutdown` from Windows) was approved by the owner on 2026-11-01. Until then the lane answers honestly with the agent's diagnosis + recovery hint, and launch attempts audit as `error`.

## Supersedes

- Spec 028, User Story 3 ("Windows program execution is explicitly out of scope") — narrowed: **app launches by name or executable path (never with launch arguments)** are now in scope on the new lane; shell/PowerShell/GUI automation and launch arguments remain out of scope everywhere. Spec 028's FR-009 continues to hold for the file lane verbatim.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Launch a desktop app from chat (Priority: P1)

As a chat user, I type *"launch Outlook"* or *"open Excel"* and the application actually starts on my Windows computer. The answer confirms what launched, and I can see the window on my desktop with my own eyes.

**Why this priority**: This is the entire feature value — chat-driven app launch with a result visible on the real Windows desktop, ending the file-only decline users get today.

**Independent Test**: Type *"open Notepad"* → Notepad opens on the Windows desktop; the answer reports the launch and the audit log records an executed launch attempt.

**Acceptance Scenarios**:

1. **Given** I prompt to launch an application by name (*"launch Outlook"*, *"open excel"*), **When** the assistant answers, **Then** the application starts on my Windows computer in the same turn — no confirmation round-trip — and the answer confirms the launch.
2. **Given** a launch prompt phrased as a question (*"can you open Notepad?"*), **When** processed, **Then** the launch behaves the same as the imperative form.
3. **Given** the named application is not installed or fails to start, **When** the launch is attempted, **Then** the answer reports the failure honestly with a recovery hint — never a fabricated success.

---

### User Story 2 - Launch arguments and shell commands are refused, never executed (Priority: P1)

As a chat user, any launch request that smuggles launch arguments, command lines, or shell/PowerShell phrasing — *"launch outlook --dangerous-flag"*, *"open notepad and also run a PowerShell command"*, *"start notepad /elevate"* — or names a script or shortcut file as the target (*"run C:\temp\setup.bat"*) — must be refused with a clear reason naming the no-arguments and executables-only rules. Nothing beyond the clean launch may ever run.

**Why this priority**: The lane starts real programs on the user's real computer. With no identity containment (owner decision), the no-arguments rule plus honest relay and audit are the remaining guardrails; a launch lane that executes whatever a prompt attaches is a vulnerability, not a feature.

**Independent Test**: Send the refusal matrix (argument strings, command lines, shell/PowerShell phrasing, script/shortcut path targets, smuggled second instructions) — every one refused with a reason; the audit log shows blocked entries and no executed launch carrying any refused element.

**Acceptance Scenarios**:

1. **Given** a prompt containing launch arguments, command-line flags, or shell/PowerShell phrasing, **When** processed, **Then** the answer refuses naming the no-arguments rule; no process starts.
2. **Given** a prompt that smuggles a second instruction (*"open notepad and also run powershell"*), **When** processed, **Then** at most the clean launch runs; the smuggled instruction must not execute and its refusal is reported.
3. **Given** a full path naming a script (.bat/.cmd/.ps1) or shortcut (.lnk) file, **When** processed, **Then** the answer refuses naming the executables-only rule; nothing starts.
4. **Given** the local agent pathway is down, **When** a launch is attempted, **Then** the answer reports the failure honestly with a recovery hint; the chat stays usable for all other lanes.

---

### User Story 3 - Launch any tool on the machine by full path (Priority: P2)

As the machine's owner, I can launch non-Start-menu tools by naming their full executable path — *"run C:\tools\mytool.exe"* — and the exact program starts. A path that does not exist or is not an executable fails honestly with the path named.

**Why this priority**: Name-launch (Story 1) delivers the everyday value; full-path launch completes the "any executable" reach the owner chose. It is a distinct, separately testable slice and does not block the MVP.

**Independent Test**: Prompt a full path to an installed tool outside the Start menu → it launches; prompt a nonexistent path (*"launch C:\nope\missing.exe"*) → honest error naming the path, nothing starts.

**Acceptance Scenarios**:

1. **Given** I prompt a full executable path (Windows or host style) to an installed tool, **When** processed, **Then** that exact program launches and the answer confirms it.
2. **Given** the path does not exist or is not an executable, **When** processed, **Then** the answer fails honestly naming the path; nothing starts.

---

## Edge Cases

- App name casing/variants (*"OUTLOOK"*, *"ms excel"*, *"excel app"*) → name matching is case-insensitive and tolerant of common phrasings.
- The app is already running → the launcher's actual observation is relayed honestly (activated / focused / second instance); no unverifiable "started fresh" claim.
- A launch prompt names no app at all (*"open it"*, *"open the file I made"*) → ask-back asking which application to launch; nothing is assumed or started.
- A prompt naming two applications (*"open notepad and calculator"*) → one launch target per request: the assistant asks which one to launch; it never launches both from a single prompt.
- The prompt mixes a launch with a file task (*"open Notepad and create notes.txt in C:\temp"*) → each part is handled by its own lane rule; both verdicts are reported honestly.
- The chat Stop button is pressed mid-launch → the visible answer stops as usual; the launch may already have happened; the audit log holds the truth, and a follow-up question about the state answers from observation, not assumption.
- A named app that cannot be resolved on this machine → honest error naming the app, never a fabricated success.
- A single ambiguous name (*"notes"* could be Notepad or Sticky Notes) → passes to the launcher, which resolves it on the machine or reports an honest failure; the gate ask-backs only when the prompt names two applications — it cannot enumerate what one name might mean without a list (removed with the allowlist in the clarify session).
- A full path written with mixed separators/casing (*"c:\TOOLS\mytool.exe"*) → normalized to one canonical form before the existence check.
- Arguments smuggled via punctuation (*"notepad -n"*, *"notepad; calc"*, *"notepad --x=y"*) → refused under the no-arguments / no-smuggling rules; no partial launch.
- A full path naming a script (.bat/.cmd/.ps1) or shortcut (.lnk) → refused under the executables-only rule even though the file exists; the answer names the rule.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Prompts recognized as launch requests (open/launch/start/run an application or executable) MUST route to the launch lane; file-task prompts MUST keep routing to the file lane; every other lane (Q&A, decks, stop) MUST keep today's behavior with zero regression.
- **FR-002**: The launch capability MUST be exposed as one new MCP tool on the sidecar's existing tool surface; all existing MCP tool schemas MUST stay byte-identical (Constitution I).
- **FR-003**: A launch MUST be permitted for any executable the prompt identifies by application name or by full executable path. Name-identified applications MUST be resolved through the machine's standard application resolution; a name that cannot be resolved MUST produce an honest error naming the application — never a guessed launch.
- **FR-004**: Executable paths from prompts MUST be accepted in Windows and host style and normalized to one canonical form before resolution; a path that does not exist or is not executable on the machine MUST fail honestly with the path named. Only real program executables are launchable: a path naming a script (.bat/.cmd/.ps1) or shortcut (.lnk) file MUST be refused with the executables-only rule named.
- **FR-005**: Launch arguments, command lines, and shell/PowerShell phrasing MUST NOT be executed or forwarded to the launched executable; such requests MUST be refused with the no-arguments rule named (v1 scope).
- **FR-006**: Every launch attempt — executed, refused, or failed — MUST be recorded in the existing append-only host-side audit log with timestamp, decision, the application or path named, and reason/outcome; the log is never rewritten or pruned by the lane.
- **FR-007**: The launch verdict MUST use the same honest envelope as the file lane: `ok` only when the launch actually succeeded, `blocked` with a user-readable reason that never claims execution, `error` with a recovery hint naming the likely cause — never a fabricated result (Constitution IV).
- **FR-008**: If the local agent pathway is unavailable or the launch fails to start the target, the answer MUST report the failure honestly with a recovery hint; the chat MUST remain usable for all other lanes.
- **FR-009**: The file lane MUST remain file-only and unchanged: launch prompts that reach it are still blocked there (defense in depth), and its existing contract tests pass unchanged.
- **FR-010**: Spec 028's program-execution decline is superseded exactly and only for app launches by name or path without arguments: launch prompts resolve via the new lane instead of a decline; the shell/PowerShell decline and 028's FR-009 for the file lane remain in force. Chat-level, "open notepad" MUST launch via `hermes_launch_app` and "run a PowerShell command" MUST still be declined, while the direct file-tool probes stay blocked (defense in depth, contracts §6).
- **FR-011**: A launch prompt naming no application MUST trigger an ask-back asking which application to launch; nothing is assumed or started (mirror of the file lane's FR-014).
- **FR-012**: When a chat turn is stopped mid-launch, the visible answer stops as usual; an in-flight launch MAY complete. The audit log MUST record the actual outcome, and the lane MUST NOT later claim a launch did not happen when the audit shows it did.
- **FR-013**: A gated launch MUST execute immediately without a chat confirmation round-trip; the answer MUST relay the verdict (launched/blocked/error). Ask-backs under FR-011 are the only pre-execution interaction.

### Key Entities

- **LaunchRequest**: the user's launch intent after normalization — one application name or one executable path, and nothing else (arguments or command lines force a refusal).
- **SafetyVerdict**: the gate's decision — allowed (with the resolved application or path) or blocked (with a user-readable reason naming the no-arguments rule, the unresolvable target, or the ask-back).
- **AuditEntry**: one append-only record per attempt: timestamp, decision (executed/blocked/error), application or path named, reason or outcome.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: *"open notepad"* answers and shows the app running on the Windows desktop within the Hermes call timeout (default 300 s — amended 2026-11-01, see Clarifications); the gate's verdict itself is computed in under 2 s.
- **SC-002**: 100% of the refusal matrix — launch arguments, command lines, shell/PowerShell phrasing, script/shortcut path targets, smuggled instructions — is refused with a reason; zero processes started carrying any refused element (audit shows blocked entries only).
- **SC-003**: A full-path launch of a non-Start-menu tool succeeds end-to-end; a nonexistent or non-executable path fails honestly naming the path.
- **SC-004**: The existing automated test suite and deploy verification battery stay green; the 028 decline expectation flips at the launch lane and classifier routing ("open notepad" → launch via `hermes_launch_app`; PowerShell → still declined) while the direct file-tool probes stay blocked per contracts §6 (defense in depth); the rest of the battery is unchanged.
- **SC-005**: For every test prompt — executed or blocked — the audit log contains exactly one entry with timestamp, decision, target named, and reason/outcome, and never claims execution that did not happen.

## Out of Scope (v1)

- Passing documents or any arguments to a launched app (*"open report.xlsx in Excel"*) — deliberately deferred, named for a follow-up version.
- Closing/quitting running apps, GUI automation (clicking/typing into windows), installing software, running scripts (also as launch targets), Windows shortcut (.lnk) targets, scheduled/autostart launches.
- Multi-user authorization (single trusted owner, as in spec 028).
- Any identity containment of launch targets (allowlist) — explicitly rejected by the owner in the clarify session; revisiting it would be a spec amendment.

## Assumptions

- **Any executable identified by name or full path may be launched** (owner decision, clarify session 2026-11-01). There is no identity containment by design; the security model is the single trusted caller — the machine's owner — plus the no-arguments rule, the honest envelope, and the append-only audit.
- The Hermes agent pathway (gateway, key, host mount) remains installed and operational as wired by spec 028; this feature adds a lane on top and does not reinstall or reconfigure it.
- Single-user trusted deployment as in spec 028 is the **primary** security control for this lane: the chat platform, the assistant, and the Windows computer belong to the same person.
- Applications launched by name are resolvable through the machine's standard application resolution (Start-menu style); prompts may alternatively supply the full executable path.
- The launch executes through the same local-agent pathway as file tasks, after the same pre-execution gating; the chatflow node relays the verdict verbatim and never claims direct desktop access.
- The existing chat UI is unchanged; the lane is reachable by typing a launch prompt.
