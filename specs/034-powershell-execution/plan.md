# Implementation Plan: PowerShell Execution Lane — Confirmed Windows-MCP Shell Commands from Chat

**Branch**: `034-powershell-execution` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/034-powershell-execution/spec.md`

## Summary

A general PowerShell lane with a **two-phase tool**: the relay drafts the exact command and the tool *registers* it (never-list-scanned, stored conversation-scoped, echoed back for verbatim display, audited with its exact text) — and only a subsequent **confirm call** executes the *stored* text through the local agent's Windows-side shell tool under the echo-and-attest protocol. The design makes the spec's core guarantees structural: what the user confirmed is byte-for-byte what runs (the stored draft executes; the confirm call carries no command text at all), and prompt injection can at most produce a *draft the owner sees and rejects* — nothing executes without the explicit chat confirmation. The office lane's compose→confirm→send email flow (spec 030) is the direct architectural precedent; the run-command lane's agent protocol (spec 033, live-proven instruction set) carries execution.

## Technical Context

**Language/Version**: Python 3.12 (sidecar package `agentic_rag_mcp`), YAML (Dify chatflow DSL), one-line JS (honesty-check node regex)

**Primary Dependencies**: existing only — httpx, FastMCP, the local Hermes gateway + agent with its `mcp__WindowsMCP__PowerShell` tool (tool inventory verified live 2026-11-09), the existing append-only audit JSONL

**Storage**: in-memory conversation-scoped pending-draft state (mirroring the office lane's pending-email state) + the audit JSONL — no new persistent storage

**Testing**: pytest (never-list gate matrix + two-phase tool suite, mirroring `test_hermes_run_gate.py` / `test_hermes_run_tool.py`); node harness re-validation for the honesty/dispatch guards; live verification via the publish cycle + audit/Postgres forensics per house practice

**Target Platform**: the sidecar container (`agentic-rag`, :28080) + the Dify chatflow (publish + Postgres verify)

**Project Type**: MCP tool + security gate + conversation state inside the existing Python service; chatflow DSL update

**Performance Goals**: execution turn within the measured agent-call envelope (the 033 lane measured 20–40 s for real commands); draft registration is gate-local (<2 s)

**Constraints**: never-list enforced in gate code, immune to confirmation (Constitution IV — prompts carry no security weight); `conversation_id` required in the tool schema; exact-match execution structural, not verified-after-the-fact; existing lanes untouched (033 direct diagnostics, launch/office/file behavior, file-lane no-delete code)

**Scale/Scope**: one gate module (~120 lines), one state module (~40 lines), tool wrapper (~110 lines), instructions constant, DSL instruction/tool/guard updates, two test files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|---|---|---|
| I. Contract Preservation | PASS | Additive: a new MCP tool (28 → 29 via `sync-tools`), a new state module; the 033/launch/office/file lanes and their pinning tests unchanged; the honesty/dispatch guards' regex extends additively; the launch pointer sentence gains wording (substring-pinned tests survive; re-run pinned in the task list) |
| II. Tests-First | PASS | Never-list matrix + two-phase tool suite specified in Phase 1 and written with the implementation; the full suite must be green |
| III. Minimal Dependencies | PASS | stdlib + already-installed httpx/FastMCP only; no new services (the Windows-side shell tool already exists) |
| IV. Honest Answers | PASS (core) | Echo-and-attest (033's generalized lesson); exact-match structural (stored draft executes); bounded output with truncation named; blocked → verbatim reason; error → real failure text + recovery hint; drafts audited with exact text |
| V. Spec-Driven Replacement | PASS | The lane-scoped supersession (confirmed deletion allowed here) is recorded in the spec's Supersedes; the file lane's code and tests stay untouched |

Post-Phase-1 re-check: no violations introduced; the two-phase design *strengthens* Principle IV (the confirm call carries no command text, removing the drift class entirely).

## Project Structure

### Documentation (this feature)

```text
specs/034-powershell-execution/
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
├── hermes_powershell_gate.py   # NEW — never-list scan + PSVerdict
├── hermes_powershell_state.py  # NEW — conversation-scoped pending command draft
├── hermes_client.py            # MODIFIED — POWERSHELL_INSTRUCTIONS (echo-and-attest, 033's
│                               #   live-proven protocol: exact tool name, USER_CONTROL
│                               #   retry, direct-channel recovery)
├── server.py                   # MODIFIED — hermes_run_powershell tool (draft + confirm phases)
└── hermes_launch_gate.py       # MODIFIED — pointer sentence names both command lanes (append-only)

dify/AGIAssistant/AGI_Assistant.yml   # MODIFIED — hermes_agent instruction (two-phase flow
                                       #   rules), tool entry, honesty/dispatch guards gain the
                                       #   new tool name, launch pointer wording
tests/unit/
├── test_hermes_powershell_gate.py  # NEW — never-list matrix (direct, confirmed, smuggled)
└── test_hermes_powershell_tool.py  # NEW — draft→pending→confirm→execute; confirm-without-
                                     #   pending; echo-mismatch; required identity; audit rows
```

**Structure Decision**: exact mirror of the proven 029/030/033 layout — gate module + state module + client instructions + tool wrapper + two unit suites — so the diff is symmetric with three already-live lanes and reviewers know where everything lives. The genuinely new mechanism is the **stored-draft execution** (the confirm call passes no command text; the agent directive is the stored string), which makes FR-003 structural instead of verified-after-the-fact.

## Complexity Tracking

No Constitution violations to justify. The one new mechanism (stored-draft execution) is small and bought to make the spec's central promise — *what you confirmed is exactly what runs* — impossible to violate rather than merely detected when violated.

## Phases

- **Phase 0 — research.md**: seven design decisions — the two-phase draft/confirm tool (office-email precedent), confirmation semantics (plain affirmative for the exact shown text; modification re-drafts), never-list membership and whole-draft scanning at both phases, prompt-injection containment via the human checkpoint, the agent protocol carried over from 033, audit shape (one row per draft and per execution), and the state-module mirror. No NEEDS CLARIFICATION remains.
- **Phase 1 — design artifacts**: data-model.md (PSVerdict, PendingCommandDraft, AuditEntry, ToolEnvelope), contracts/tool-contract.md (the tool schema + the four envelope shapes + relay rules), quickstart.md (suites + live two-phase run + never-list refusal despite confirmation + audit tail + Stop mid-execution + 033-lane-unchanged check).
- **Next**: `/speckit.tasks` decomposes this plan into the implementation task list.
