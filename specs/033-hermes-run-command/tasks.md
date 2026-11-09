---

description: "Task list for spec 033 — Hermes Run-Command Lane (allowlisted Windows diagnostics from chat)"

---

# Tasks: Hermes Run-Command Lane — Allowlisted Windows Diagnostics from Chat

**Input**: Design documents from `/specs/033-hermes-run-command/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/tool-contract.md, quickstart.md

**Tests**: Required — Constitution II (tests-first): every non-trivial behavior lands with its runnable check; the gate matrix and tool-envelope suites are the feature's primary test surface (spec SC-002/SC-003).

**Organization**: Tasks are grouped by user story. The gate module and its matrix are foundational (both P1 stories depend on them); the tool, DSL, and live-publish work map to their stories.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US4 per spec.md)
- Exact file paths in every description

---

## Phase 1: Setup (Shared Infrastructure)

No setup tasks — the feature extends the existing `agentic_rag_mcp` sidecar package with zero new dependencies (Constitution III); all files it needs are created by the phases below.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The security core both P1 stories depend on — the allowlist gate, its matrix, and the agent protocol.

- [x] T001 Write the failing-first gate matrix in `tests/unit/test_hermes_run_gate.py`: intent mapping (*"show my (current) IP address"*→`ipconfig`, *"what's running"*→`tasklist`, *"system info"*→`systeminfo`, *"host name"*→`hostname`, *"who am i"*→`whoami`, literal command names) and the full refusal matrix (cmdlets like `Get-NetIPAddress`, destructive verbs `del`/`format`/`shutdown`/`reg`/`netsh`, flags (`tasklist /v`), pipes (`ipconfig | clip`), separators (`ping 8.8.8.8 && shutdown`), redirection, quoting smuggles, two commands → ask-back, unmapped request → ask-back offering the list); every blocked reason must show the allowlist verbatim per `contracts/tool-contract.md`
- [x] T002 Implement `src/agentic_rag_mcp/hermes_run_gate.py` to green the matrix: `AllowlistEntry` constants (bare: `ipconfig`, `systeminfo`, `tasklist`, `whoami`, `hostname`; single-target: `ping`, `nslookup`, `tracert`), fixed intent-phrase synonym table, `CommandVerdict` (`decision`: `ok|blocked|ask-back`; `command`; `target`; `reason`) — validation per `data-model.md`: target charset `[A-Za-z0-9.-]` single token only, one command per request, gate never guesses and never passes raw user text through
- [x] T003 [P] Add `RUN_COMMAND_INSTRUCTIONS` to `src/agentic_rag_mcp/hermes_client.py`: the echo-and-attest agent prompt — run EXACTLY the directive's one command, nothing else, no modifications; report `COMMAND: <exact command>`, the complete output in an `OUTPUT:` block, and end with `TASK: COMPLETED`; never run anything not stated in the directive

---

## Phase 3: User Story 1 — Real diagnostics answers (P1)

**Story goal**: *"show my Windows current IP address"* returns the machine's real answer, honestly, audited, timed, cancellable.
**Independent test**: quickstart Scenario 2 (live IP matches the desktop's real `ipconfig`) + the tool suite below.

- [x] T004 [US1] Write the failing-first tool suite in `tests/unit/test_hermes_run_tool.py` (respx at the Hermes boundary, mirroring `tests/unit/test_hermes_launch_tool.py`): `hermes_run_command` exists on the server; a call without `conversation_id` is **rejected by the tool schema** (FR-006 required parameter); blocked → one audit row (`operation="run-command"`, verbatim reason) and nothing reaches Hermes; `ok` stamped ONLY when the agent echoes the gated command (`COMMAND:` marker, normalized match) AND attests `TASK: COMPLETED` — missing or mismatched markers → `error`, never a fabricated success (FR-005); ok/error envelopes carry the `timing` profile; output bounded (~4000 chars) with truncation named when cut
- [x] T005 [US1] Implement `hermes_run_command` in `src/agentic_rag_mcp/server.py`: register the tool with `conversation_id` as a required parameter; gate first (blocked → audit + envelope, zero agent contact); directive built from `CommandVerdict.command`/`.target` + `RUN_COMMAND_INSTRUCTIONS`; execute via the shared stream path (`_await_with_keepalive` + `_run_hermes`, default budget like the office lane); parse the echo/attestation markers and verify the echoed command matches the gated directive before stamping `ok`; honest envelope shapes per `contracts/tool-contract.md`; exactly one `HermesAudit.write_attempt` per attempt (`operation="run-command"`, `duration_s` + `timing` on executed/error)
- [x] T006 [US1] Verify Scenario-2 readiness offline: full gate + tool suites green with `pytest tests/unit/test_hermes_run_gate.py tests/unit/test_hermes_run_tool.py -q`; no execution path exists that bypasses the gate (blocked turns show zero Hermes calls in the respx router)

---

## Phase 4: User Story 2 — Everything outside the allowlist is refused (P1)

**Story goal**: the refusal matrix is 100% refused with the list shown and zero execution, and users are pointed from the launch lane to this lane.
**Independent test**: quickstart Scenario 3 + the launch-gate suite staying green.

- [x] T007 [US2] Append the pointer sentence to the shell-refusal message in `src/agentic_rag_mcp/hermes_launch_gate.py` (keep every pinned phrase — add only: for read-only diagnostics, ask for an allowed command like `ipconfig` or `ping <host>`, which the run-command lane serves); re-run `pytest tests/unit/test_hermes_launch_gate.py -q` green (substring-pinned tests must pass unchanged — Constitution I)
- [x] T008 [US2] Confirm the destructive-verb and smuggle cases are pinned in the gate matrix (`tests/unit/test_hermes_run_gate.py`): `del`, `format`, `shutdown`, `reg`, `netsh`, `sc`, `Remove-Item`, backtick/quote smuggles, and the "allowed + refused mixed prompt" case (refused part never executes, refusal reported) — add any missing cases to the matrix before the live phase

---

## Phase 5: User Story 3 — Targeted diagnostics with one host argument (P2)

**Story goal**: `ping 8.8.8.8` / `nslookup google.com` run with exactly one strict-charset target; anything else is refused.
**Independent test**: quickstart Scenario 3's charset cases + the targeted-command matrix.

- [x] T009 [US3] Pin the targeted-command parsing in `tests/unit/test_hermes_run_gate.py`: accept single tokens `8.8.8.8`, `google.com`, `my-host.example-1.com`; reject `8.8.8.8 -l 65500`, `a b`, `a;b`, quoted or backticked targets, targets with slashes/spaces/metacharacters — refusal names the single-simple-target rule per `data-model.md` (charset quoted in the task: `[A-Za-z0-9.-]`, one token)

---

## Phase 6: User Story 4 — Honesty machinery + live publishing (P2)

**Story goal**: the lane joins the honesty contract end-to-end and goes live.
**Independent test**: quickstart Scenarios 4–5 (audit tail one-row-per-turn, Stop mid-ping, near-repeat fabrication guard) + the Postgres graph check.

- [x] T010 [US4] Update `dify/AGIAssistant/AGI_Assistant.yml`: add the run-command routing bullets to the `hermes_agent` instruction (route system-state/diagnostics requests — including "powershell"-phrased ones that map to a listed command — to `hermes_run_command`, pass `conversation_id` exactly as `'{{#sys.conversation_id#}}'`, relay verdicts honestly, one command per request, refusal verbatim with the list); add `hermes_run_command` to the `honesty_check` node's `claims` regex (`hermes_(launch_app|office_task|file_task|cancel_turn)` gains `run_command`); extend the hermes classifier class topic with diagnostics phrasing (*"show my IP address"*, *"run a diagnostic command"*)
- [x] T011 [US4] Deploy live: hot-patch/rebuild the sidecar with the new code, run the MCP tool sync (27 → 28 tools), publish the chatflow via the established console cycle (sync-check live == HEAD first, then `update_workflow_draft` + `publish`), and verify: Postgres graph carries the new instruction/regex text, tool count 28, and quickstart Scenarios 2–5 pass live (real IP probe, refusal matrix, audit tail with `operation="run-command"` rows, Stop mid-`ping` honest cancel, near-repeat probe still places a real tool call)

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T012 Run the full python suite `pytest tests/ -q` — all green except the documented pre-existing failures (antv/ppt tool-count contracts, web-research cap, onedrive staleness — unrelated, proven pre-existing 2026-11-09); run `ruff check` on the new/changed files and fix new findings only
- [ ] T013 Add the ops note to `DEPLOY.md`: the run-command lane, its audit operation (`run-command`), and that the allowlist is code-side (extended only by spec amendment)
- [ ] T014 Fold the whole lifecycle into the next commit together with the open bug-lifecycle docs (spec 033 artifacts + gate/tool/instructions/DSL changes + suites)

---

## Dependencies (story completion order)

```text
T001 → T002 ┐
T003 ────────┤ (foundational: matrix, gate, protocol)
             ├→ T004 → T005 → T006   (US1 — tool live-ready)
             ├→ T007, T008           (US2 — refusals + pointer; parallel to US1 after T002)
             └→ T009                (US3 — charset matrix; parallel to US1/US2 after T002)
US1 + US2 + US3 → T010 → T011        (US4 — DSL + live publish last)
T011 → T012 → T013 → T014            (polish)
```

## Parallel execution examples

- T001, T003: different files (tests vs `hermes_client.py`) — parallelize.
- T007/T008 (US2) and T009 (US3) after T002: three different files/areas — parallelize.
- T010 is single-file DSL work but must follow all story phases (it publishes their combined state).

## Implementation strategy

MVP = Phase 2 + Phase 3 (T001–T006): the gate, protocol, and tool make *"show my IP address"* work end-to-end offline-testable — the entire feature value. US2/US3 harden and pin the same gate (small, fast), US4 makes it live and honest at the relay layer, polish closes the lifecycle. Each phase leaves the suite green.
