# Implementation Plan: Skill Manager (spec 036)

**Branch**: `036-skill-manager` | **Date**: 2026-11-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/036-skill-manager/spec.md`, governing architecture `/specs/035-ai-helpdesk-architecture/` (spec, plan, research R1–R3/R7, data model, contracts, test plan 1a/1b/E1/E5/E6/A3).

## Summary

The Skill Manager is the first component of the 035 architecture: a server-side shared skill store (WSL, inside the existing sidecar package) with semantic intent search riding the existing embeddings path, parameterized workflow records, trust-gated reuse (>80% AND ≥3 successes, feedback-driven decay), versioned same-name updates, escalation-without-deletion, live re-confirmation of gated steps during replay (035 FR-020), and audit on every operation. It surfaces as four additive MCP tools on the existing sidecar plus the classifier/lane DSL rules for the skill loop. New module: `src/agentic_rag_mcp/skill_manager/`; four new tools (29 → 33).

## Technical Context

**Language/Version**: Python 3.12, existing sidecar `src/agentic_rag_mcp/`.

**Primary Dependencies**: Existing only — `search/embeddings.py` `Embedder` (sentence-transformers) for semantic intent search; `store/vectordb.py` (LanceDB) as the vector index; SQLite (stdlib `sqlite3`) for transactional skill/feedback records; existing `hermes_audit.py` writer for audit rows; existing gate modules (`hermes_powershell_gate/state`, `office_gate`, `run_gate`) called by the replay executor. No new third-party dependencies (Constitution III).

**Storage**: SQLite at `~/.config/agentic-rag-mcp/hermes-mcp/skills.db` (WAL mode) for skills/feedback; a LanceDB table for intent vectors; audit stays in the existing JSONL. Store survives sidecar container restarts via the same bind-mount as the audit log.

**Testing**: pytest — `tests/unit/test_skill_trust.py`, `test_skill_executor.py`, `test_skill_store.py` (035 test-plan 1a/1b, extended); live battery via `python -m agentic_rag_mcp.deploy verify` (+ E1/E5/E6 scenarios); adversarial A3 (replay bypass) and A6 (fabricated completion) mandatory per 035 SC-007.

**Target Platform**: WSL Ubuntu server side; no Windows-side changes (the executor reuses existing lanes).

**Project Type**: Sidecar extension — new module + 4 additive MCP tools + DSL lane rules. No new services, no new containers.

**Performance Goals**: `skill_search` adds one embed+ANN round trip (< ~200 ms local) to operational turns only; replay itself is bounded by the lanes it calls (existing TIMING profiles).

**Constraints**: 035 FR-020 (gated steps re-confirm live) is non-negotiable; store-down must degrade (FR-013/036); Dify `tool_mcp_providers` rebuild + api/worker restart on the 4 new tools; never-list binding inherited.

**Scale/Scope**: Single shared store, single host (v1 fleet); skills are fleet-global by name (035 clarification).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Contract Preservation | ✅ Pass | 29 → 33 tools, purely additive; no existing schema touched; `ask` field set unchanged |
| II. Tests-First | ✅ Pass | Trust matrix, executor, store, and adversarial A3/A6 suites written before implementation (035 test-plan inherited) |
| III. Minimal Dependencies | ✅ Pass | stdlib SQLite + existing Embedder/vectordb/audit; zero new dependencies; no new runtime service |
| IV. Honest Answers | ✅ Pass | Trust data surfaced with every hit; not-found explicit; store-down honest; A6 fabrication guard extends to the skill lane |
| V. Spec-Driven Replacement | ✅ Pass | No supersession — new component |

**Post-Phase-1 re-check**: still all-pass — the design adds a module inside the existing package and four additive tools; the replay executor calls existing gates rather than duplicating them (no dead code, no parallel gate logic).

## Project Structure

### Documentation (this feature)

```text
specs/036-skill-manager/
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
├── skill_manager/            # NEW
│   ├── __init__.py
│   ├── store.py              # SQLite skills/feedback store (save/update/get/list, trust calc)
│   ├── intent.py             # embed descriptions + ANN search over skills (Embedder + LanceDB)
│   ├── executor.py           # replay: substitution, per-step expect checks, gated-step live confirm
│   └── api.py                # the 4 MCP tool handlers (search/get/save/feedback)
├── server.py                 # +4 tool registrations (skill_search, skill_get, skill_save, skill_feedback)
├── hermes_audit.py           # + skill-* operation rows
└── search/embeddings.py, store/vectordb.py   # reused, unchanged

dify/AGIAssistant/AGI_Assistant.yml          # classifier class + lane instructions: skill loop rules
tests/unit/test_skill_store.py               # NEW
tests/unit/test_skill_trust.py               # NEW (035 test-plan 1a)
tests/unit/test_skill_executor.py            # NEW (035 test-plan 1b)
tests/integration/test_skill_lanes.py        # NEW (E1/E5/E6 live-path harness)
```

**Structure Decision**: single-package extension — the Skill Manager is a module of the existing sidecar (server-side WSL per 035 clarification), its tools register alongside the existing 29, and the replay executor calls the existing gate modules. No new top-level projects, no new containers.

## Complexity Tracking

> Not required — Constitution Check passes with no violations.