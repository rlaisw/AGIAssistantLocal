# Feature Specification: Hermes Run-Command Lane — Allowlisted Windows Diagnostics from Chat

**Feature Branch**: `033-hermes-run-command`

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description: "to allow Windows-MCP to run hermes_run_command tool" — arising from the two by-design bug reports of 2026-11-09 (`i-cant-execute-powershell-…`, `the-local-agent-simply-has-no-shell-…`) and the live verification that the local agent's WindowsMCP tool surface includes a shell-execution tool. This spec opens a narrow, allowlisted, read-only diagnostics lane on the existing Hermes architecture (specs 028/029/030): gate in sidecar code before execution, honest verdicts, append-only audit.

## Clarifications

### Session 2026-11-09

- Q: Does the launch lane's shell refusal go away? → A: **No.** Spec 029's FR (shell/PowerShell/command-line phrasing refused in the launch lane) remains in force verbatim; this spec adds a **separate lane** with its own tool and gate. The two bug reports' by-design verdicts stand.
- Q: How is safety enforced — prompt rules or code? → A: **Code.** The allowlist lives in the sidecar's gate, never in a prompt (Constitution IV: the prompt carries none of the security weight). Everything not on the list is refused with the list shown; there is no path from user text to an arbitrary command.
- Q: What may run? → A: A fixed set of **read-only diagnostics**: `ipconfig`, `systeminfo`, `tasklist`, `whoami`, `hostname` (bare), plus `ping`, `nslookup`, `tracert` with exactly one simple host/IP target. Owner may extend the list via a spec amendment only.
- Q: What about PowerShell cmdlets (*"run Get-NetIPAddress"*)? → A: Out of scope for v1 — no cmdlets, no aliases, no flags, no arguments beyond the single target. The refusal names the allowlist so the user can re-ask with a listed command.
- Q: Multiple commands in one prompt (*"ipconfig and tasklist"*)? → A: One command per request, mirroring the launch lane's one-launch-per-request rule — ask-back naming which one.
- Q: Must the per-conversation identity be a required tool parameter? → A: **Yes — required** (owner decision, clarify session 2026-11-09): the tool schema rejects calls without it. The launch lane's optional-parameter omission (observed live 2026-11-09: a turn missing the identity got no timing profile and could not be stopped) is not repeatable on this lane — cancellability and timing are guaranteed by construction (FR-006).

## Supersedes

- None. Spec 029's launch-lane shell refusal stays in force; this spec is additive.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask a diagnostics question and get the machine's real answer (Priority: P1)

As a chat user, I ask *"show my Windows current IP address"* (or *"what's my hostname"*, *"list the running tasks"*, *"system info"*) and the assistant runs the matching allowlisted diagnostic on my Windows computer and relays its **real output** — the same text I would get typing the command myself.

**Why this priority**: This is the exact user need that surfaced twice today; it is the entire feature value — chat-driven system-state lookups ending in honest, verifiable answers instead of a by-design refusal.

**Independent Test**: Ask *"show my current ip address"* → the answer contains the machine's actual IP address (matches the real `ipconfig` output on the desktop); the audit log records an executed run-command attempt.

**Acceptance Scenarios**:

1. **Given** I ask for a system-state fact that maps to an allowlisted diagnostic (*"show my ip"*, *"what processes are running"*), **When** the assistant answers, **Then** the matching command ran on my Windows computer this turn and the answer reports its actual output — never a remembered or invented value.
2. **Given** the diagnostic output is longer than the chat answer can carry, **When** relayed, **Then** the answer carries a bounded excerpt with the truncation named honestly — never a silent cut that hides the relevant part (the answer targets the part that answers the question when one is detectable, e.g. the IPv4 lines for an IP question).
3. **Given** the local agent pathway or the shell tool is down, **When** I ask, **Then** the answer reports the failure honestly with a recovery hint; the chat stays usable for all other lanes.

---

### User Story 2 - Everything outside the allowlist is refused, never executed (Priority: P1)

As the machine's owner, any request that names a command not on the allowlist — arbitrary executables, PowerShell cmdlets, anything with flags, pipes, redirection, scripts, background jobs, remote execution, or any state-changing verb (*"delete"*, *"format"*, *"shutdown"*, *"reg add"*, *"netsh"*) — is refused with a clear reason naming the read-only allowlist and showing the list. Nothing beyond an allowlisted command may ever run.

