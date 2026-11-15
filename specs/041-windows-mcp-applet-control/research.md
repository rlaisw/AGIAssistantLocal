# Research: Windows-MCP Applet Control (041)

Created: 2026-11-15. All findings verified LIVE during planning (read-only probes + the service's own source).

## R1: FR-001 — the "missing tool surface" is already restored (no code change)

**Decision**: FR-001 is satisfied by verification alone; the plan's prerequisite task collapses to a pinned check.

**Rationale / live evidence**:
- The installed package registers **all modules cleanly** (isolated probe, same interpreter): `ControlStatus, App, DisplayInventory, PowerShell, FileSystem, Screenshot, Snapshot, Click, Move, Scroll, Shortcut, Type, Wait, WaitFor, Scrape, MultiEdit, MultiSelect, Clipboard, Process, Notification, Registry` — 21 tools.
- No filter applies on the live path: no `--tools`/`--exclude-tools` flag in the running command line (verified via `Get-CimInstance Win32_Process`), no `WINDOWS_MCP_TOOLS` env var (User/Machine both empty), no `~/.windows-mcp/config.toml`, no log errors; package mtime (2026-11-06) predates the restarts — no version skew.
- The live server **re-listed on 2026-11-15: all 21 tools present**.
- Root cause of the earlier "4 tools" observations: a stale, filtered server instance (started 2026-11-14 with a minimal tool set) that predates the task-started restarts; every post-restart probe called tools without re-listing. The 2026-11-14 restart (via the Scheduled Task's unfiltered `start-server.cmd`) restored the full surface.

**Alternatives considered**: patching `register_all`, changing the task action — both moot.

## R2: Execution-channel decision (the clarify-deferred question) — tiers vs tools

**Decision**:
- **Tier 1 (open)**: the service's `App`/`PowerShell` tools via the lane's bounded launcher (`control <applet>.cpl` / `start ms-settings:<page>`), targets restricted to the reviewed list — our gate, not the service's.
- **Tier 2 (read)**: the service's `PowerShell` tool behind OUR new read-allowlist gate (mirror of `hermes_run_gate.py`: fixed query set — adapter list, power plan, firewall rules listing, volume info; anything else refused with the list). No confirmation.
- **Tier 3 (write)**: the **existing `hermes_run_powershell` machinery** executes the drafts — verbatim display, plain confirm, stored-text execution, one command per request. We add only the extended never-list (remote-access-cutting class; firewall-rule changes confirmed-only per the clarification). Rationale: the machinery is proven, audited, and already wired into the chat; reusing it is the shortest correct diff.
- **Tier 4 (GUI)**: the service's `Snapshot`/`Screenshot`/`Click`/`Type`/`Wait` tools orchestrated by the lane behind the UI gate (per-sequence plain-word confirm, stored like a tier-3 draft; credential fields refused; UAC → honest stop; cascade → re-confirm).

**Rationale**: no raw passthrough of the service's `PowerShell` tool is ever registered to the chat (it is `destructiveHint=True`, ungated, and now live on the bridge — the lane wrappers are the ONLY chat-facing path; network trust stays as-is).

**Alternatives considered**: routing tier 3 through the windows-mcp PowerShell tool with a wrapper — rejected (duplicates the draft/confirm store, two sources of truth for the never-list); extending `hermes_run_command`'s spec-033 list for tier 2 instead of a lane-local allowlist — rejected (mixes gateway concerns; the settings-read list is applet-feature-specific).

## R3: Tier-4 tool semantics (captured from the live surface + source)

**Decision**: the sequence orchestrator uses `Snapshot` (state tree) to locate controls, `Click`/`Type` to act, `Wait`/`WaitFor` for transitions, `Screenshot` for the confirm-time visual relay.

**Live evidence**: the 21-tool listing (R1) plus the gate source (`ControlToolGate.on_call_tool`): every call passes the control-lease check — the USER_CONTROL deferral already observed in the lane applies to ALL tools, so GUI sequences inherit the named-deferral envelope and must budget waits.

**Alternatives considered**: `MultiEdit`/`MultiSelect` batching — deferred (complexity; single-step confirmations first).

## R4: USER_CONTROL and the desktop dependency in GUI sequences

**Decision**: a GUI sequence is a series of gated calls; between them the desktop user may be active. The lane reuses the existing USER_CONTROL wait-retry (bounded) per step and surfaces the named deferral on exhaustion; sequences never hang past the turn budget; an interrupted sequence reports which steps completed (audited) and never claims the rest.

**Rationale**: single-call semantics proven 2026-11-14 (consent-wait retry + deferral envelope); sequence semantics are the same contract, one step at a time.

## R5: The test plan (the owner's explicit requirement: unit + E2E + error handling)

**Decision** (`quickstart.md` is the runnable plan):
- **Unit** (deterministic, fake-session style): launcher bounds/ask-backs; read-allowlist refusals (unmapped, write-shaped); tier-3 reuse pins (never-list extension — remote-access refusals incl. firewall-profile disable, adapter disable, IP/gateway; firewall-rule changes allowed-after-confirm); UI gate (sequence text, credential-field refusal, UAC stop, cascade re-confirm, never-list-via-click); audit classes per tier; loop-gate classification.
- **E2E (live)**: open each starter applet + a settings page (<15 s); read queries before/after state-unchanged; a benign confirmed write; a never-list write refused after confirm; a GUI flow on the safe starter set with confirm; the refusal, deferral, down-service, and UAC cases.
- **Error handling** as first-class cases at every tier: unknown target ask-back, unmapped read refusal, unconfirmed write no-op, modified-confirmation re-draft, never-list refusal verbatim, credential-field refusal, UAC honest stop, dialog cascade, service-down envelope, USER_CONTROL deferral, desktop-disconnected.
