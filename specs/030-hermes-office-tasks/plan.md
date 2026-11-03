# Implementation Plan: Hermes Office Task Lane — Prompt-Driven Office Execution

**Branch**: `030-hermes-office-tasks` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/030-hermes-office-tasks/spec.md` (+ clarify passes 1–2: confirm-before-send; pending draft lives until resolved; conversation-scoped active document; no step cap with honest resume; literal content only; apps left open) and the plan input "original plan + create test cases and add error handling" (test strategy R8, error matrix in contract + quickstart).

## Summary

Prompt-driven Office execution as the third Hermes lane: one new sidecar MCP tool `hermes_office_task(task, conversation_id)` gated by a new pure module (`office_gate.py`) and holding conversation state (`office_state.py`: PendingDraft + ActiveDocument) — Excel/Word/PowerPoint/Outlook tasks as bounded step sequences, confined to the Office work folder (default `C:\OfficeMCP`), literal content only, email compose-then-confirm-then-send. The **bridge is agent-native**: the Hermes gateway's built-in MCP client (`hermes mcp add OfficeMCP --url http://127.0.0.1:8888/sse` — mirrored-network loopback, probe-verified) gives the local agent OfficeMCP's tools; the sidecar never talks to OfficeMCP directly. The sidecar keeps everything that makes the lane trustworthy: task gate, conversation state, per-step audit, honest envelope (STEP/TASK marker protocol, the 029 LAUNCH-marker pattern extended), and the confirm-before-send flow (COM EntryID as the pending-draft handle). Wired onto the existing Hermes Local Agent node (classifier phrasing + one tool + office rules), `conversation_id` bound from the Dify sys variable. Supersedes 029's exclusion narrowly (typed Office operations on four apps); file and launch lanes stay byte-identical.

## Technical Context

**Language/Version**: sidecar Python 3.12 (`src/agentic_rag_mcp/`); chatflow DSL (Dify); no frontend changes. Office-side executor: owner-installed OfficeMCP v1.0.5 (Windows, uv tool) + its COM engine — host state, not a repo dependency.

**Primary Dependencies**: Hermes gateway Responses API via `hermes_client.run_task` with a new `OFFICE_INSTRUCTIONS` system prompt; the gateway's native MCP client (`hermes mcp add/list/test`, probe-verified) as the OfficeMCP bridge. Zero new pip packages; xlsx verification in the battery uses stdlib `zipfile`+XML (no openpyxl).

