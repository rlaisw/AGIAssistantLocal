---
description: "Task list for Windows-MCP Applet Control (041)"
---

# Tasks: Windows-MCP Applet Control (041-windows-mcp-applet-control)

**Input**: Design documents from `specs/041-windows-mcp-applet-control/` (plan.md, spec.md, research.md, data-model.md, contracts/applet-tiers.md, quickstart.md)

**Tests**: INCLUDED — the owner explicitly required unit tests + end-to-end cases + error handling (quickstart.md is the test plan). Tests are written FIRST in each story (red), then implemented (green).

**Organization**: Tasks grouped by user story (US1 open → US2 read → US3 confirmed write → US4 GUI), each independently implementable and testable per spec.md.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependencies on incomplete tasks)
- **[Story]**: user story (US1, US2, US3, US4)
- Exact file paths in every description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: the bounded target inventory and the live tool schemas the tiers build on

- [X] T001 Create the reviewed settings-target inventory in `src/agentic_rag_mcp/windows_mcp/targets.py` — the .cpl applets + ms-settings: pages list (the inventory reviewed 2026-11-15, spec Assumptions), each entry `{kind: cpl|settings_page, identifier, display_name}`; unknown/ambiguous resolution and ask-back helpers per the tier-1 contract
- [X] T002 [P] Capture the live tool schemas (App, PowerShell, Snapshot, Screenshot, Click, Type, Move, Scroll, Shortcut, Wait, WaitFor, DisplayInventory) into `src/agentic_rag_mcp/windows_mcp/schemas.py` as constants — extend `TOOL_SCHEMAS` in `src/agentic_rag_mcp/windows_mcp/client.py` to validate the new tools' args (probe the live service for exact arg names; research.md R1 confirms the 21-tool surface)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the shared gate pieces every story depends on

- [X] T003 Extend the never-list in `src/agentic_rag_mcp/hermes_powershell_gate.py` with the remote-access-cutting class per FR-005 and the 2026-11-15 clarifications — adapter enable/disable, IP/gateway changes, firewall-PROFILE disable, remote-access and account changes are refused ALWAYS (draft and confirm); individual firewall-rule additions/changes are NOT never-listed (confirmed-only boundary); tests in `tests/unit/test_powershell_gate.py` pin both sides
- [X] T004 [P] Implement the settings read-allowlist gate in `src/agentic_rag_mcp/windows_mcp/read_gate.py` per the tier-2 contract — fixed command shapes only (network adapters, power plan, firewall-rule listing, volumes, system/locale facts); unmapped or write-shaped requests refused with the list shown; one query per request (mirror the `hermes_run_gate.py` pattern)
- [X] T005 [P] Wire the new operation classes into the shared funnel: audit operation names `windows-mcp-open-<kind>` / `windows-mcp-read-<name>` / `windows-mcp-gui-<step>` through `HermesAudit` (decision mapping executed/blocked/error), and add the open/read ops to `EXEMPT_OPS` in `src/agentic_rag_mcp/loop_gate.py` (deterministic fast path, the spec-040 precedent) — GUI/confirm ops keep the existing loop rules

**Checkpoint**: gates and schemas ready — stories can begin.

---

## Phase 3: User Story 1 - Open any settings surface (Priority: P1) 🎯 MVP

**Goal**: "open device manager" / "open display settings" opens the window on the owner's desktop.

**Independent Test**: quickstart E2E-1 + EH-1 — a listed applet/page opens < 15 s, audited executed; an unknown target asks back with the list; one target per request.

### Tests for User Story 1 (write first, expect red)

- [X] T006 [P] [US1] Unit tests in `tests/unit/test_windows_mcp_applets.py::TestOpenTier`: target-list membership; unknown/ambiguous → ask-back envelope naming the list; one-target rule; identifier-only execution (no extra arguments reach the service); audit class `windows-mcp-open-*`

### Implementation for User Story 1

- [X] T007 [US1] Implement the launcher in `src/agentic_rag_mcp/windows_mcp/open.py` + register `windows_mcp_open_settings` in `src/agentic_rag_mcp/server.py` + the DSL routing rule in `dify/AGIAssistant/AGI_Assistant.yml` (open-phrasings → the tool FIRST; ambiguous asks back; honest relays; the shared down/deferral envelopes)
- [X] T008 [US1] Live E2E-1 + EH-1 (+ EH-8/9 for the shared envelopes) in `tests/integration/test_windows_mcp_applets_e2e.py` per quickstart.md — opens < 15 s, audit rows, unknown-target ask-back, service-down envelope with the real recovery

