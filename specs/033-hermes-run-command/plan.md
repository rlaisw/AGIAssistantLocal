# Implementation Plan: Hermes Run-Command Lane — Allowlisted Windows Diagnostics from Chat

**Branch**: `033-hermes-run-command` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/033-hermes-run-command/spec.md`

## Summary

A fourth Hermes lane: `hermes_run_command(task, conversation_id)` executes a **read-only diagnostics allowlist** on the user's Windows computer through the existing local-agent pathway, extending the established architecture (specs 028/029/030): a new gate module parses the request into at most one allowlisted command (bare, or with exactly one strict-charset target), refuses everything else with the list shown, and only a gated directive ever reaches the agent, which runs it via its WindowsMCP shell tool under an echo-and-attest protocol. Verdicts relay honestly (real output, bounded, truncation named), every attempt audits as `operation=run-command` with the turn timing profile, `conversation_id` is a **required** parameter (schema-enforced cancellability), and the relay-side anti-fabrication law and structural honesty check extend to the new tool.

## Technical Context

**Language/Version**: Python 3.12 (sidecar package `agentic_rag_mcp`), YAML (Dify chatflow DSL), one-line JS (honesty-check node regex)

**Primary Dependencies**: existing only — httpx (gateway client), FastMCP (tool registration), the local Hermes gateway + agent with its WindowsMCP `PowerShell` tool (verified live 2026-11-09: `hermes mcp test WindowsMCP` → 21 tools)

**Storage**: existing append-only audit JSONL (`~/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl`) — no new storage

**Testing**: pytest (unit gate matrix + tool envelope suite, mirroring `test_hermes_launch_gate.py` / `test_hermes_launch_tool.py`); live verification via the Dify publish cycle + audit/Postgres forensics per house practice

**Target Platform**: the sidecar container (`agentic-rag`, streamable-http MCP at :28080) + the Dify chatflow (live publish, then re-export to the DSL file)

**Project Type**: MCP tool + security gate inside an existing Python service; chatflow DSL update

**Performance Goals**: verdict within the configured Hermes agent-call budget (measured on this host per SC-004, amendment pattern from spec 029); gate+relay overhead < 2 s (already the measured norm for the other lanes)

**Constraints**: the allowlist is enforced in gate code, never in a prompt (Constitution IV); `conversation_id` required in the tool schema; no new Windows-side components; launch-lane contracts preserved (Constitution I)

**Scale/Scope**: one gate module (~150 lines), one tool wrapper (~80 lines), one instructions constant, DSL instruction/regex/honesty updates, two test files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|---|---|---|
| I. Contract Preservation | PASS | Purely additive: a new MCP tool and gate; the launch lane's shell refusal text keeps its pinned substance (its tests assert substrings, and the pointer sentence added per FR-008 is appended text, not changed text); `ask` contract untouched; tool list grows 27→28 via the established `sync-tools` path |
| II. Tests-First | PASS | Gate matrix + tool envelope suites specified in Phase 1 and written with the implementation (tasks phase); full suite must be green |
| III. Minimal Dependencies | PASS | stdlib + already-installed httpx/FastMCP only; no new services (the WindowsMCP shell tool already exists upstream) |
| IV. Honest Answers | PASS (core) | Echo-and-attest protocol (the 029 FR-007 lesson generalized): `ok` only when the agent echoes the exact gated command and attests completion; bounded real output, truncation named; blocked → verbatim reason; error → recovery hint |
| V. Spec-Driven Replacement | PASS | Nothing superseded — spec 029's refusal stays in force (spec §Supersedes: none) |

Post-Phase-1 re-check: no violations introduced; the honesty-check regex change is additive to a node added this same day (no published consumers depend on the pattern's exact form).

## Project Structure

### Documentation (this feature)

```text
specs/033-hermes-run-command/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── tool-contract.md # Phase 1 output
└── tasks.md             # /speckit.tasks output (next phase)
```

### Source Code (repository root)

```text
src/agentic_rag_mcp/
├── hermes_run_gate.py        # NEW — allowlist gate + intent mapping + strict target parsing
├── hermes_client.py          # MODIFIED — RUN_COMMAND_INSTRUCTIONS constant (echo-and-attest prompt)
├── server.py                 # MODIFIED — hermes_run_command tool registration (conversation_id required)
├── hermes_launch_gate.py     # MODIFIED — refusal message gains a pointer to the run-command lane (append-only)
└── hermes_audit.py           # unchanged (operation="run-command" rides the existing writer)

dify/AGIAssistant/AGI_Assistant.yml   # MODIFIED — hermes_agent instruction (run-command routing + refusal relay),
                                       #   honesty_check claims regex gains hermes_run_command,
                                       #   hermes class topic names diagnostics requests
tests/unit/
├── test_hermes_run_gate.py   # NEW — phrase→command mapping, refusal matrix, charset, ask-backs
└── test_hermes_run_tool.py   # NEW — envelope contract: blocked audited, ok only on echo+attest,
                              #   required conversation_id (schema rejection), timing present
```

**Structure Decision**: exact mirror of the launch lane's layout (gate module + client instructions + tool wrapper + two unit suites), so the diff is symmetric with a proven pattern and reviewers already know where everything lives.

## Complexity Tracking

No Constitution violations to justify. The single genuinely new mechanism beyond the 029 pattern is the **echo-and-verify step** (the tool compares the agent's echoed command against the gated directive before stamping `ok`) — one small function, bought to make fabrication at the agent layer structurally impossible rather than prompt-hoped.

## Phases

- **Phase 0 — research.md**: the six design decisions (intent mapping vs literal parsing, echo-and-attest protocol, output bound, tool placement under the existing hermes_agent node, honesty-check regex extension, required identity parameter), each with rationale and rejected alternatives. No NEEDS CLARIFICATION remains (all resolved by the spec's Clarifications + the 2026-11-09 clarify session).
- **Phase 1 — design artifacts**: data-model.md (CommandVerdict, AllowlistEntry, AuditEntry, ToolEnvelope), contracts/tool-contract.md (the MCP tool schema and verdict shapes), quickstart.md (runnable validation: gate/tool suites, live IP probe, refusal matrix, audit tail, Stop-mid-ping).
- **Next**: `/speckit.tasks` decomposes this plan into the implementation task list.
