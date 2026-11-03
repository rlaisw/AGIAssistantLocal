# Implementation Plan: Office Save Anywhere — user-named save locations on any folder

**Branch**: `031-office-save-anywhere` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/031-office-save-anywhere/spec.md` (+ clarify session 2026-11-03: any local location allowed, OS permissions are the guardrail; named-file overwrite = intent with the unsaved-conflict ask-back carried; reads widened consistently; unnamed saves default to the work folder) and the plan input "original plan + create test cases and add error handling" (test strategy R5, error matrix in contract + quickstart).

## Summary

A surgical amendment to the office lane's gate: the work-folder **boundary becomes a default**. The pure gate's containment check is removed for locations the user's task explicitly names (any drive, any folder); unnamed saves keep defaulting to `C:\OfficeMCP` (`hermes_office_root`, owner-configurable); the OS's own permission rules guard protected locations (no elevation — honest error relay per the existing `PARTIAL` machinery); the audit's location field now records the actual target. One wording update to the tool description (retiring the out-of-folder refusal text), one to the node instructions, and regression proof that everything else is byte-identical (US3/FR-005). Supersedes spec 030's FR-003; the file lane and launch lane are untouched.

## Technical Context

**Language/Version**: sidecar Python 3.12 (`src/agentic_rag_mcp/`); chatflow DSL (Dify); no frontend changes.

**Primary Dependencies**: unchanged from spec 030 — the Hermes gateway Responses API via `hermes_client.run_task` with `OFFICE_INSTRUCTIONS`; the gateway's native MCP connection to OfficeMCP. Zero new packages.

**Storage**: the append-only audit JSONL — `HermesAudit` unchanged; the launch/office entries' `normalized_path`/`allowed_root` fields now record the actual target (named) or the default folder (unnamed).

**Testing**: pytest — failing-first amendment suite for the widened gate (`tests/unit/test_office_gate.py` + a new overwrite/ask-back case), tool-wrapper suite (`tests/unit/test_hermes_office_tool.py` — the directive must carry the named location; the envelope must relay OS errors honestly); battery — `scenario_hermes_office_task` gains the named-location probe (the owner's exact `c:\temp\test` case) and the named-file overwrite check.

**Target Platform**: sidecar container `agentic-rag` (:28080); OfficeMCP on the Windows side (127.0.0.1:8888 over mirrored loopback); the agent runs as the signed-in Windows user — **no elevation, ever** (FR-004).

**Performance Goals**: unchanged agent-turn bounds (the 600 s Hermes timeout configured during the 2026-11-03 ops session).

**Constraints**: Constitution I — no tool added/removed; the 26-tool surface is unchanged (this amends one tool's gate + description text); existing schemas byte-identical; II — failing-first; III — zero new packages; IV — honest error relay is the core of this feature (US3/SC-002); V — Supersedes record in the spec narrows 030 FR-003.

**Scale/Scope**: single-user, single-conversation state; local drives only (network/UNC deferred per the spec's Out of Scope).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Contract Preservation | PASS | No tool added or removed — `hermes_office_task` keeps its exact schema (task, conversation_id → the same envelope keys). The gate internals + description text change; the 028 file lane and 029 launch lane are untouched; all existing contract tests stay green. |
| II. Tests-First | PASS | The gate is pure — failing-first matrix: named-anywhere saves pass (the owner's `c:\temp\test` case), out-of-work-folder refusals retire, punctuation tolerance holds, overwrite/ask-back rules, OS-error relay in the wrapper suite (client mocked). |
| III. Minimal Dependencies | PASS | Zero new packages; the change is gate logic + instruction wording + the audit field usage. |
| IV. Honest Answers | PASS | The feature IS error handling: permission-denied → the OS's error relayed honestly; overwrite → "replaced" reported; unsaved conflict → ask-back; the audit records the true target. No fabricated success anywhere. |
| V. Spec-Driven Replacement | PASS | The spec carries the Supersedes record (030 FR-003 replaced); the retired refusal text is removed from the tool description + the actionable-hint wording from bug `no-powerpoint-tool` is retired with it. |

Post-Phase-1 re-check: the design touches one pure module, one instruction block, and the battery — still PASS on all five.

## Project Structure

### Documentation (this feature)

```text
specs/031-office-save-anywhere/
├── plan.md                      # This file
├── research.md                  # Phase 0 output (R1–R4)
├── data-model.md                # Phase 1 output
├── quickstart.md                # Phase 1 output (validation guide)
├── contracts/
│   └── hermes-office-save-anywhere.md  # The amended gate contract (delta against 030's)
└── tasks.md                     # Phase 2 (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/agentic_rag_mcp/
├── office_gate.py               # MODIFIED: the containment check becomes default-only —
│                                #   named locations pass (any drive); the out-of-folder
│                                #   refusal class retires; the executable-only and
│                                #   code-exec checks unchanged
├── server.py                    # MODIFIED: the directive carries the named location verbatim;
│                                #   the tool docstring loses the containment sentence;
│                                #   the audit records the actual target
├── hermes_client.py             # MODIFIED: OFFICE_INSTRUCTIONS gain the named-location rule +
│                                #   overwrite honesty (report "replaced"; ask-back on unsaved
│                                #   conflicts; never elevate)
├── deploy/battery.py             # MODIFIED: scenario_hermes_office_task gains the named-location
│                                #   probe (c:\temp\test) + named-file overwrite check
├── hermes_gate.py / hermes_launch_gate.py / office_state.py   # UNCHANGED
└── config.py                    # UNCHANGED (hermes_office_root stays, now a default)

dify/AGIAssistant/AGI_Assistant.yml  # MODIFIED: the hermes node's office-rule wording —
│                                #   "save where the user names (any folder); unnamed → default"
tests/unit/test_office_gate.py   # MODIFIED: the widened matrix (failing-first)
tests/unit/test_hermes_office_tool.py  # MODIFIED: named-location directive + OS-error relay

**Structure Decision**: the smallest amendment that satisfies the spec — one gate rule inverted (containment→default), three wording surfaces updated, regression proof everywhere else. No new modules, no new tools, no new state.
