---
description: "Task list for Windows-MCP lane enablement"
---

# Tasks: Windows-MCP lane enablement (040-windowsmcp-powershell)

**Input**: Design documents from `specs/040-windowsmcp-powershell/` (plan.md, spec.md, research.md, data-model.md, contracts/windowsmcp-lane.md, quickstart.md)

**Tests**: INCLUDED — the owner explicitly required unit tests, end-to-end test cases, and error handling for this feature. Tests are written FIRST in each story (red), then implemented (green).

**Organization**: Tasks grouped by user story; each story independently implementable and testable per spec.md.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependencies on incomplete tasks)
- **[Story]**: user story (US1, US2, US3)
- Exact file paths in every description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: package skeleton + the lane's constants of record

- [X] T001 Create the lane package `src/agentic_rag_mcp/windows_mcp/__init__.py` exporting the public surface (client + health) per plan.md structure
- [X] T002 [P] Add the lane constants to `src/agentic_rag_mcp/windows_mcp/client.py`: bridge URL `http://172.17.0.1:18800/sse`, mandatory canonical `Host: 127.0.0.1:8800` header (the verified 400-fix, research.md R1), 2 s probe budget, recovery text naming `schtasks /run /tn windows-mcp-server`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the transport core every story depends on

- [X] T003 Implement the SSE MCP session factory with the mandatory canonical Host header on every request in `src/agentic_rag_mcp/windows_mcp/client.py` (initialize/tools-list/tools-call lifecycle via the existing `mcp` client; no request may leave without the header)
- [X] T004 [P] Implement args validation against the captured tool schemas (`Process` mode/name/pid/sort_by/limit/force; `Clipboard` mode/text; `Notification` title/message/app_id; `Registry` mode/path/name/value/type — contracts/windowsmcp-lane.md) with `blocked:` envelopes and NO service call on invalid shape, in `src/agentic_rag_mcp/windows_mcp/client.py`
- [X] T005 [P] Implement the audit integration in `src/agentic_rag_mcp/windows_mcp/client.py`: every attempt through the shared `HermesAudit` funnel, operation `windows-mcp-<tool>` / `windows-mcp-status`, decisions executed/blocked/error, `conversation_id` always present, `duration_s` recorded

**Checkpoint**: transport core + validation + audit wiring ready — stories can begin.

---

## Phase 3: User Story 1 - One real consented command end-to-end (Priority: P1) 🎯 MVP

**Goal**: the stack drives the Windows-MCP service through the repaired lane and relays genuine output — the top-5-process acceptance case (already transport-proven live during planning).

**Independent Test**: quickstart.md E2E-1 — `Process mode=list sort_by=memory limit=5` returns the genuine host process table, < 30 s, audit row `windows-mcp-process` decision executed; plus the unit battery green.

### Tests for User Story 1 (write first, expect red)

- [X] T006 [P] [US1] Unit contract pins in `tests/unit/test_windows_mcp_lane.py`: canonical Host header on every request; honest envelope texts; tool-schema validation blocked paths; audit row shape (operation/decision/conversation_id) — mirror the `test_loop_gate.py` style
- [X] T007 [P] [US1] Behavioral unit tests with a fake SSE server in `tests/unit/test_windows_mcp_lane.py`: accept-then-close → unavailable envelope; HTTP responder → ok; request WITHOUT the canonical Host header → the `400 Invalid host header` failure reproduced

### Implementation for User Story 1

- [X] T008 [US1] Implement the tool-call wrappers in `src/agentic_rag_mcp/windows_mcp/client.py` — `process_list(sort_by, limit)` first-class, generic dispatch for the other three tools, genuine-output relay, `error:windows-mcp-tool-error` verbatim on service errors (depends T003, T004, T005)
- [X] T009 [US1] Live E2E harness `tests/integration/test_windows_mcp_e2e.py`: quickstart E2E-1 (top-5-process round-trip, genuine output, < 30 s, audit row)

**Checkpoint**: User Story 1 fully functional — the acceptance case runs from the stack.

---

## Phase 4: User Story 2 - Durable lane + honest health (Priority: P2)

**Goal**: the lane's state is reported truthfully from the sidecar vantage, with a recovery hint that names a task that exists, and the lane survives reboots.

**Independent Test**: quickstart.md E2E-2 — with the host task stopped, the probe reports the unavailable envelope with the recovery hint in < 5 s; after `schtasks /run /tn windows-mcp-server`, E2E-1 passes again.

### Tests for User Story 2 (write first, expect red)

- [X] T010 [P] [US2] Unit tests for the probe in `tests/unit/test_windows_mcp_lane.py`: HTTP-level probe with canonical Host (any response = reachable; accept-then-close/EOF/timeout = down with envelope); probe-before-envelope ordering (no fabricated reachable — the browser-lane lesson); envelope names `windows-mcp-server`

### Implementation for User Story 2

- [X] T011 [US2] Implement `probe_windows_mcp()` in `src/agentic_rag_mcp/windows_mcp/health.py` (HTTP-level through the bridge, 2 s never-hang budget, honest unavailable envelope with the recovery text) mirroring `browser_lanes/dynamic_health.py`
- [X] T012 [US2] E2E-2 harness case in `tests/integration/test_windows_mcp_e2e.py`: stop task → envelope < 5 s → start task → E2E-1 passes