**Why this priority**: The lane executes commands on the user's real computer via an uncontained shell tool; the allowlist enforced in gate code is the entire security model. A run-command lane that executes whatever a prompt attaches is a vulnerability, not a feature.

**Independent Test**: Send the refusal matrix (arbitrary command names, cmdlets, flag/pipe/redirection/semicolon tricks, quoted smuggles, destructive verbs, multi-command prompts) — every one refused with a reason; the audit log shows blocked entries and no executed command outside the list.

**Acceptance Scenarios**:

1. **Given** a prompt naming a command not on the allowlist (*"run Get-NetIPAddress"*, *"execute del C:\temp\*.txt"*), **When** processed, **Then** the answer refuses with the allowlist shown; nothing runs.
2. **Given** a prompt smuggling syntax around a listed command (*"ipconfig | clip"*, *"ping 8.8.8.8 && shutdown"*, *"tasklist /v"*), **When** processed, **Then** the answer refuses naming the no-flags/no-piping rule; the clean form alone may run.
3. **Given** a prompt mixing an allowed command with a refused one (*"ipconfig and run format D:"*), **When** processed, **Then** the refused part never executes and its refusal is reported; at most the clean allowed part runs.
4. **Given** a prompt naming two allowlisted commands (*"ipconfig and tasklist"*), **When** processed, **Then** the assistant asks which one — one command per request; neither runs until the user picks.

---

### User Story 3 - Targeted diagnostics with one host argument (Priority: P2)

As a chat user, I can ask connectivity questions — *"ping 8.8.8.8"*, *"nslookup google.com"*, *"check the route to example.com"* — and the matching allowlisted command runs with exactly that one target and its real output is relayed.

**Why this priority**: Bare lookups (Story 1) deliver the everyday value; targeted network checks complete the diagnostics reach. Separately testable; does not block the MVP.

**Independent Test**: Ask *"ping 8.8.8.8"* → real round-trip statistics from the machine; ask *"ping 8.8.8.8 -l 65500"* → refused (no flags) with the rule named.

**Acceptance Scenarios**:

1. **Given** a listed network diagnostic with exactly one simple target token (letters, digits, dots, hyphens — a hostname or IP), **When** processed, **Then** the command runs with that target and the answer reports its real output.
2. **Given** the target contains anything beyond the simple-token charset (spaces, quotes, metacharacters, a second token, flags), **When** processed, **Then** the answer refuses naming the single-simple-target rule; nothing runs.

---

### User Story 4 - The lane joins the honesty machinery (Priority: P2)

As the machine's owner, every run-command attempt is audited (`operation=run-command`, blocked or executed), the turn is cancellable from the chat Stop button, its timing profile is recorded like the other lanes, and the relay-level anti-fabrication contract covers the new tool — an answer claiming a run-command result without a tool call this turn is blocked.

**Why this priority**: These are the guarantees that make every "done" from this system verifiable; the new lane must not be a second-class citizen of the honesty architecture.

**Independent Test**: Run one allowed and one refused request → the audit log holds both with timing; press Stop mid-run → the turn cancels honestly; the DSL instruction names the new tool in its anti-fabrication law and honesty-check coverage.

**Acceptance Scenarios**:

1. **Given** any run-command request (executed or blocked), **When** the turn ends, **Then** the append-only audit log holds exactly one entry per attempt with the verdict and timing.
2. **Given** the Stop button is pressed during a running diagnostic, **When** the turn cancels, **Then** the visible answer says so honestly; read-only work means no partial-state risk.
3. **Given** the relay drafts an answer claiming a command ran without calling the tool this turn, **When** the answer is delivered, **Then** the structural honesty check replaces it — the fabrication guard extends to the run-command lane.

---

## Edge Cases