**Checkpoint**: MVP — settings surfaces open from chat, honestly gated.

---

## Phase 4: User Story 2 - Read settings, state unchanged (Priority: P2)

**Goal**: "what's my power plan?" answers with genuine values, no confirmation, provably state-unchanging.

**Independent Test**: quickstart E2E-2 + EH-2 — genuine values < 30 s; config snapshot before/after identical; unmapped/write-shaped refused with the list.

### Tests for User Story 2 (write first, expect red)

- [X] T009 [P] [US2] Unit tests in `tests/unit/test_windows_mcp_applets.py::TestReadTier`: allowlist match → the fixed command shape; unmapped → refusal with the list; write-shaped ("change/set/disable") → refusal; one-query rule; audit class `windows-mcp-read-*`

### Implementation for User Story 2

- [X] T010 [US2] Implement the read wrapper (read_gate → the lane's PowerShell-tool call path) + register `windows_mcp_read_settings` in `src/agentic_rag_mcp/server.py` + the DSL rule in `dify/AGIAssistant/AGI_Assistant.yml`
- [X] T011 [US2] Live E2E-2 + EH-2 in `tests/integration/test_windows_mcp_applets_e2e.py` — genuine output < 30 s, before/after state-unchanged proof, refusal cases

**Checkpoint**: Stories 1-2 independently functional (the nondestructive tiers live).

---

## Phase 5: User Story 3 - Confirmed settings write (Priority: P3)

**Goal**: settings changes run only through the existing two-phase machinery with the extended never-list.

**Independent Test**: quickstart E2E-3 + EH-3/EH-4 — a benign write executes after verbatim draft + plain confirm; a remote-access-class write is refused at draft AND confirm; an unconfirmed draft never runs.

### Tests for User Story 3 (write first, expect red)

- [X] T012 [P] [US3] Unit tests in `tests/unit/test_powershell_gate.py`: the remote-access-cutting class refused at both phases (adapter disable, IP/gateway, firewall-profile disable, account changes); firewall-rule additions/changes NOT refused (the clarified boundary); re-draft on modification; confirm-carries-no-text

### Implementation for User Story 3

- [X] T013 [US3] Wire tier 3 in `dify/AGIAssistant/AGI_Assistant.yml` — settings-write phrasings route to the EXISTING `hermes_run_powershell` two-phase flow (no new execution path; the never-list extension from T003 binds); the routing rule names the honest-refusal and re-draft contracts
- [X] T014 [US3] Live E2E-3 + EH-3/EH-4 in `tests/integration/test_windows_mcp_applets_e2e.py` — benign confirmed write < 60 s post-confirm; never-list refused twice (0% execution); unconfirmed draft a no-op; audit rows carry the refusals

**Checkpoint**: Stories 1-3 functional; the write tier fully gated.

---

## Phase 6: User Story 4 - GUI flow on the safe starter set (Priority: P4)

**Goal**: a plain-word-confirmed click/type sequence completes in a starter applet (uninstall, power options, display, sound, date/time) with every stop condition honest.

**Independent Test**: quickstart E2E-4 + EH-5/6/7 — sequence drafted in plain words → confirm → steps execute with per-step audit; credential fields refused before any call (value absent from audit); UAC → honest stop; unexpected dialog → stop + re-confirm.

### Tests for User Story 4 (write first, expect red)

- [X] T015 [P] [US4] Unit tests in `tests/unit/test_windows_mcp_applets.py::TestGuiTier` (fake-session style): sequence-draft text shape (control + effect per step); credential/password field refusal BEFORE any call with the value absent from audit; UAC → stop + honest text; dialog cascade → stop + re-confirm; never-list-via-click refused verbatim; per-step audit rows `windows-mcp-gui-*`

### Implementation for User Story 4

- [X] T016 [US4] Implement the GUI orchestrator in `src/agentic_rag_mcp/windows_mcp/gui.py` — sequence stored as a `gui_sequence` draft in the existing confirm store (confirm carries no text); step execution Snapshot → Click/Type/Wait via the lane; the four stop conditions with honest partial reports (completed steps named); starter-set scope enforcement; register the draft/confirm tool in `src/agentic_rag_mcp/server.py` + the DSL rule in `dify/AGIAssistant/AGI_Assistant.yml`
- [X] T017 [US4] Live E2E-4 + EH-5/6/7 in `tests/integration/test_windows_mcp_applets_e2e.py` — a throwaway-app uninstall flow end-to-end; EH-6 (UAC) may be harness-asserted against the stop contract with the owner present for one real prompt

**Checkpoint**: all four stories functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T018 [P] Pin the full surface in the deploy battery: extend `scenario_tools_surface` in `src/agentic_rag_mcp/deploy/battery.py` to assert the sidecar's new tool set (open/read/gui registrations; still NO raw PowerShell passthrough) and the live service's 21-tool surface (E2E-5, FR-001)
- [X] T019 Full battery per quickstart.md: `pytest tests/unit` green, `ruff check` clean, `deploy all` (tool count changes + DSL publish), the live E2E + EH sweep, audit cross-check (`grep windows-mcp` in the audit trail)
- [X] T020 Commit and push the feature (working tree clean; the quickstart post-reboot note carried in the message)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: immediate; T001 → T002 parallel-friendly
- **Foundational (Phase 2)**: after Setup; T003 first (US3/US4 depend on it), T004/T005 parallel — BLOCKS all stories
- **Stories (Phases 3-6)**: each after Phase 2, in priority order US1 → US2 → US3 → US4 (US2 can parallel US1; US3 depends on T003 only; US4 depends on T003 + the confirm-store pattern from US3)
- **Polish (Phase 7)**: after the stories

### User Story Dependencies

- **US1 (P1)**: after Foundational — the MVP
- **US2 (P2)**: after Foundational (T004/T005); independent of US1
- **US3 (P3)**: after T003; reuses the existing confirm machinery (no US1/US2 dependency)
- **US4 (P4)**: after T003 + US3's pattern; the highest-risk tier lands last

### Within Each User Story

Tests first (red) → implementation (green) → live E2E + error cases

### Parallel Opportunities

T002/T003/T004/T005 across their phases; T006/T009/T012/T015 (disjoint test classes, same new file except T012 in test_powershell_gate.py — parallelizable); each story's E2E after its implementation

---

## Parallel Example: User Story 1

```bash
# Launch together:
Task: "T006 unit tests for the open tier in tests/unit/test_windows_mcp_applets.py"
Task: "T004 read-gate module in src/agentic_rag_mcp/windows_mcp/read_gate.py"   # if US2 work starts early
# Then implement against red tests:
Task: "T007 launcher + registration + DSL rule"
Task: "T008 live E2E-1/EH-1 harness"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 + Phase 2 (targets, schemas, gates, audit wiring)
2. Phase 3 (US1) — STOP and VALIDATE: quickstart E2E-1 + EH-1 pass → settings surfaces open from chat, honestly gated

### Incremental Delivery

1. MVP (US1) → 2. read tier (US2) → 3. confirmed-write tier (US3) → 4. GUI tier (US4) → 5. Polish (battery pins, deploy all, commit)

---

## Notes

- Tests are a first-class deliverable (owner requirement): every story writes its unit class red first; quickstart.md is the runnable test plan (E2E-1..5, EH-1..10).
- Never register a raw passthrough of the service's `PowerShell` tool (destructiveHint=True, ungated) — the wrappers are the only chat-facing path; the battery pins this (T018).
- EH-8 (service down) and EH-9 (USER_CONTROL deferral) reuse the lane's existing honest envelopes — verify, do not rebuild.
- The live E2E cases need the owner at the desktop for confirm-gated and UAC cases; read/open cases run unattended.
- Commit after each task or logical group; append-only audit integrity rule throughout.

---

## Phase 8: Convergence

- [ ] T021 Run one real-owner E2E-4 per SC-004/EH-6 (partial): a confirmed throwaway-app uninstall through windows_mcp_gui_flow in chat — draft relayed, owner confirms, steps execute, final state relayed; record the audit rows in this file's Notes
- [ ] T022 Close the probe-residue windows on the desktop (unrequested): two Device Manager windows and two stray notepads from the routing/launcher probes — owner action, no code change
