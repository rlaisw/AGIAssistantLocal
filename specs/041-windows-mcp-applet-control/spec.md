# Feature Specification: Windows-MCP Applet Control (gated, four tiers)

**Feature Branch**: `041-windows-mcp-applet-control`

**Created**: 2026-11-15

**Status**: Draft

**Input**: User description: "enable items 1-4 and follows your recommendation" — the four applet-control capabilities with the gate design analyzed and agreed 2026-11-15: (1) launching classic Control Panel applets (.cpl), (2) opening modern Settings pages (ms-settings:), (3) headless applet control via PowerShell cmdlets — split into a read-only tier and a fully confirmed write tier, and (4) end-to-end GUI applet automation — each tier gated per its risk class.

## Clarifications

### Session 2026-11-15

- Q: Should creating or changing individual firewall rules be allowed after your plain confirmation, or refused always like disabling the firewall profile? → A: Confirmed-only (Option A) — individual firewall rule additions/changes are tier-3 confirmed operations; the never-list keeps the firewall-profile disable and the remote-access-cutting class.
- Q: Should GUI automation cover every applet from day one, or start with a safe subset and expand later? → A: Safe starter subset first (Option B) — uninstall, power options, display, sound, date/time; expansion to the full applet list is a deliberate follow-up after the tier proves itself, with the never-list binding everywhere in the meantime.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Open any settings surface by name (Priority: P1)

The owner asks in chat "open Network Connections" or "open display settings". The requested window — a classic Control Panel applet or a modern Settings page — opens on the owner's desktop within seconds. Opening a window changes nothing by itself; the applet simply appears for the owner to use. Unknown or ambiguous targets ask back honestly instead of guessing; one target per request.

**Why this priority**: The simplest complete value — everything else builds on reaching the settings surface, and it is nondestructive by nature (a window opens, nothing changes until a human acts inside it).

### User Story 2 - Inspect settings headlessly, read-only (Priority: P2)

The owner asks "what's my current power plan?" or "which network adapters do I have?". The assistant answers with genuine, current values read from the system through a strictly allowlisted set of read-only commands — no confirmation needed because nothing can change: the allowlist contains only queries, every unmapped or write-shaped request is refused with the list shown, and each call is audited.

**Why this priority**: The most common real need is looking, not changing; the read tier is safe to use freely and builds trust for the write tier.

### User Story 3 - Change settings via a confirmed command (Priority: P3)

The owner asks "set my power plan to high performance". The assistant drafts the exact command, shows it verbatim in chat, and nothing runs until the owner replies with a plain confirmation. The confirmed text is what executes — a later "yes" carries no command text at all. System-integrity commands and the remote-access-cutting class are refused always, even after confirmation. A modified instruction re-drafts; silence never executes.

**Why this priority**: This is the first tier that changes the machine, so it carries the full two-phase gate and the extended never-list before it can be enabled.

### User Story 4 - Complete a GUI flow inside an applet (Priority: P4)

The owner asks "uninstall Zoom from Programs and Features". The assistant opens the applet (Story 1), inspects its window, and proposes the click/type sequence in plain words — "I will click Uninstall on Zoom, then confirm the removal dialog" — and waits for the owner's yes. Only then does it drive the GUI. On day one the tier serves the safe starter applets (uninstall, power options, display, sound, date/time), expanding deliberately once proven. Password and credential fields are never typed into; an elevation prompt stops the sequence with an honest report; any dialog beyond the described sequence stops and re-confirms. Every click is audited.

**Why this priority**: The most capable and the most dangerous tier — the click IS the write — so it is enabled last, only on top of the proven lower tiers, with its own UI gate.

### Edge Cases