**Checkpoint**: Stories 1 and 2 independently functional.

---

## Phase 5: User Story 3 - Audited, bounded, error-honest relays (Priority: P3)

**Goal**: every failure class is named honestly, output is bounded with truncation named, and every attempt lands in the audit trail.

**Independent Test**: quickstart.md E2E-3/E2E-4 — invalid args → blocked envelope with no service call; a service-side error → verbatim relay; large output → bounded with the truncation named; audit rows present for all classes.

### Tests for User Story 3 (write first, expect red)

- [X] T013 [P] [US3] Unit tests in `tests/unit/test_windows_mcp_lane.py` for the error classes: consent-declined/timeout named refusal (never fabricated success), service-error verbatim envelope, output bounding with named truncation, blocked-before-dispatch ordering

### Implementation for User Story 3

- [X] T014 [US3] Implement the error-class wrappers + output bounding (house-rule truncation naming) in `src/agentic_rag_mcp/windows_mcp/client.py`
- [X] T015 [US3] E2E-3/E2E-4 harness cases in `tests/integration/test_windows_mcp_e2e.py`: invalid-args blocked, genuine service error relayed, large output bounded

**Checkpoint**: All three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T016 [P] Run the full quickstart.md battery + `pytest tests/unit -q` green + `ruff check` clean on all touched files; update `specs/040-windowsmcp-powershell/checklists/requirements.md` if any item changed
- [X] T017 Rebuild the sidecar (`python -m agentic_rag_mcp.deploy redeploy`) so the module ships in the image; verify health/imports in-container; note E2E-5 (post-reboot durability) for the next natural reboot
- [X] T018 Commit and push the feature (lifecycle-style message; working tree clean)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: immediate; T001 → T002 parallel-friendly
- **Foundational (Phase 2)**: after Setup; T003 first, then T004/T005 in parallel — BLOCKS all stories
- **Stories (Phases 3-5)**: each after Phase 2; US1 → US2 → US3 in priority order (US2/US3 can parallel if staffed)
- **Polish (Phase 6)**: after the desired stories complete

### User Story Dependencies

- **US1 (P1)**: after Foundational — no other story needed (MVP)
- **US2 (P2)**: after Foundational; uses the same client module (independently testable)
- **US3 (P3)**: after Foundational; extends US1's wrappers (independently testable)

### Within Each User Story

- Tests first (red) → implementation (green) → live E2E harness

### Parallel Opportunities

- T002, T004, T005 within their phases; T006/T007 (both in the new test file, written together); T010, T013 (same file, disjoint sections)

---

## Parallel Example: User Story 1

```bash
# Launch the US1 test pair together:
Task: "T006 unit contract pins in tests/unit/test_windows_mcp_lane.py"
Task: "T007 fake-SSE behavioral tests in tests/unit/test_windows_mcp_lane.py"
# Then implement against red tests:
Task: "T008 tool-call wrappers in src/agentic_rag_mcp/windows_mcp/client.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 + Phase 2 (transport core with the Host fix)
2. Phase 3 (US1: tests red → implementation → live top-5 E2E)
3. STOP and VALIDATE: quickstart E2E-1 passes → the acceptance case is delivered

### Incremental Delivery

1. MVP (US1) → 2. honest health + durability (US2) → 3. error classes + bounding (US3) → 4. Polish (battery, rebuild, commit)

---

## Notes

- Provenance (T021, convergence 2026-11-14): `windows/safe-shutdown.ps1` is an owner-requested session artifact (WSL-only safe shutdown, 2026-11-14) that ships alongside this feature but is outside spec 040's scope.

- The transport fix (canonical Host header) is the feature's core — verified live during planning; every test layer pins it.
- No new chat tool, no DSL change, no host-side change (clarified Option A).
- The live E2E harness cases touch the real Windows host service — run on demand (house pattern: integration harnesses are not CI gate).
- E2E-2 must restore the `windows-mcp-server` task after stopping it — never leave the lane down.
- Commit after each task or logical group; keep the audit trail's integrity rule (append-only, never rewritten).

---

## Phase 7: Convergence

- [x] T019 Live-verify the declined-consent refusal per FR-003 (partial): run one privileged lane call live (e.g. a scratch Registry write) while the owner clicks Decline on the host prompt; expect the `blocked: the host did not approve execution` envelope and an audit row `decision: blocked`
  - **Finding (2026-11-14)**: verified live with three privileged shapes (Registry set, process kill of a sacrificial notepad, registry delete) — **this WindowsMCP build does not consent-gate any operation** (all executed directly, no prompt); the USER_CONTROL consent flow belongs to the agent's gateway path (spec 034), not this service. The lane's refusal handling (classification → blocked envelope → audit blocked) remains unit-pinned and correct for service builds that do gate. Probe key cleaned (deleted), sacrificial process terminated by the lane itself.
- [ ] T020 Verify post-reboot durability per SC-003/FR-005 (partial): after the next natural Windows reboot + logon, run the quickstart.md battery (E2E-5) from the container vantage and record the result in this file's Notes section
- [x] T021 Add a one-line provenance note for windows/safe-shutdown.ps1 (unrequested): document it in this file's Notes section as an owner-requested session artifact (2026-11-14) outside spec 040 scope