**Storage**: the append-only audit JSONL (per-step entries, `operation="office-task"`, `allowed_root` = the Office work folder — the lane's audit discriminator); conversation state in-memory in the sidecar, keyed by conversation id (documented loss-on-restart → honest ask-back).

**Testing**: pytest — failing-first `office_gate` matrix, `office_state` lifecycle, tool wrapper with the client mocked (step parsing, confirm flow, error mapping); contract: additive 26th tool, existing suites green; battery — new `scenario_hermes_office_task` O-matrix incl. multi-turn state checks (the battery passes conversation_id itself).

**Target Platform**: sidecar container `agentic-rag` (:28080); Hermes gateway on the WSL host (172.17.0.1:8642); OfficeMCP SSE on the Windows side (127.0.0.1:8888, mirrored loopback — probe-verified networking mode `mirrored`).

**Performance Goals**: per-step and task verdicts within the Hermes call timeout (300 s default — the 029-measured agent-turn reality); no artificial step cap (owner decision): budget exhaustion stops at the last completed step with an honest resume.

**Constraints**: Constitution I — one additive tool, existing 25 schemas byte-identical, existing node extended (no new Dify nodes); II — pure gate/state modules, failing-first; III — zero new packages; IV — step-level honest envelope (STEP/TASK markers), confirm-before-send, per-step audit; V — Supersedes record in the spec narrows 029's exclusion to typed Office operations.

**Scale/Scope**: single-user; one conversation's state independent of others; OfficeMCP server bound to loopback only (single-machine trust).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Contract Preservation | PASS | One additive MCP tool (`hermes_office_task`, 25→26); existing schemas byte-identical; DSL extends the existing Hermes Local Agent node (tool + conversation_id binding + office rules in instructions) and the classifier phrasing — no new nodes/edges; file and launch lanes untouched (FR-012). |
| II. Tests-First | PASS | `office_gate.py`/`office_state.py` are pure — failing-first pytest matrix (policy, containment, recipient rules, confirm classification, state lifecycle) written with the tasks; battery scenario written with the tasks. |
| III. Minimal Dependencies | PASS | Zero new pip packages. OfficeMCP is owner-installed host state (like the Hermes gateway itself), reached through the gateway's existing MCP client. |
| IV. Honest Answers | PASS | Step-level honesty: the agent must end each step with `STEP <n>: <op> OK/FAILED` and the task with `TASK: COMPLETED/PARTIAL/FAILED`; the sidecar parses, audits one entry per step, and stamps `ok` only on COMPLETED. Confirm-before-send: `ok` for a send requires the user's explicit chat confirmation resolved against the recorded pending draft. |
| V. Spec-Driven Replacement | PASS | The spec carries the Supersedes record (029's exclusion narrowed to typed Office operations on four apps; GUI automation of arbitrary apps stays out). |

Post-Phase-1 re-check: research R3 surfaced that OfficeMCP's execution mechanism is a host-side Python REPL over COM (`RunPython`), not typed operations — the design answers with instruction-level tool rules, prompt-level gate bans, and per-step audit; the spec's FR-004 (prompt-borne executable content) still holds as written and is enforced at the instruction + report layer. Still PASS on all five.

## Project Structure

### Documentation (this feature)

```text
specs/030-hermes-office-tasks/
├── plan.md                      # This file
├── research.md                  # Phase 0 output (R1–R9, live-probe evidence)
├── data-model.md                # Phase 1 output
├── quickstart.md                # Phase 1 output (validation guide + O-matrix)
├── contracts/
│   └── hermes-office-task.md    # MCP tool contract + gate/state/step invariants + host wiring
└── tasks.md                     # Phase 2 (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/agentic_rag_mcp/
├── office_gate.py               # NEW: pure task gate (app/kind classification, work-folder
│                                #      containment, code-exec vectors, recipient rules,
│                                #      confirmation/cancel classification)
├── office_state.py              # NEW: conversation state (PendingDraft, ActiveDocument),
│                                #      in-memory, keyed by conversation id
├── hermes_client.py             # MODIFIED: adds OFFICE_INSTRUCTIONS (run_task unchanged)
├── server.py                    # MODIFIED: hermes_office_task MCP tool (gate → state →
│                                #      agent call → step parse → audit → envelope)
├── config.py                    # MODIFIED: one field — hermes_office_root ("C:\\OfficeMCP")
├── hermes_gate.py / hermes_launch_gate.py / hermes_audit.py   # UNCHANGED
└── deploy/battery.py            # MODIFIED: scenario_hermes_office_task (O-matrix) + registry

dify/AGIAssistant/AGI_Assistant.yml  # MODIFIED: classifier phrasing (+Office control), Hermes
                                      #   node: +hermes_office_task with conversation_id bound to
                                      #   {{#sys.conversation_id#}}, office rules in instructions
tests/unit/test_office_gate.py        # NEW: failing-first gate matrix
tests/unit/test_office_state.py      # NEW: state lifecycle
tests/unit/test_hermes_office_tool.py # NEW: tool wrapper (mocked client: steps, confirm, errors)
```

**Structure Decision**: the bridge is configuration on the host (`hermes mcp add`, research R2) — no bridge code in the repo; the sidecar owns gate, state, and audit; the agent owns execution. The 028/029 layering (pure gate → stateful broker → stateless agent call → marker-parsed honest envelope) is preserved with the office lane as its third instance.