- Applet already open: the request focuses the existing window (or honestly reports a second instance) — never silently does nothing.
- Unknown applet or settings page: ask-back with the known list; never a guessed launch.
- Read request that maps to no allowlisted command: refused with the allowlist shown (the read-tier contract), never a "best effort" write.
- A write command confirmed with a modification ("yes but add -Force"): re-draft with the new text and ask again — the confirmed text is always what runs.
- Never-list attempt at any tier, confirmed or not: refused always, reason verbatim — including clicking a never-list button inside a dialog (the dialog is just another keyboard).
- Remote-access-cutting commands (adapter disable, IP/gateway changes, firewall-profile disable): refused always — losing the remote session may need physical access to recover.
- An elevation (UAC) prompt appearing mid-GUI-flow: the sequence stops, the prompt is reported honestly for the owner to approve by hand, and no success is ever claimed for the uncompleted part.
- A dialog cascade beyond the confirmed sequence: stop, describe the new dialog, request a fresh confirmation.
- The Windows-MCP service down or the desktop session disconnected: the honest unavailable envelope with the real recovery; the desktop-activity deferral (USER_CONTROL) reports as a named deferral — ask again shortly.
- Sensitive fields: password/credential inputs are never typed, never logged, masked in any snapshot relay.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Restore the full Windows-MCP tool surface — the installed service exposes only four tools live (process, clipboard, notification, registry) while the package ships the launch/shell/inspect/input modules this feature needs; the live registration gap is diagnosed and fixed first, and the restored surface is verified before any tier is enabled.
- **FR-002 (Tier 1 — open)**: Named Control Panel applets and Settings pages open on the owner's desktop from chat; targets are bounded to a known list; one target per request; unknown or ambiguous targets ask back; nothing beyond the identifier is passed.
- **FR-003 (Tier 2 — read)**: A strictly allowlisted set of read-only settings queries answers with genuine current values, no confirmation; anything not on the allowlist, or any write-shaped request, is refused with the list shown; every call audited.
- **FR-004 (Tier 3 — write)**: State-changing settings commands run only through the two-phase flow — draft shown verbatim, plain confirmation, stored-text execution, one command per request; a confirmation never carries command text.
- **FR-005 (Never-list, binding at every tier)**: The shared never-list always binds — the existing system-integrity class (boot config, disks, BitLocker, recovery, volume operations) plus the remote-access-cutting class (adapter enable/disable, IP/gateway changes, firewall-profile disable, remote-access and account changes); individual firewall-rule additions/changes are confirmed tier-3 operations, not never-listed (clarified 2026-11-15). Refusal reasons are relayed verbatim, and a never-list action attempted through the GUI is refused exactly like a typed command.
- **FR-006 (Tier 4 — GUI)**: GUI automation (inspect + click/type) runs only per confirmed plain-word sequence naming each control and its effect; credential fields never typed; elevation prompts stop the flow honestly; unexpected dialogs stop and re-confirm; every click audited. Scope on day one is the safe starter set — the uninstall, power options, display, sound, and date/time applets — with expansion to the full applet list as a deliberate follow-up once the tier proves itself (clarified 2026-11-15); the never-list binds everywhere throughout.
- **FR-007**: All four tiers route through the chat's Hermes Local Agent lane with the existing honesty contracts: no claim of action without the call in the same turn, refusals and errors relayed verbatim, recovery hints name actions that exist.
- **FR-008**: Every attempt in every tier lands in the shared append-only audit trail (operation class, decision, conversation, duration); refusals are audited as refusals, never hidden.

### Key Entities

- **Settings target**: a bounded identifier — a Control Panel applet name or a Settings page name from the known list (Story 1).
- **Read-only allowlist entry**: a named query with a fixed command shape; the only path that answers without confirmation (Story 2).
- **Draft/confirm record**: the verbatim command text, the confirmation state, and the stored-text rule — what was confirmed is structurally what runs (Story 3).
- **GUI sequence confirmation**: the plain-word description of each control and its effect, per sequence; credential fields excluded (Story 4).
- **Audit row**: operation class, decision (executed/blocked/error), conversation, duration — append-only across all tiers (all stories).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- SC-001: "open device manager" (or any listed applet/page) opens the window on the owner's desktop in under 15 s, one target, audited as executed.
- SC-002: A read-tier question ("what's my power plan?") returns genuine values in under 30 s with no confirmation, and the system state is provably unchanged (config identical before and after).
- SC-003: A write-tier command never executes without the verbatim draft and the plain confirmation in the same conversation; the confirmed text is exactly what runs; never-list attempts are refused 100% of the time, confirmed or not.
- SC-004: A GUI flow completes only after its plain-word confirmation; credential fields are never typed (zero occurrences in any audit row); an elevation prompt produces an honest stop, never a success claim.
- SC-005: The full automated test suite stays green across the enablement, with each tier pinned by deterministic tests plus a live end-to-end battery.
- SC-006: User-visible latency per tier: opens under 15 s; reads under 30 s; writes under 60 s after confirmation; a whole GUI flow within the chat turn budget.

## Assumptions

- The gate design is the one analyzed and accepted on 2026-11-15: tiers 1-2 are nondestructive (light gating); tier 3's read half uses the read-only allowlist pattern (spec 033) and its write half the full two-phase machinery (spec 034) with the extended never-list; tier 4 adds the UI gate (per-sequence plain-word confirmations, credential ban, elevation honesty).
- The two-phase and never-list machinery already exists in the codebase and is reused, not reinvented; the never-list gains the remote-access-cutting class as this feature's only security-list change.
- The Hermes Local Agent lane is the routing surface; the chat's existing honesty, consent, and audit contracts govern every tier unchanged.
- The four tiers are enabled staged in story order (open → read → confirmed write → GUI), each verifiable before the next.
- The Windows-MCP service's interactive-desktop dependency (it cannot run without an active desktop session) and its desktop-activity deferral behavior are inherited as-is; the honest envelopes for both already exist in the lane.
- The .cpl and ms-settings: target lists are bounded to the standard Windows set (the applet inventory reviewed 2026-11-15); additions to the list are a deliberate future edit.
