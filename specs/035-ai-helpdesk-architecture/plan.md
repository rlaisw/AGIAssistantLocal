# Implementation Plan: AI Helpdesk Architecture (Six-Service Hermes Fleet)

**Branch**: `035-ai-helpdesk-architecture` | **Date**: 2026-11-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/035-ai-helpdesk-architecture/spec.md`

## Summary

Spec 035 is the **governing architecture** for the AI Helpdesk fleet: six services (Windows-MCP, Playwright MCP, Playwright Scripts, office-mcp, cli-anything, Skill Manager) routed per intent class through the existing Hermes gateway lanes, with a skill search/reuse/save/feedback learning loop. Per the clarified delivery model, **implementation does not land in this spec** — each component ships as its own numbered spec/lifecycle. This plan therefore delivers the **architecture program**: research decisions, the shared data model and contract vocabulary that every component spec inherits, the constitution check against the existing substrate, and the quickstart validation guide each component spec's battery follows. First component: **Skill Manager** (036), then the browser services, then the task-API gateway.

## Technical Context

**Language/Version**: Python 3.12 (sidecar, `src/agentic_rag_mcp/`); Windows-side services stay upstream-managed (OfficeMCP `uvx officemcp sse` :8888, WindowsMCP `windows-mcp-server` Scheduled Task :8800 — 21 tools incl. PowerShell/Registry).

**Primary Dependencies**: Existing stack — Hermes gateway (`172.17.0.1:8642`, bearer `API_SERVER_KEY`), sidecar container (:28080), Dify chatflow (`dify/AGIAssistant/AGI_Assistant.yml`), audit log (`~/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl`). New components later: Playwright (browser lanes), HKUDS CLI-Anything or equivalent wrapper (task-API gateway), SQLite + a vector index (Skill Manager — index tech resolved in research).

**Storage**: SQLite for skills/feedback (Skill Manager, server-side WSL); audit stays append-only JSONL; no Dify schema changes beyond `tool_mcp_providers` cache rows per new tool.

**Testing**: pytest (`tests/unit|integration|contract`); live verification battery via `python -m agentic_rag_mcp.deploy verify`; per SC-007 every component battery MUST include adversarial scenarios (refusal + audit row expected).

**Target Platform**: WSL Ubuntu (server side) + Windows 10/11 clients (WSL mirrored networking, `/mnt/c` v9fs automount).

**Project Type**: Architecture spec / program plan — one spec that spawns component specs; this plan's "implementation" = the component spec series (036+).

**Performance Goals**: Inherited from the live stack — desktop turns carry `TIMING:` profiles; long jobs (>30 s) never ride a single streamed MCP call (FR-009); skill search adds one round trip to operational turns only (FR-001).

**Constraints**: Spec-034 never-list stays binding everywhere (FR-013); 300 s Dify plugin-daemon stream ceiling (known, mitigated by split-request guidance); Dify `tool_mcp_providers` cache staleness rule (rebuild + api/worker restart on every new tool).

**Scale/Scope**: v1 fleet = the one existing Windows client (TVB-OA\RLWC145); multi-host is designed-for (FR-016/018) but not shipped.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Contract Preservation | ✅ Pass | No existing tool schema changes; new lanes add new tools additively; DSL changes ship per owning component spec (clarified), never a breaking chatflow republish |
| II. Tests-First | ✅ Pass | Each component spec lands tests before implementation, per house lifecycle; SC-007 mandates adversarial scenarios in every battery |
| III. Minimal Dependencies | ✅ Pass | Reuses the existing gateway/audit/DSL substrate; new runtime services (Skill Manager, browser services, gateway) land as separately spec'd increments with graceful degradation (skill store unavailable → manual routing, spec Edge Cases) |
| IV. Honest Answers | ✅ Pass | Anti-fabrication law + `honesty_check` + dispatch-leak guards carry over to all new lanes; FR-019 extends it to web content; refusals always name their reason |
| V. Spec-Driven Replacement | ✅ Pass | No supersession in this spec; routing-rule corrections (draft prompt's office-scope error, FR-007) are documented in Clarifications |

No violations — no Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/035-ai-helpdesk-architecture/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # NOT created by /speckit.plan (component specs carry their own tasks)
```

### Source Code (repository root)

```text
src/agentic_rag_mcp/          # existing sidecar — extended per component spec
├── hermes_client.py          # existing lanes + timing profiles
├── hermes_*_gate.py          # existing gates (file/launch/office/run/powershell)
├── server.py                 # MCP tool surface (29 tools today)
├── skill_manager/            # NEW (spec 036): store, search, feedback, API
├── browser_lanes/            # NEW (spec 037+): dynamic + scripted browser routing
└── cli_gateway/              # NEW (spec 038+): task-API gateway client + Tier-1/2 lanes

dify/AGIAssistant/AGI_Assistant.yml   # per-component classifier classes + lane nodes
tests/unit/test_*.py                   # per-component gate/store/tool tests
specs/03[6-9]-*/                       # component specs, one per service
```

**Structure Decision**: Single-project extension of the existing sidecar package — every component lands as a new module + its gate + its tests in the established layout, matching how specs 028–034 shipped. No new top-level projects.

## Complexity Tracking

> Not required — Constitution Check passes with no violations.