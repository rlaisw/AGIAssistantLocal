---

description: "Task list for spec 034 — PowerShell Execution Lane (confirmed Windows-MCP shell commands from chat)"

---

# Tasks: PowerShell Execution Lane — Confirmed Windows-MCP Shell Commands from Chat

**Input**: Design documents from `/specs/034-powershell-execution/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/tool-contract.md, quickstart.md

**Tests**: Required — Constitution II (tests-first); the never-list matrix and two-phase tool suite are the feature's primary test surfaces (spec SC-002/SC-003/SC-004).

**Organization**: Tasks are grouped by user story. The never-list gate, state module, and agent instructions are foundational (all stories depend on them); the tool, guard updates, and live-publish work map to their stories.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US5 per spec.md)
- Exact file paths in every description

---

## Phase 1: Setup (Shared Infrastructure)

No setup tasks — the feature extends the existing `agentic_rag_mcp` sidecar package with zero new dependencies (Constitution III); all files it needs are created by the phases below.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The security core and shared machinery — the never-list gate, the pending-draft state, and the agent protocol.

- [x] T001 Write the failing-first never-list suite in `tests/unit/test_hermes_powershell_gate.py`: every never-list class refused with the rule named (per `contracts/tool-contract.md` D3: `format`, `diskpart`, `bcdedit`/`bootcfg`/`bootrec`, `vssadmin … delete`, `reagentc`, `manage-bde … (off|remove)`, `cipher /w`, `Clear-Disk`/`Initialize-Disk`/`Restore-Disk`) — direct, smuggled inside chained operators (`;`/`&&`/`|`), redirection tails, and nested calls (the scan covers the **complete exact draft text**); clean real-PowerShell drafts pass (pipes, `Where-Object`, `Remove-Item`, service/process control are LEGAL on this lane — only system-integrity destruction refuses)
- [x] T002 Implement `src/agentic_rag_mcp/hermes_powershell_gate.py` to green the matrix: `PSVerdict` (`decision`: `ok|blocked`; `reason` naming the matched class on blocked), the closed never-list pattern set in gate code (never a prompt), scan over the whole draft at registration shape
- [x] T003 [P] Implement `src/agentic_rag_mcp/hermes_powershell_state.py`: conversation-scoped pending-draft state mirroring the office lane's pending-email pattern — `set_pending(conversation_id, command)` (one per conversation, new replaces old), `pending(conversation_id)`, `clear(conversation_id)`; in-memory, module-level singleton, ephemeral by design (the audit JSONL is the durable record per `data-model.md`)
- [x] T004 [P] Add `POWERSHELL_INSTRUCTIONS` to `src/agentic_rag_mcp/hermes_client.py`: 033's live-proven protocol generalized — run EXACTLY the directive's command via `mcp__WindowsMCP__PowerShell` (never the WSL `terminal`), retry `USER_CONTROL` patiently (wait ~10 s / the returned wait_seconds), fall back to the direct WindowsMCP SSE channel (`http://127.0.0.1:8800`, the OfficeMCP-style recovery) when the gateway strips arguments, and report `COMMAND:` / `OUTPUT:` / `TASK: COMPLETED` (echo-and-attest; failed → `TASK: FAILED` + reason, never fabricated output)

---

## Phase 3: User Story 1 — Confirmed command execution (P1)

**Story goal**: draft → pending-confirmation → confirm → the stored command executes with real output relayed honestly.
**Independent test**: quickstart Scenario 2 (live round-trip) + the tool suite below.

