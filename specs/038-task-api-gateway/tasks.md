# Tasks: Task-API Gateway (spec 038)

**Input**: Design documents from `/specs/038-task-api-gateway/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/README.md, quickstart.md — all present. Inherited: 034 never-list patterns, 036 state/audit patterns, 037 Scheduled-Task + adversarial-harness patterns.

**Tests**: included (Constitution II — tests-first house lifecycle).

**Organization**: Tasks grouped by user story from spec.md (5 stories).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US5 per spec.md

## Phase 1: Setup

- [X] T001 Create `src/agentic_rag_mcp/task_gateway/__init__.py` + `services/task-gateway/` directory structure per plan.md (two halves: sidecar lane + stdlib host service)
- [X] T002 Add `[task_gateway]` config to `src/agentic_rag_mcp/config.py`: `task_gateway_url` default `http://172.17.0.1:8080`, connect timeout 5 s, read timeout 30 s (R5) — with graceful absence handling

## Phase 2: Foundational (blocking prerequisites)

- [X] T003 [P] Write `tests/unit/test_neverlist_shared.py` first — 034's full pattern table (format/diskpart/bcdedit/bootcfg/bootrec/vssadmin delete/reagentc/manage-bde/cipher /w/Clear-Disk/Initialize-Disk/Restore-Disk/sdelete) + tier-2 additions (smuggled "repair by formatting" class) + repair-class allowed cases (`sfc /scannow`, `DISM /Online /Cleanup-Image /RestoreHealth` WITHOUT /ResetBase) — FAIL first
- [X] T004 Extract the shared never-list into `src/agentic_rag_mcp/task_gateway/neverlist.py` (`NEVERLIST_PATTERNS` + `scan(text) -> reason | None`, byte-identical 034 patterns verbatim from data-model) and point `src/agentic_rag_mcp/hermes_powershell_gate.py` at it — **034's existing suite (`tests/unit/test_hermes_powershell_gate.py` or wherever 034 pins live) re-runs green unchanged** (Constitution V constraint quoted from plan.md)
- [X] T005 [P] Write `tests/unit/test_task_tier2_state.py` first — the 034-pattern state: `set_pending`/`pending`/`clear`/supersede (new tier1 run replaces), conversation-scoped, thread-safe — FAIL first
- [X] T006 Implement `src/agentic_rag_mcp/task_gateway/tier2_state.py` (`Tier2State` mirroring `PowerShellState` per data-model Tier2Recommendation: conversation_id, issue_type, repair_name, repair_text, created_at; supersession rule FR-004)
- [X] T007 [P] Write `tests/unit/test_task_gateway_client.py` first — honest envelopes: connect refused → `task-gateway-unavailable` + recovery text; malformed JSON/HTML → `task-gateway-malformed-response` (never parsed as content, never a fabricated "none"); recommendation values only "none"|"tier2" (anything else → error) — FAIL first

**Checkpoint**: never-list shared + 034 re-pinned; state + envelope suites green.

---

## Phase 3: US1 — Tier-1 quick fix first (P1) 🎯 MVP

**Goal**: `task_helpdesk_tier1` runs the protocol's first step with honest verdicts.
**Independent Test**: quickstart P1 — tier1 audit row, "none"→report+stop, "tier2"→pending named repair.

- [X] T008 [US1] Implement `services/task-gateway/service.py` tier-1 half: `POST /api/helpdesk/tier1` with a curated tier-1 script set (`services/task-gateway/tier1_scripts/`: service-restart, printer-queue-clear, cache-clear), structured JSON `{recommendation: none|tier2, actions, detail}`, `GET /api/healthz`, stdlib `http.server`, loopback bind
- [X] T009 [US1] Implement `src/agentic_rag_mcp/task_gateway/client.py` tier-1 call (httpx, cfg timeouts per T002) and the lane handler in `src/agentic_rag_mcp/task_gateway/lane.py`: audit `operation=task-tier1`; on "tier2" register pending state (T006) and return `pending-repair: <name>` guidance
- [X] T010 [US1] Register `task_helpdesk_tier1` MCP tool in `src/agentic_rag_mcp/server.py` (schema per contracts/README.md; `conversation_id` required; additive — existing 35 schemas byte-identical)

