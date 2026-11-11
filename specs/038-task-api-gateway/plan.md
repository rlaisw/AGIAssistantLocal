# Implementation Plan: Task-API Gateway (spec 038)

**Branch**: `038-task-api-gateway` | **Date**: 2026-11-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/038-task-api-gateway/spec.md`, governing architecture `/specs/035-ai-helpdesk-architecture/` (research R5, FR-009/013/014, test plan gateway rows, error matrix), closed siblings 036 (skill loop, state patterns) and 037 (Scheduled-Task pattern, A2 harness).

## Summary

The third 035 component: a plain-HTTP **task-API gateway service on the Windows host** (`127.0.0.1:8080`) exposing the 035-R5 endpoint shapes (`/api/helpdesk/tier1`, `/api/helpdesk/tier2`, `/api/office/install`, `/api/helpdesk/job/{id}`), plus the **sidecar lane** that gates every interaction: Tier-1-first protocol, conversation-scoped Tier-2 recommendation+confirmation state, the never-list binding even confirmed, poll-based long jobs off the 300 s stream, structured-JSON-only handling with honest malformed/outage envelopes, and audit on every attempt. New sidecar module `task_gateway/` (client + tier2 state + never-list extension); new service `services/task-gateway/` on the Windows side; 35 → 39 tools.

## Technical Context

**Language/Version**: Python 3.12 sidecar (`src/agentic_rag_mcp/task_gateway/`); the Windows gateway service is Python stdlib-only (`http.server`/`json` — no FastAPI: Constitution III, the service is three endpoints and a job table) launched via Scheduled Task.

**Primary Dependencies**: Existing only — `HermesAudit` (audit rows incl. `conversation_id`), the spec-034 never-list patterns (extended, not duplicated — one shared source), `hermes_powershell_state` pattern for the tier-2 state, `httpx` (installed) for the sidecar→host gateway client. `cli-anything-hub` 0.4.1 is INSTALLED but used only as a **script donor** where its harnesses fit Tier-1 tasks; the service endpoints are ours (spec assumption: shapes are the contract).

**Storage**: Gateway job table in-memory + on-disk JSONL under `C:\ProgramData\agentic-rag\task-gateway\jobs.jsonl` (job start/progress/completion rows, append-only — the durable record mirrors the audit discipline); sidecar tier-2 state in-memory conversation-scoped (034 pattern).

**Testing**: pytest unit suites (`test_task_tier2_state.py`, `test_task_gateway_lane.py`, `test_neverlist_extension.py`); integration: A1 gate-shopping + A4 never-list-via-Tier-2 (035 SC-007 mandatory); live battery via `deploy verify` extension + quickstart.

**Target Platform**: Windows 11 host (`127.0.0.1:8080`, loopback-bound), sidecar in WSL reaching it over the host network (`http://$(hostname -I gateway)/…` — mirrored networking, same as the Hermes gateway path); Scheduled Task auto-start (037 pattern).

**Project Type**: Sidecar extension + a new small host service + DSL lane rules. No new containers.

**Performance Goals**: Tier-1 responds in seconds (quick fixes only); install jobs poll at ~5 s intervals; no lane call held open near 300 s (FR-005 structural: job + poll, never a held stream).

**Constraints**: 035 FR-013 binding (never-list even confirmed — Q3=C); structured JSON only; one issue per request; Dify `tool_mcp_providers` staleness rule on the 4 new tools; the Dify agent node carries NO raw HTTP tool (FR-007 structural).

**Scale/Scope**: Single host. The service wraps Tier-1 quick-fix script set + DISM/SFC-class Tier-2 + ODT Office install — a curated set, not a general script-runner (that boundary IS the security surface).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Contract Preservation | ✅ Pass | Additive tools (35 → 39); existing schemas byte-identical; the 034 never-list patterns move to a shared module with the SAME patterns verbatim — 034's contract tests re-run green against it |
| II. Tests-First | ✅ Pass | Tier-2 state, lane protocol, never-list extension, adversarial A1/A4 suites red before implementation |
| III. Minimal Dependencies | ✅ Pass | Gateway service is stdlib http.server (no FastAPI); sidecar reuses httpx + existing audit/state; cli-hub used as script donor only where it fits |
| IV. Honest Answers | ✅ Pass | Structured-JSON-only, malformed→error envelope distinct from "none", job states real at every poll, outage envelope with recovery — never a fabricated verdict anywhere in the protocol |
| V. Spec-Driven Replacement | ✅ Pass | No supersession — new component; the 034 never-list moves to shared source with 034's tests re-pinned against it (not a rewrite of semantics) |

**Post-Phase-1 re-check**: still all-pass — the shared never-list module preserves 034 behavior verbatim (034 suite re-runs green), the tier-2 state mirrors the 034 pending-draft semantics, and the service is three endpoints + a job table.

## Project Structure

### Documentation (this feature)

```text
specs/038-task-api-gateway/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
src/agentic_rag_mcp/
├── task_gateway/             # NEW (sidecar half)
│   ├── __init__.py
│   ├── client.py             # httpx client: tier1/tier2/install/job-status + honest envelopes
│   ├── tier2_state.py        # conversation-scoped recommendation+confirm (034-pattern state)
│   ├── neverlist.py          # shared never-list module (034 patterns extended; 034 re-pins to it)
│   └── lane.py               # the 4 MCP tool handlers + protocol checks + audit
├── hermes_powershell_gate.py # imports neverlist patterns from the shared module (V-safe move)
└── server.py                 # +4 tools (task_helpdesk_tier1, task_helpdesk_tier2,
                              #     task_office_install, task_job_status) — additive

services/task-gateway/        # NEW (Windows-host half)
├── service.py                # stdlib http.server: the 4 endpoints, job table, JSONL rows
├── tier1_scripts/             # curated quick-fix scripts (printer queue, service restart, cache clear)
└── run_service.cmd           # Scheduled Task entrypoint

windows/task-gateway-task.xml # NEW — Scheduled Task definition (037 pattern)
tests/unit/test_task_*.py     # NEW suites
tests/integration/test_task_a14.py  # A1 + A4 adversarial harness

dify/AGIAssistant/AGI_Assistant.yml  # issue-intent routing + tier protocol rules + no-raw-HTTP pin
```

**Structure Decision**: two halves, one spec — the service is the smallest stdlib surface that satisfies the R5 shapes (three endpoints + job status), the sidecar lane owns ALL security (protocol, confirmation, never-list), and the never-list moves to ONE shared module so 034 and 038 enforce identical patterns (no drift).

## Complexity Tracking

> Not required — Constitution Check passes with no violations.