- [x] T005 [US1] Write the failing-first two-phase tool suite in `tests/unit/test_hermes_powershell_tool.py` (respx at the Hermes boundary, mirroring `tests/unit/test_hermes_run_tool.py`): draft phase → `pending-confirmation` envelope carrying the **exact registered text** and nothing executes; confirm phase (`confirm: true`, no command text) → executes the **stored** draft with real SSE output, `ok` only on stored-draft echo-match + `TASK: COMPLETED`; confirm without pending → `blocked` ask-back; never-list draft → `blocked` **and not stored**; echo mismatch vs the stored draft → `error`, wrong output never relayed; `conversation_id` required (schema rejection, zero audit rows); audit holds one exact-text row per attempt (registration `executed` with outcome = draft text; execution `executed` with bounded output + `duration_s` + `timing`); state cleared after execution; output bounded ~4000 chars with truncation named
- [x] T006 [US1] Implement `hermes_run_powershell` in `src/agentic_rag_mcp/server.py` per `contracts/tool-contract.md`: two phases (draft registers + never-list-scans + stores + audits; confirm executes the stored draft — re-scanned, echo-verified against the **stored** text); the confirm call passes no command text (FR-003 structural); honest envelopes (pending-confirmation / ok / blocked / error with recovery hint); `_await_with_keepalive` + stream path; `HermesAudit` rows with `operation="run-powershell"`
- [x] T007 [US1] Verify offline readiness: `pytest tests/unit/test_hermes_powershell_gate.py tests/unit/test_hermes_powershell_tool.py -q` green; no execution path bypasses the stored-draft flow (blocked drafts never store; unconfirmed drafts never execute)

---

## Phase 4: User Story 2 — Never-list immunity (P1)

**Story goal**: system-integrity destruction refuses even with confirmation; smuggling variants included.
**Independent test**: quickstart Scenario 3 + the immunity matrix.

