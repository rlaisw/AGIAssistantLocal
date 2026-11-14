# Feature Specification: Enable Windows-MCP PowerShell Lane

**Feature Branch**: `040-windowsmcp-powershell`

**Created**: 2026-11-14

**Status**: Draft

**Input**: User description: "enable Windows-MCP can run PowerShell"

## Clarifications

### Session 2026-11-14

- Q: Should this feature deliver a repaired channel that the existing agent stack can drive, or also a new owner-facing chat tool with its own gates? → A: Repair the channel only (Option A) — no new owner-facing chat tool or routing surface in this feature; the agent stack drives the consented channel, and a chat-facing tool can be a separate follow-up feature.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a PowerShell command through the Windows-MCP lane (Priority: P1)

The owner asks the assistant (in chat or via the stack) to run a read-only PowerShell command on the Windows host — e.g. "use PowerShell to list the top 5 processes by memory". The request travels through the Windows-MCP lane, the Windows host shows its consent prompt (the Windows-MCP user-control dialog), the owner approves once, and the assistant relays the genuine command output verbatim (e.g. the top-5 process table) — never a fabricated result. Today this exact request fails before reaching the host: the lane's endpoint answers with an HTTP error (observed 2026-11-14: 400 Bad Request on the bridged endpoint), so no PowerShell request can complete at all.

**Why this priority**: This is the whole feature — the lane executing one real, consented PowerShell command with honest output. Everything else exists to make this reliable.

### User Story 2 - Lane is durable and honest about its state (Priority: P2)

After a host reboot or a service restart, the owner asks the same class of request and it works again without manual reconfiguration — the Windows host service behind the lane starts with the user's logon and the lane's reachability is reported honestly. When the lane is down, requests fail fast with a named, actionable error (which service to start, what to check) instead of a raw HTTP status; when it is up, a health check says so truthfully.

**Why this priority**: The stack's other three Windows services already behave this way (auto-start at logon, honest envelopes); a lane that dies silently after every reboot would be unusable in practice.

### User Story 3 - Command results are auditable and bounded (Priority: P3)

Every executed command is recorded in the stack's append-only audit trail (operation, decision, duration, outcome) consistent with the other lanes, and long command output is bounded with the truncation named honestly in the relay, so the owner can always see what ran and what came back.

**Why this priority**: Trust and observability house rules (the audit trail is the shared source of truth across all lanes); it matters once the lane actually works.

### Edge Cases

- The Windows-MCP service is not running (host rebooted, task not started): the lane fails fast with the honest unavailable envelope and the recovery action (start the Scheduled Task) — the recovery command named must actually exist, the same contract the browser lane learned (2026-11-14).
- The owner declines or ignores the consent prompt: the command never runs; the assistant reports that execution was not approved — no retry loops, no executing without consent.
- The command returns large output: the relay truncates and names the truncation (house rule).
- The command fails (PowerShell error): the genuine error text is relayed verbatim; the assistant never masks a failure as success.
- The lane is asked to run a command while another session holds the host service busy: behavior is honest (named busy/refused envelope), never a hang past the turn budget.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The assistant can submit a PowerShell command to the Windows host through the Windows-MCP lane and receive its genuine output (or genuine error) for relay. Read-only diagnostics commands (process/task/service/system listings) are the first-class use case.
- **FR-002**: The lane is reachable from the container-side stack through the existing port bridge, and a health probe reports its state honestly (up = up, down = down with the named recovery), verified from the sidecar's vantage point — not a probe that a bridge can satisfy while the far side is dead (the browser-lane lesson, 2026-11-14).
- **FR-003**: Execution requires the host-side user consent (the Windows-MCP user-control prompt); no command executes without the owner's approval, and a declined/ignored consent is reported honestly.
- **FR-004**: Every attempt (executed, blocked, error) is recorded in the shared append-only audit trail with the command's operation class, decision, and duration.
- **FR-005**: The host-side service survives reboots via its logon auto-start, and the lane's recovery instructions name a recovery action that exists on the host.
- **FR-006**: The current broken state is diagnosed and fixed as part of this feature — the lane's endpoint currently rejects connections with an HTTP error before any command can be attempted.

### Key Entities

- **PowerShell command request**: the literal command text, the requesting conversation, and the consent decision.
- **Audit entry**: operation class, decision (executed/blocked/error), duration, outcome or reason — appended, never rewritten.
- **Consent record**: the host-side approval flow outcome for one command (approved / declined / timed out).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- SC-001: A read-only PowerShell request (e.g. top-5 processes) completes end-to-end — consent prompt shown on the host, output relayed verbatim — in under 30 s from request to answer in the same turn (excluding owner think-time on the consent prompt).
- SC-002: With the host service stopped, a request fails in under 5 s with a named, actionable unavailable envelope; with it started again, the next request succeeds.
- SC-003: After a host reboot and logon, the first PowerShell request succeeds without any manual reconfiguration.
- SC-004: 100% of attempts appear in the audit trail; a declined consent produces a blocked entry and no output is fabricated in the chat.
- SC-005: The full automated test suite remains green (house constitution) with the lane's contract pinned by deterministic tests.

## Assumptions

- **Out of scope (clarified 2026-11-14)**: a new owner-facing sidecar chat tool or chat routing surface for PowerShell — this feature repairs and verifies the channel the agent stack drives; a chat-facing tool can be a separate follow-up feature.
- The Windows-MCP service itself (the host-side product exposing a PowerShell tool with user-control consent) already exists and is installed as a Scheduled Task, as are its three sibling services; this feature wires/diagnoses/verifies the lane rather than building a new host service.
- PowerShell requests through this lane follow the stack's existing lane rules: consent-gated, audited, honest relays; the scope of commands is not restricted by this feature beyond what the host service's own consent flow enforces (the separate two-phase PowerShell gate governs the chat-driven generic PowerShell lane).
- The existing port-bridge pattern (container-side bridge to a Windows-side service port) is the connectivity mechanism; the current 400 Bad Request is a diagnosable wiring/endpoint issue, not a redesign trigger.
- The read-only diagnostics first-class commands mirror the established allowlist spirit (processes, tasks, services, system info) — chosen as the acceptance slice because they are safe and verifiable.
