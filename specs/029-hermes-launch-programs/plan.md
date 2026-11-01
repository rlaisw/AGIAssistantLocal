# Implementation Plan: Hermes Program Launch Lane — Windows Apps from Chat

**Branch**: `029-hermes-launch-programs` | **Date**: 2026-11-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/029-hermes-launch-programs/spec.md` (+ clarify session 2026-11-01: no allowlist — any executable by name or full path; never launch arguments, never shell phrasing; scripts/shortcuts refused; immediate execution) and the plan input "original plan + create test cases and add error handling" (test strategy R6, error-handling matrix in contracts + quickstart).

## Summary

Add program-launch as a second capability of the Hermes local lane: one new sidecar MCP tool `hermes_launch_app`, gated by a new pure module (`hermes_launch_gate.py`) — any executable identified by **name or full `.exe` path**, never with arguments, never shell/PowerShell phrasing, scripts (.bat/.cmd/.ps1) and shortcuts (.lnk) refused, one target per request, ask-backs for no-target/ambiguity — executed through the existing Hermes gateway client with a launch-specific system prompt, every attempt recorded in the same append-only audit log (`operation="launch-app"`), wired onto the **existing** Hermes agent node (classifier prompt extended, one new tool added). Supersedes spec 028's US3 decline for launches; the file lane stays byte-identical (FR-009).

## Technical Context

**Language/Version**: sidecar Python 3.12 (existing `src/agentic_rag_mcp/`); chatflow DSL (Dify); no frontend changes.

**Primary Dependencies**: Hermes gateway Responses API — `POST /v1/responses` (verified in 028 R1: bearer key, port 8642, `store:false`, stateless) — reached via the existing `hermes_client.run_task`; `httpx` (present). Zero new pip packages.

**Storage**: the existing append-only audit JSONL (`HermesAudit`, default `~/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl`) — launch entries reuse the writer unchanged with `operation="launch-app"`, `allowed_root=""` (no containment root applies to launches).

**Testing**: pytest — failing-first unit suite for the pure launch gate (`tests/unit/test_hermes_launch_gate.py`), tool-wrapper suite with the Hermes client mocked at the trust boundary (`tests/unit/test_hermes_launch_tool.py`, respx); contract: tool schema additive, existing suites green; deploy battery — new `scenario_hermes_launch_app`; classifier routing regression.

**Target Platform**: sidecar container `agentic-rag` (:28080 MCP, Dify allowlist); Hermes gateway on the host (`172.17.0.1:8642`).

**Performance Goals**: launch answer < 60 s end-to-end (SC-001); Hermes call timeout 300 s (existing `hermes_timeout_s`).

**Constraints**: Constitution I — one additive tool, existing 24 tools byte-identical, DSL extends the existing node; II — pure gate module, failing-first tests; III — zero new packages; IV — honest envelopes (ok only on real launch success, blocked/error never fabricated); V — Supersedes record in the spec narrows 028 US3.

**Scale/Scope**: single-user; single in-flight generation (spec 027); sidecar changes ship via `docker cp` hot-patch + source (image rebuild still pending from earlier specs — 028 T021 caveat).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Contract Preservation | PASS | One additive MCP tool (`hermes_launch_app`); existing 24 tool schemas byte-identical; DSL extends the existing Hermes node's tool list and the classifier prompt — no new nodes/branches; file-lane behavior + contracts untouched (FR-009); stream/stop contracts (specs 013/027) unaffected. |
| II. Tests-First | PASS | `hermes_launch_gate.py` is a pure module — failing-first pytest matrix (targets, arguments, shell phrasing, script/shortcut refusal, one-target, ask-backs) written with the tasks; battery scenario written with the tasks. |
| III. Minimal Dependencies | PASS | Zero new packages: reuses `httpx`, `HermesAudit`, `hermes_client.run_task` (gains one instructions constant), `hermes_gate`'s path-normalization helpers unchanged. |
| IV. Honest Answers | PASS | Same honest envelope: `ok` only when the agent reports a real launch, `blocked` with a user-readable reason that never claims execution, `error` with a recovery hint (gateway down / key rejected / timeout / unresolvable target); one audit entry per attempt holds the truth. |
| V. Spec-Driven Replacement | PASS | The spec carries the Supersedes record (028 US3 narrowed to allowlisted-free name/path launches). The 028 decline probes are updated, not silently broken: direct file-tool probes stay blocked (FR-009 defense in depth); chatflow-level "open notepad" flips to launch (FR-010) — mapping documented in the contract. |

Post-Phase-1 re-check: design adds one pure module + one tool + one instructions constant + DSL/battery edits — still PASS on all five.

## Project Structure

### Documentation (this feature)

```text
specs/029-hermes-launch-programs/
├── plan.md                      # This file
├── research.md                  # Phase 0 output (R1-R7)
├── data-model.md                # Phase 1 output
├── quickstart.md                # Phase 1 output (validation guide + V-matrix test cases)
├── contracts/
│   └── hermes-launch-app.md     # MCP tool contract + gate/audit invariants + probe mapping
└── tasks.md                     # Phase 2 (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/agentic_rag_mcp/
├── hermes_launch_gate.py        # NEW: pure launch gate (verb/target extraction, no-args,
│                                #      executables-only, one-target, ask-back verdicts)
├── hermes_client.py             # MODIFIED: adds LAUNCH_INSTRUCTIONS (run_task unchanged)
├── hermes_gate.py               # UNCHANGED — file lane byte-identical (FR-009)
├── hermes_audit.py              # UNCHANGED — launch entries: operation="launch-app", allowed_root=""
├── server.py                    # MODIFIED: hermes_launch_app MCP tool (honest envelopes)
└── deploy/battery.py            # MODIFIED: scenario_hermes_launch_app; B5 keeps file-tool declines

dify/AGIAssistant/AGI_Assistant.yml  # MODIFIED: classifier prompt (launch phrasing),
                                     #   Hermes node: +hermes_launch_app tool, instructions update
tests/unit/test_hermes_launch_gate.py  # NEW: failing-first gate matrix
tests/unit/test_hermes_launch_tool.py  # NEW: tool wrapper (mocked client: ok/blocked/error + audit)
```

**Structure Decision**: single project; the launch gate is one pure module consumed by the tool wrapper — a mirror of the 028 file-lane architecture (gate → audit → client → honest envelope), no new packages, no new Dify node types.