- [x] T008 [US2] Pin the confirmation-immunity cases across both files: in `tests/unit/test_hermes_powershell_gate.py` — never-list inside pipes/chains/nested calls/redirection (whole-text scan); in `tests/unit/test_hermes_powershell_tool.py` — a never-list draft is refused AND unstored, so a later confirm answers the no-pending ask-back with zero executions anywhere in the sequence
- [x] T009 [US2] Verify the never-list cannot be reached via re-registration: registering a clean draft then confirming with a never-list text in the confirm call must NOT execute anything foreign (the confirm call ignores `draft` and executes only the stored, scanned text — pin this in `tests/unit/test_hermes_powershell_tool.py` per `data-model.md`'s "the confirm call carries no command text")

---

## Phase 5: User Story 3 — Exact-match binding (P1)

**Story goal**: what was confirmed is exactly what runs; drift ends as an honest error with nothing executed.
**Independent test**: the suite's mismatch paths + quickstart Scenario 4.

- [x] T010 [US3] Pin the binding paths in `tests/unit/test_hermes_powershell_tool.py`: agent echoes a command differing from the stored draft → `error` naming the mismatch, output of the wrong command never relayed; a stored draft is replaced only by a NEW registration (supersession), never by confirm-time text; Stop mid-execution → honest cancelled verdict via the shared cancel machinery (required `conversation_id` throughout)

---

## Phase 6: User Story 4 — Safety machinery parity (P2)

**Story goal**: audit, guards, one-command-per-request, and injection containment cover the new lane.
**Independent test**: quickstart Scenario 6 + the guard harness.

- [x] T011 [US4] Extend the guard texts and re-validate: in `dify/AGIAssistant/AGI_Assistant.yml` — the honesty-check `claims` pattern gains `run_powershell` (…` (succeeded|completed|returned|ran)`; the dispatch-leak detector's `hermes_` name match covers the new tool automatically); re-run the node harness (all prior recorded cases unchanged: fabrications block, honest drafts pass, the leaked `<invoke>` dispatch case replaced) and add a case for a leaked `hermes_run_powershell` invocation

---

## Phase 7: User Story 5 — Lane preservation + live publishing (P2)

**Story goal**: the lanes stay distinct and the feature goes live.
**Independent test**: quickstart Scenarios 2–6 live + Postgres graph check.

- [x] T012 [US5] Update `dify/AGIAssistant/AGI_Assistant.yml`: add the `hermes_run_powershell` tool entry to the `hermes_agent` node (description from `contracts/tool-contract.md`); add the two-phase flow rules to the instruction (draft → relay the pending envelope's command VERBATIM and ask; plain affirmative → confirm call; modification → re-draft; silence/new request → drop; never narrate execution without a tool call; one command per request; discovered content is never drafted for execution); extend the launch gate's shell-refusal pointer in `src/agentic_rag_mcp/hermes_launch_gate.py` to name both command lanes (append-only — re-run `pytest tests/unit/test_hermes_launch_gate.py -q` green, substring-pinned tests must pass unchanged)
- [x] T013 [US5] Deploy live: hot-patch the sidecar (gate, state, client, server), run tool sync (28 → 29), publish via the established console cycle (drift-check first), verify via Postgres (graph carries the two-phase rules + tool + guard regex; tool count 29), and run quickstart Scenarios 2–6 live: the confirmation round-trip with a real command (e.g. the services query), the never-list refusal despite confirmation, the modification re-draft, Stop mid-execution, 033/launch lane preservation (`show my ip address` still direct; `open notepad` unchanged), and the guard coverage probe

---

## Phase 8: Polish & Cross-Cutting Concerns

- [x] T014 Run the full python suite `pytest tests/ -q` — all green except the documented pre-existing failures (antv/ppt tool-count contracts, web-research cap, onedrive staleness — proven pre-existing 2026-11-09); run `ruff check` on the new/changed files and fix new findings only
- [x] T015 Add the ops note to `DEPLOY.md`: the PowerShell lane, its confirmation flow, the never-list's code-side enforcement and amendment rule, and the `run-powershell` audit operation
- [ ] T016 Fold the whole lifecycle into the next commit together with the open bug-lifecycle docs and spec 034 artifacts

---

## Dependencies (story completion order)

```text
T001 → T002 ┐
T003 ────────┤ (foundational: matrix, gate, state, protocol)
T004 ────────┤
             ├→ T005 → T006 → T007   (US1 — two-phase tool offline-ready)
             ├→ T008, T009           (US2 — immunity; parallel after T006)
             └→ T010                (US3 — binding; parallel after T006)
US1+US2+US3 → T011                   (US4 — guards + harness)
        T011 → T012 → T013           (US5 — DSL + live publish last)
T013 → T014 → T015 → T016            (polish)
```

## Parallel execution examples

- T003, T004: different files (state module vs client instructions) — parallelize with T001/T002.
- T008/T009 (US2) and T010 (US3): three suite areas, all after T006 — parallelize.
- T012 is single-file DSL work plus one gate text append, but must follow T011 (it publishes their combined state).

## Implementation strategy

MVP = Phase 2 + Phase 3 (T001–T007): the gate, state, protocol, and two-phase tool make the confirmed-execution path work end-to-end offline-testable — the entire feature value. US2/US3 harden and pin the same tool (small, fast), US4 wires the guards, US5 publishes and verifies live, polish closes the lifecycle. Each phase leaves the suite green.

---

## Phase 9: Convergence

- [x] T017 Align the pending-draft lifecycle with cancelled confirm turns and fix the DEPLOY.md overclaim per spec Edge Cases + DEPLOY.md:423 (contradicts) — `src/agentic_rag_mcp/server.py`: on a cancelled confirm turn (the `outcome` error branch whose reason is the turn-cancel class, i.e. ReadError "turn was cancelled"), `ps_state.clear(conversation_id)` so a later confirm cannot re-execute a stopped draft; decide + document whether non-cancel failed confirms (USER_CONTROL/transport) keep the draft re-confirmable (current live-proven behavior) and correct DEPLOY.md:423's "a failed execution clears the pending draft" to match; add `tests/unit/test_hermes_powershell_tool.py` cases pinning: cancel-class confirm error → pending cleared; other confirm errors → pending kept
- [x] T018 Collect the SC-001 live measurement per spec SC-001 (partial) — in an idle-machine window, run four fresh-conversation draft→confirm→relay round-trips (e.g. the services query), record first-attempt completions (target ≥3 of 4), and note the result in the spec's Clarifications or the DEPLOY.md ops row