- Phrasing that maps to no listed command (*"check my network health"*) → ask-back offering the listed diagnostics; the gate never guesses an arbitrary command.
- Command output containing the answer buried in volume (`tasklist`, `systeminfo`) → bounded relay with truncation named; when the question implies a slice (IP lines, a process name), the answer targets it without inventing content.
- A listed command that fails on the machine (dead resolver for `nslookup`) → the command's real error output is relayed honestly; never a fabricated success.
- The target host token is an IP with odd formatting or a hostname with underscores → strict charset parsing decides; refused forms name the rule.
- A blocked request is re-asked with rephrased smuggling (*"please run ipconfig with the redirect thing"*) → the refusal stands; no re-attempt with rephrased paths (spec 029 rule verbatim).
- The Stop button mid-command → turn cancelled honestly; the command is read-only, so no partial state exists to clean up.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST enforce a fixed, read-only diagnostics allowlist in gate code at the trust boundary **before** any execution: `ipconfig`, `systeminfo`, `tasklist`, `whoami`, `hostname` (bare), `ping`, `nslookup`, `tracert` (one simple target). The allowlist MUST never live in a prompt.
- **FR-002**: The system MUST refuse every request outside the allowlist with a reason that names the rule and shows the list — arbitrary command names, cmdlets, flags, pipes, redirection, separators, quoting tricks, background/remote forms, and any state-changing verb — with zero execution.
- **FR-003**: `ping`/`nslookup`/`tracert` MUST accept exactly one target token matching a strict hostname/IP charset (letters, digits, dots, hyphens); anything else is refused naming the single-simple-target rule.
- **FR-004**: Every attempt MUST be audited exactly once (`operation=run-command`) — blocked with the reason, executed with the real bounded output — in the append-only audit log, with the turn's timing profile like the existing lanes.
- **FR-005**: The answer MUST relay the command's actual output verbatim (bounded, truncation named) — never fabricated, summarized as fact, or claimed without a tool call in the turn; blocked → reason verbatim; error → honest failure with a recovery hint.
- **FR-006**: The turn MUST be cancellable by construction: the per-conversation identity is a **required** tool parameter — the tool schema rejects calls without it — and Stop must halt the turn with an honest cancelled verdict. Every run-command turn is timing-instrumented and cancellable, never dependent on the relay remembering to pass the identity.
- **FR-007**: The relay's anti-fabrication law and the structural honesty check MUST cover `hermes_run_command` — an answer claiming a command ran without this turn's tool call is replaced.
- **FR-008**: The launch lane's shell refusal MUST remain unchanged (Constitution I); its refusal message SHOULD point users to the run-command lane for allowlisted diagnostics.
- **FR-009**: The router MUST send system-state/diagnostics requests to the new lane (including requests phrased with "powershell" that map to a listed command), without disturbing existing routing.

### Key Entities

- **CommandVerdict**: the gate's decision for one request — `executed` (command, real output) | `blocked` (reason verbatim) | `error` (failure + recovery hint); the only honest shapes.
- **Allowlist Entry**: a command name plus its argument policy (`bare` or `single-target`); the complete route from user text to execution.
- **Audit Entry**: one per attempt — decision, operation `run-command`, the command, verdict text, timing profile; append-only.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: *"show my current IP address"* returns the machine's real IP (verified against the actual command output on the desktop) within the existing agent-turn envelope; the sidecar's gate-plus-relay adds under 2 s.
- **SC-002**: The refusal matrix (arbitrary commands, cmdlets, flags, pipes, redirection, smuggles, destructive verbs, multi-command prompts) is 100% refused with reasons and zero execution — verified by gate tests plus audit inspection.
- **SC-003**: 100% of run-command attempts (blocked and executed) appear in the audit log with timing — no unaudited execution path exists.
- **SC-004**: An allowed diagnostic's verdict arrives within the configured agent-call timeout, measured on this host, not assumed (amendment pattern from spec 029's SC-001).

## Assumptions

- Execution rides the existing local Hermes agent pathway (gate → agent → its WindowsMCP shell tool → honest envelope); no new Windows-side component is introduced.
- "Read-only" means the bare listed forms; no flags or switches in v1 (e.g. `ipconfig /all` is deferred until an amendment adds specific safe flags).
- One command per request; mixed prompts follow the launch lane's precedent (each lane handles its own part, refusals reported).
- The relay model's router and tool descriptions are updated via the existing publish cycle; honesty-check coverage extends by adding the tool name.
- No cmdlet aliases, no PowerShell syntax mapping in v1 — listed commands only.
- Out of scope: any state-changing execution, remote commands, background jobs, output redirection, scheduled tasks.
