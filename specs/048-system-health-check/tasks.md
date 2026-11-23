---

description: "Task list for system health check implementation"

---

# Tasks: System Health Check — Read-Only Desktop Diagnosis

**Input**: Design documents from `specs/048-system-health-check/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Explicitly requested. Write all deterministic tests and owner-present probes first; confirm the expected red failure before implementation.

**Organization**: US1 delivers the complete automatic health-check MVP and reusable host/report infrastructure. US2 validates the manual-only decline and HelpDesk guidance-only boundary.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel at the same gate (different files, no incomplete dependencies).
- **[Story]**: US1 = automatic health check; US2 = manual decline and HelpDesk boundary.
- All paths are repository-relative. Live tests are owner-present and must not repair or change system settings.

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 [P] Record baseline Python unit/contract and frontend Vitest/typecheck/lint results, including the current full-suite count, in `specs/048-system-health-check/test-report.md`
- [X] T002 [P] Add sanitized health-check fixtures under `tests/fixtures/system_health/`: valid JSON with pass/warn/fail/info/skip checks, reliability records/timeline, missing-reliability data, malformed/truncated/oversized JSON, malicious HTML/text, complete self-contained HTML, and tiny valid/invalid report content
- [X] T003 [P] Add the reviewed read-only script from the feature discussion as `windows/health-check.ps1` with no settings/service/registry mutations (the only `Start-Process` is the optional `perfmon /rel` display, suppressed by `-NoReliabilityMonitor`), and record its intended SHA-256 in `src/agentic_rag_mcp/mcp_action/health.py` placeholder comments only

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add failing tests and prove external host/report contracts before wiring execution.

- [X] T004 [P] Add state tests for `system_health_check` with parameters exactly `{}`, rejecting any non-empty `printer`/`foo`/list, no host effects at draft, existing `N+1` consent/expiry/supersession/wrong-conversation behavior, and `parameters=None`/`{}` normalization in `tests/unit/test_mcp_action_state.py`
- [X] T005 [P] Add host/health tests in `tests/unit/test_mcp_action_health.py` for the pinned script hash, read-only verb allow/deny rules, fixed 32-hex run ID/wrapper paths, child 120-second timeout and kill behavior, sub-4000-character marker, JSON/HTML file existence, UTF-8/BOM/NUL/oversize/malformed handling, recomputed counts/score/overall/confidence, explicit skips, reliability unavailable, PII report fields, and no credentials
- [X] T006 [P] Add report-store tests in `tests/unit/test_mcp_action_reports.py` for 256-bit 43-character tokens, one complete HTML document ≤5 MiB, `0700`/`0600`, symlink/traversal rejection, 899.99/900/900.01 fake-clock TTL, GET no-renewal, janitor/startup cleanup, escaping of `<script>`/quotes/`&`, and no active/external content
- [X] T007 [P] Add report-route contracts in `tests/contract/test_mcp_action_report_route.py` for exact HTML bytes/MIME, no-store/CSP `sandbox`/no-referrer/no-CORS, indistinguishable 404, non-GET 405 + `Allow: GET`, expiry deletion, route isolation from screenshots, and no token/path leakage
- [X] T008 [P] Add reviewed-action tests in `tests/unit/test_mcp_action_actions.py` for `execute_system_health_check()`, fixed-command/no interpolation, marker/file reads through `/mnt/c/ProgramData/agentic-rag/health/reports`, timeout/hash/staging failures, sanitized host errors, and no blind retry
- [X] T009 [P] Add tool/service tests in `tests/unit/test_mcp_action_tool.py` for health draft no-host effects, confirm success summary/report/display/screenshot, machine `fail` still action `ok`, report/display/screenshot partial failures, 180-second health budget with only 60 seconds queue, deadline exhaustion, one Reliability Monitor launch, helpdesk guidance only, and summary-only audit with no report URL/PII
- [X] T010 [P] Add concurrency tests in `tests/unit/test_mcp_action_concurrency.py` for desktop-wide serialization, duplicate health confirms, parallel health requests, queue timeout, and no duplicate report/monitor/capture
- [X] T011 [P] Extend `tests/unit/test_mcp_action_dsl.py` for health-only prompts in General-cloud/Hermes, no registration in General-local/PPT, no health parameters, ask-first/manual/exact offer, no HelpDesk tool call/repair, report URL evidence, forged report/score/display assertions, and unchanged printer/duplex/newline binding tests
- [X] T012 [P] Add owner-present health E2E cases H-E01–H-E16 and `LiveHealthHarness` in `tests/integration/test_mcp_action_e2e.py`, including report URL/Reliability Monitor, read-only invariants, report/display/screenshot failures, malformed/timeout cases, privacy scan, and restoration/cleanup
- [X] T013 [P] Add Dify health draft/cancel cases for General-cloud and Hermes in `tests/integration/test_mcp_action_dify_contract.py`, including exact raw query/turn/conversation, no host side effect, no HelpDesk tool, and existing newline/yes regressions
- [X] T014 [P] Add report-token boundary tests in `tests/unit/test_logging_setup.py` for `/mcp-action/reports/<43>` redaction while preserving screenshot/credential redactions and leaving non-token paths unchanged
- [X] T015 Run owner-present read-only probes for `C:\ProgramData\agentic-rag\health` permissions, `/mnt/c` casing, script copy/hash, wrapper JSON/HTML/marker/child timeout, and Reliability Monitor “Performance Monitor” window verification; record exact evidence in `specs/048-system-health-check/test-report.md` without changing settings or launching a second monitor

**Checkpoint**: All deterministic tests are red for the expected missing implementation; host and display contracts are known.

---

## Phase 3: User Story 1 — Run an approved read-only health check (Priority: P1) 🎯 MVP

**Goal**: After manual guidance and explicit yes, run the fixed read-only diagnostic, publish a 15-minute report URL, display Reliability Monitor, capture evidence, summarize honestly, and refer repairs to HelpDesk guidance only.

**Independent Test**: On Windows 11, decline once (no report/monitor/screenshot), then accept. Verify the summary/report link/Reliability Monitor/screenshot, no system-setting repair, no HelpDesk tool call, and read-only before/after evidence (quickstart H-E01–H-E16).

### Implementation for User Story 1

- [X] T016 [US1] Add `system_health_check: frozenset()` to the closed action schema and reject every non-empty parameter in `src/agentic_rag_mcp/mcp_action/state.py`; normalize `None`/`{}` without touching printer/duplex behavior
- [X] T017 [US1] Implement `src/agentic_rag_mcp/mcp_action/health.py`: fixed script/output paths, SHA-256 pin, run-ID validation, hash-checked wrapper, `-NoReliabilityMonitor` invocation, child 120-second deadline/kill, stdout-to-JSON capture, `/mnt/c` artifact reads, HTML/JSON validation, summary/score/counts/confidence recomputation, and owned-artifact cleanup
- [X] T018 [P] [US1] Implement `src/agentic_rag_mcp/mcp_action/reports.py` with the 15-minute 43-character-token HTML store, 5 MiB/content validation, `0700`/`0600`, absolute TTL, janitor/startup cleanup, and no path/token leakage in failures
- [X] T019 [US1] Add `GET /mcp-action/reports/{token}` with exact 200/404/405 and CSP/no-store/no-CORS/no-referrer headers, report-store wiring/base URL, startup/shutdown/30-second cleanup in `dify/docker/mcp-server/server.py`
- [X] T020 [P] [US1] Add `/mcp-action/reports/<43>` capability-token redaction to `src/agentic_rag_mcp/logging_setup.py` without changing screenshot/credential rules
- [X] T021 [US1] Implement `execute_system_health_check()` in `src/agentic_rag_mcp/mcp_action/actions.py` using the fixed wrapper and validated artifacts; return only bounded summary/report metadata and sanitized errors
- [X] T022 [US1] Integrate health draft/confirm/execution into `src/agentic_rag_mcp/mcp_action/service.py` and `src/agentic_rag_mcp/server.py`: no-parameter proposal, health-specific result envelope, report publisher injection, 180-second budget with 60-second queue allowance and stage deadline, and summary-only audit
- [X] T023 [US1] Add `WindowsDisplay.show_reliability_monitor()` in `src/agentic_rag_mcp/mcp_action/service.py` using one `open_settings("reliability monitor")` attempt, WaitFor/Snapshot verification, App focus, and existing ScreenshotCapture; no relaunch loop and separate display/capture outcomes
- [X] T024 [P] [US1] Add host-asset staging to `src/agentic_rag_mcp/deploy/host_assets.py` and `src/agentic_rag_mcp/deploy/__main__.py`: copy `windows/health-check.ps1` to `C:\ProgramData\agentic-rag\health\health-check.ps1`, verify SHA-256 before/after, and fail closed without changing machine policy
- [X] T025 [US1] Add the report-route 404/no-store smoke and keep the 59-tool surface assertion unchanged in `src/agentic_rag_mcp/deploy/battery.py`
- [X] T026 [US1] Add `system_health_check` protocol/tool descriptions and honesty evidence rules to General-cloud and Hermes in `dify/AGIAssistant/AGI_Assistant.yml`; preserve exact offer/pending/no-parameter behavior, override automatic HelpDesk routing for health turns, and deterministically append a real report link if omitted
- [X] T027 [US1] Run the health-focused unit, contract, DSL, concurrency, and report-route suites plus all existing printer/duplex/newline/MCP regressions; record exact results in `specs/048-system-health-check/test-report.md`
- [X] T028 [US1] Redeploy the sidecar and publish the updated DSL to both explicit app IDs; verify health action/tool availability, report route, host staging, and the 59-tool surface in `specs/048-system-health-check/test-report.md`
- [X] T029 [US1] Run live Dify health draft/cancel for General-cloud and Hermes in `tests/integration/test_mcp_action_dify_contract.py`; verify no host action, no HelpDesk tool, exact raw query/turn/conversation, and unchanged newline binding, recording results in `specs/048-system-health-check/test-report.md`
- [X] T030 [US1] Run the owner-present success E2E in `tests/integration/test_mcp_action_e2e.py`: explicit or instability request, exact yes, summary/report URL/Reliability Monitor/screenshot, no repair, no HelpDesk mutation, read-only before/after evidence, recorded in `specs/048-system-health-check/test-report.md`
- [X] T031 [US1] Run the owner-present failure matrix H-E05–H-E12/H-E16 in `tests/integration/test_mcp_action_e2e.py`: report publication, display, screenshot, host offline/hash mismatch, malformed/truncated output, timeout/budget, report expiry/404, token/privacy/log checks, recorded in `specs/048-system-health-check/test-report.md`
- [X] T032 [US1] Run at least 20 owner-present full health checks, record queue/execution/evidence timings, require ≥19/20 report URL + verified display within 180 seconds, and record privacy/read-only/cleanup evidence in `specs/048-system-health-check/test-report.md`

**Checkpoint**: The automatic health-check MVP works independently and no repair or HelpDesk mutation occurs.

---

## Phase 4: User Story 2 — Decline automation and use manual diagnosis (Priority: P2)

**Goal**: Preserve manual guidance when the user declines and make repairs HelpDesk-guidance-only with no automatic handoff.

**Independent Test**: Decline the offer and verify no report/monitor/screenshot. Ask for a repair and verify HelpDesk guidance, no `task_helpdesk_*` call, no ticket, and no system change.

### Tests for User Story 2

- [X] T033 [P] [US2] Add decline/no-offer/out-of-scope cases to `tests/integration/test_mcp_action_e2e.py`, verifying no report/display/screenshot and manual guidance remains
- [X] T034 [P] [US2] Add HelpDesk guidance-only and no-tool-call cases to `tests/integration/test_mcp_action_dify_contract.py`, including an explicit repair request after a health check

### Verification for User Story 2

- [X] T035 [US2] Run the owner-present decline and repair-request scenarios through Dify; verify no health execution, no automatic HelpDesk/ticket/repair, clear manual guidance, and unchanged system state; record evidence in `specs/048-system-health-check/test-report.md`

**Checkpoint**: Both the automatic and manual-only journeys are independently validated.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T036 Run the complete Python unit/contract suite, Dify health contracts, frontend `pnpm test`, typecheck, and lint; require a fully green suite and record exact counts in `specs/048-system-health-check/test-report.md`
- [X] T037 [P] Update `AGENTS.md`, `ai-chat-landing/AGENTS.md`, `README.md`, `DEPLOY.md`, and `/home/administrator/.config/kilo/skills/agenticrag-deploy/SKILL.md` for the third reviewed action, 15-minute report URL, HelpDesk boundary, host staging, and unchanged 59-tool surface
- [X] T038 Refresh `graphify-out/graph.json` with the manual saved-node-preserving runbook if the known guard fires, then rebuild `ccc` and codebase-memory indexes; record status in `specs/048-system-health-check/test-report.md`
- [X] T039 Reconcile FR-001–FR-025 and SC-001–SC-007 against evidence in `specs/048-system-health-check/test-report.md`, verify host/container report artifacts are removed, no PII is in audit/logs, all live rows pass or are explicitly environment-blocked with owner sign-off, and no dishonest success or regression remains

---

## Dependencies & Execution Order

### Phase dependencies

- Setup T001–T003 starts immediately; T001/T002/T003 may run in parallel.
- Foundational T004–T015 depends on setup; all test tasks T004–T014 may run in parallel, T015 follows T003 and must pass before execution wiring.
- US1 T016–T032 depends on foundational. T016 depends T004; T017 depends T005/T015; T018 depends T006; T019 depends T007/T018; T020 depends T014; T021 depends T008/T017; T022 depends T009/T010/T016/T021; T023 depends T015/T022; T024 depends T003/T017; T025 depends T019; T026 depends T011/T022/T023; T027 depends T016–T026; T028 depends T027; T029–T032 depend T028.
- US2 T033–T035 depends on delivered US1 prompt/action behavior. T033/T034 may run in parallel; T035 depends both.
- Polish T036–T039 depends on all desired stories; T037 may parallel T036, T038 waits for code/docs, T039 is last.

### Within US1

- T018 may parallel T016/T017 after tests pass.
- T020 may parallel T016–T019/T021.
- T024 may parallel T019–T023 after T017.
- T025/T026 wait for route/service/display integration.
- T027 is the deterministic gate; T028 deployment; T029–T032 live gates in order.

### Parallel opportunities

- Setup T001 + T002 + T003.
- Foundation tests T004–T014.
- US1 independent files T018 + T020 + T024.
- US2 tests T033 + T034.
- T037 docs alongside T036.

## Parallel Example: Foundational tests

```text
T004 State/no-parameter tests
T005 Host script/wrapper/parser tests
T006 Report store tests
T007 Report route contracts
T008 Action executor tests
T009 Service evidence/budget/audit tests
T010 Concurrency tests
T011 Dify DSL/honesty tests
T012 Live E2E harness/cases
T013 Dify draft/cancel tests
T014 Log-redaction tests
```

## Implementation Strategy

### MVP first (User Story 1)

1. Complete T001–T015 and stop if host staging, wrapper output, Reliability Monitor, or report-route contracts cannot be proven.
2. Complete T016–T032.
3. Validate automatic health check independently, including report link, monitor, timeout/failure, privacy, performance, and read-only evidence.
4. Deliver the MVP before the manual-only path.

### Incremental delivery

1. Setup + foundational tests/probes.
2. US1 automatic diagnostic with report and Reliability Monitor.
3. US2 decline/HelpDesk guidance.
4. Full suite, docs, indexes, and final acceptance reconciliation.

## Notes

- No new MCP tool; the tool surface remains 59. No new runtime dependency.
- The report may display owner-approved PII but audit/logs may not.
- Never call `task_helpdesk_tier1`/`tier2`, create a ticket, or repair from the health action.
- Never put report URL/token/path/HTML or desktop text into audit.
- Temporary report URL and generated artifacts expire/are cleaned; host/container cleanup is part of acceptance.
- Stop at each checkpoint and validate independently.

## Phase 6: Convergence

- [X] T040 Make the H-E13 read-only service-state evidence fit the Windows-MCP 4,000-character bound by comparing a compact digest/count instead of the full service list, then run the owner-present H-E13 row and record it as passed per FR-008 (partial)