**Checkpoint**: US1 independently testable.

---

## Phase 4: US2 — Tier-2 confirmation + never-list binding (P1)

**Goal**: two-phase tier-2 with the named-repair confirmation and never-list refused even confirmed.
**Independent Test**: quickstart P2 + A4 — confirm/decline/silence/modify matrix + never-listed refused with both preconditions.

- [X] T011 [P] [US2] Write `tests/unit/test_task_tier2_lane.py` first — the full matrix: no-recommendation→blocked; confirm executes ONLY stored repair (confirm call carries no payload); never-list at draft AND execution → refused + escalated (FR-003); supersession by a new tier1; missing state → honest blocked — FAIL first
- [X] T012 [US2] Implement the tier-2 half of `service.py` (`POST /api/helpdesk/tier2`: bounded ~120 s sync, repair catalog per issue_type) + the tier-2 lane handler in `lane.py` (draft→`pending-confirmation` with the NAMED repair; confirm→never-list re-scan→execute stored; audits `task-tier2-draft|executed|refused`)
- [X] T013 [US2] Register `task_helpdesk_tier2` MCP tool in `server.py` (two-phase schema per contracts: `issue_type, conversation_id, confirm=False`)
- [X] T014 [P] [US2] Build the A4 adversarial harness in `tests/integration/test_task_a14.py`: seed a never-listed "repair", assert refusal + escalation WITH recommendation + confirmation, assert zero executions of the class, assert audit rows (`task-tier2-refused`) — 035 SC-007 mandate

**Checkpoint**: the destructive-surface security story is closed and pinned.

---

## Phase 5: US3 — Office install as a polled job (P1)

**Goal**: install returns a job handle; polling reports real states; nothing near 300 s.
**Independent Test**: quickstart J1 — job handle fast, real polled states, audit durations ≪ 300 s.

- [X] T015 [P] [US3] Write `tests/unit/test_task_jobs.py` first (service half, mocked exec): install→queued handle; background thread → running→progress→completed/failed; `GET /api/helpdesk/job/{id}` real at every poll; unknown id → honest not-found; JSONL rows appended per transition (data-model Job verbatim) — FAIL first
- [X] T016 [US3] Implement the install/job half of `service.py` (job table + background thread + `C:\ProgramData\agentic-rag\task-gateway\jobs.jsonl` append-only rows) + `lane.py` handlers (install → handle, never blocking; `task_job_status` → poll) + register `task_office_install` and `task_job_status` MCP tools in `server.py` (audits `task-office-install`, `task-job-status`)
- [X] T017 [US3] Add the DSL poll discipline to the lane rules: report the handle, poll on ask or turn end, never loop-poll inside one call beyond ~15 s (R4)

---

## Phase 6: US4 — No raw HTTP + gate-shopping refused (P2)

**Goal**: FR-007 structural + A1 pinned.
**Independent Test**: quickstart A1 — tool-surface enumeration shows no raw HTTP tool; cross-lane smuggling refused.

- [X] T018 [US4] Pin the tool-scope in `tests/integration/test_task_a14.py` (extend): the gateway lane's DSL tool list carries ONLY the 4 task tools + skill tools + status (no powershell/office/browser tools) and NO generic HTTP tool exists in any lane; adversarial "call the API directly with curl/POST to :8080" prompts → refused (no tool to do it with) + reported
- [X] T019 [US4] Add the gateway lane DSL wiring to `dify/AGIAssistant/AGI_Assistant.yml`: issue-intent classifier class, tier1-first protocol rules verbatim, tier-2 confirmation semantics, install job+poll discipline, never-list-refusal-is-final rule, and the lane's scoped tool list

---

## Phase 7: US5 — Managed service + honest degradation (P2)

