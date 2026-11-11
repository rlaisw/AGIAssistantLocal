# Implementation Plan: Browser Lanes (spec 037)

**Branch**: `037-browser-lanes` | **Date**: 2026-11-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/037-browser-lanes/spec.md`, governing architecture `/specs/035-ai-helpdesk-architecture/` (spec, research R4/R6, data model, contracts, test plan), closed sibling `/specs/036-skill-manager/` (store, replay walk, audit patterns).

## Summary

The second 035 component: two browser lanes over one Playwright engine. **Dynamic lane** — the agent drives the already-installed official `@playwright/mcp` 0.0.85 (SSE, `127.0.0.1:3002`, verified live) through Hermes-native MCP wiring; no new server code. **Scripted lane** — named, versioned, deterministic Playwright scripts on the Windows host, wrapped as sidecar tools (`{script, args}` in, structured per-step checkpoint results out). Both lanes inherit: untrusted web content (FR-008/SC-003, adversarial A2 mandatory), audit+timing on every attempt (FR-009), routing pins (browser-never-via-OS-lane, long-flow splitting), Scheduled-Task auto-start for `:3002` (FR-010), and honest degradation (FR-011). New sidecar module `browser_lanes/`; new tools TBD by tasks (scripted-run, browser health); the dynamic lane's tools live on the Playwright server itself, reached via Hermes.

## Technical Context

**Language/Version**: Python 3.12 sidecar (`src/agentic_rag_mcp/browser_lanes/`); Windows host runs Node for the Playwright MCP server and Python for scripted runs via `uv`/system python.

**Primary Dependencies**: Existing only — `@playwright/mcp` 0.0.85 (installed, SSE `:3002`), Playwright CLI 1.65.0 + Chromium (installed this morning), `HermesAudit` (audit rows), `hermes_client` (gateway turns), config block pattern from 036. **No new third-party Python deps** (Constitution III); scripted runs invoke Playwright via the installed CLI/Node runtime on Windows, not a new Python package.

**Storage**: No new stores — scripts live as files (`scripts/browser/` in the repo, synced to the Windows host the way `ppt-master` skills ship); audit stays the existing JSONL; state (active browser session refs) is conversation-scoped in memory like the office lane.

**Testing**: pytest unit suites (`test_browser_routing_gate.py`, `test_browser_scripted_run.py`); live battery via `deploy verify` extension + quickstart; adversarial A2 (injection payload pages served locally) and A6 mandatory (035 SC-007).

**Target Platform**: WSL sidecar + Windows 11 host (WSL mirrored networking; `/mnt/c` v9fs). The Playwright server and script executions run Windows-side.

**Project Type**: Sidecar extension + host Scheduled Task + DSL lane rules. No new containers.

**Performance Goals**: Dynamic-lane steps are agent-paced (10–100 ms per Playwright action); scripted runs bounded per script with `duration_s` audited; long flows split per FR-003.

**Constraints**: 035 FR-019 binding (web content untrusted); 300 s streamed-transport ceiling (split guidance); Dify `tool_mcp_providers` staleness rule on every new sidecar tool; the dynamic server must survive reboots (Scheduled Task, FR-010).

**Scale/Scope**: Single host; single browser (Chromium). Multi-browser and fleet enrollment are out of scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Contract Preservation | ✅ Pass | Additive tools only; existing 33 schemas byte-identical; `ask` field set untouched |
| II. Tests-First | ✅ Pass | Routing gate, scripted-run, injection-defense suites written before implementation; A2/A6 adversarial trials mandated in acceptance |
| III. Minimal Dependencies | ✅ Pass | Zero new Python deps — rides installed Playwright MCP + CLI; scripts are files, not packages |
| IV. Honest Answers | ✅ Pass | Not-found scripts, ask-back params, checkpoint-failure aborts, unavailable-server envelopes — all honest by construction; FR-008 extends the anti-fabrication posture to browsed content |
| V. Spec-Driven Replacement | ✅ Pass | No supersession — new component |

**Post-Phase-1 re-check**: still all-pass — the design adds one sidecar module + host Scheduled Task + DSL rules; the dynamic server is upstream-managed (installed verbatim, not vendored), and the scripted lane is data (files) + a thin executor, so no dead code or parallel gate logic.

## Project Structure

### Documentation (this feature)

```text
specs/037-browser-lanes/
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
├── browser_lanes/            # NEW
│   ├── __init__.py
│   ├── routing_gate.py       # browser-intent classification + lane pick + OS-lane refusal
│   ├── scripted_run.py       # script registry, arg substitution, per-step checkpoints, executor
│   └── dynamic_health.py     # :3002 probe + honest-unavailable envelope + recovery text
├── server.py                 # +N tools (browser_scripted_run, browser_status) — additive
├── hermes_audit.py           # unchanged (T030 pattern already carries conversation_id)
└── skill_manager/            # unchanged (036 closed)

scripts/browser/              # NEW — named versioned Playwright scripts (data, not code packages)
└── *.py / *.md               # one file per script: name, version, params schema, expect checkpoints

dify/AGIAssistant/AGI_Assistant.yml   # browser lane classifier classes + lane instructions (FR-008 rules, A2)
windows/playwright-mcp-task.xml       # NEW — Scheduled Task definition (schtasks import), FR-010
tests/unit/test_browser_routing_gate.py
tests/unit/test_browser_scripted_run.py
```

**Structure Decision**: scripted scripts are **files in `scripts/browser/`** (name, version, params, checkpoints as data), synced to the host like the ppt-master skills — NOT a Python package (Constitution III: files over packages; the skill loop can later record new scripts as skills that reference them). The dynamic lane adds no server-side code at all: Hermes wires to the installed SSE endpoint.

## Complexity Tracking

> Not required — Constitution Check passes with no violations.