**Goal**: the service survives reboots; outage degrades honestly.
**Independent Test**: quickstart D1 — task stopped → honest unavailable envelope within one turn.

- [X] T020 [US5] Create `windows/task-gateway-task.xml` + `services/task-gateway/run_service.cmd` (037 pattern: logon auto-start, hidden, restart-on-failure PT1M, loopback :8080) — import on the host via the elevated path (`schtasks /create /tn task-gateway-service /xml …`, the T018-of-037 UAC route), verify `:8080/api/healthz`
- [X] T021 [US5] Pin the degradation test: service stopped → tier-1 call returns `error:task-gateway-unavailable` + recovery (`schtasks /run /tn task-gateway-service`) within one turn (unit, against a dead URL)

---

## Phase 8: Polish & Cross-Cutting

- [X] T022 [P] Update `README.md` + `AGENTS.md`: tool count 35 → 39, the gateway lane feature surface + tier protocol description (house doc pattern)
- [X] T023 Run `ruff` on new sources; full pytest suite green minus the 3 pre-existing contract pins
- [X] T024 [P] Run `graphify update .`
- [X] T025 Rebuild Dify `tool_mcp_providers` rows + restart `docker-api-1`/`docker-worker-1` + `deploy chatflow` publish — deploy window
- [X] T026 Run quickstart.md live battery: P1/P2/A1/A4/J1/D1; grep the audit JSONL for `task-*` rows incl. every A1/A4 refusal — deploy window (idle host)

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 2**: T003 ∥ T005 ∥ T007 (three suites); T004/T006/T007-impl after their tests (T004 must keep 034 green — the V constraint)
- **US1 (Phase 3)**: needs client + state (T006/T009 after T002)
- **US2 (Phase 4)**: needs US1's tier-1 (recommendation source) + T003/T004 never-list
- **US3 (Phase 5)**: needs the service shell (T008) but not US2
- **US4 (Phase 6)**: needs all 4 tools registered (after T010/T013/T016)
- **US5 (Phase 7)**: T020 host ops independent; T021 after T009's envelope exists
- **Polish**: T025/T026 = the deploy window, last

### User story dependencies

- US1 and US5: independent
- US2: needs US1 (recommendations come from tier1)
- US3: needs the service shell only
- US4: needs all tools + DSL (last of the code stories)

### Parallel opportunities

- Phase 2: T003 ∥ T005 ∥ T007; T004 ∥ T006
- T014 (A4 harness) ∥ T015 (jobs suite) ∥ T011 once the never-list + state land
- T020 (host ops) parallel with any sidecar work
- T022 ∥ T024

## Parallel Example: Phase 2 kickoff

```bash
Task T003 never-list suite (tests/unit/test_neverlist_shared.py)
Task T005 tier2 state suite (tests/unit/test_task_tier2_state.py)
Task T007 client envelope suite (tests/unit/test_task_gateway_client.py)
# then after red:
Task T004 shared neverlist module (034 re-pinned green)
Task T006 Tier2State
Task T007-impl client.py envelopes
```

## Implementation Strategy

### MVP First (US1)

1. Phase 1–2 foundation (never-list shared + state + envelopes)
2. US1 tier-1 → validate P1 (quickstart)
3. **STOP and VALIDATE**

### Incremental delivery

4. US2 tier-2 + A4 → the security milestone
5. US3 install jobs → J1
6. US4 DSL + A1 pins; US5 host ops + degradation → D1
7. Polish; deploy window (T025/T026); `/speckit.converge`

## Notes

- Tests are NOT optional (Constitution II); every suite FAILs red first
- T004's constraint: 034's never-list patterns move byte-identical to the shared module and 034's suite re-runs green — this is the drift-prevention pin (R3)
- T020 needs the elevated UAC route (the 037 T018 precedent)
- A1/A4 are acceptance GATES (035 SC-007): zero gate-shopping successes or the lane fails
- The 035 program completes with this spec's deploy window — then the final `/speckit.converge` on 035 itself