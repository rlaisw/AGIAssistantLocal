---
description: "Task list for Hermes Office Task Lane (feature 030)"
---

# Tasks: Hermes Office Task Lane — Prompt-Driven Office Execution

**Input**: Design documents from `/specs/030-hermes-office-tasks/`

**Prerequisites**: plan.md ✓, spec.md ✓ (4 user stories, P1×3 + P2×1), research.md ✓ (R1–R9, live-probed), data-model.md ✓, contracts/hermes-office-task.md ✓, quickstart.md ✓

**Tests**: Requested at plan time ("original plan + create test cases and add error handling") and mandated by Constitution II — three failing-first unit suites; battery O-matrix as the live gate.

**Organization**: Grouped by user story (US1 P1 Excel write, US2 P1 Outlook compose/confirm/send, US3 P1 refusals + honest failures, US4 P2 Word/PowerPoint parity). Stories share the gate + state + tool, so the build is foundational-then-lanes (029 pattern).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story the task belongs to
- Exact file paths in every description

## Path Conventions

Sidecar Python at repo root: `src/agentic_rag_mcp/`, tests in `tests/unit/`, battery in `src/agentic_rag_mcp/deploy/battery.py`, DSL artifact `dify/AGIAssistant/AGI_Assistant.yml`.

---

## Phase 1: Setup

**Purpose**: Host wiring (probe-verified architecture, research R9) + the one config knob — everything else rides on specs 028/029 infrastructure.

- [x] T001 Wire and verify the OfficeMCP bridge on the host per research R9/quickstart §Prerequisites: ensure the Windows service is reachable at `http://127.0.0.1:8888` (if not running, start it with the owner's command — `officemcp sse --port 8888 --host 127.0.0.1 --folder C:\OfficeMCP`, runnable via WSL interop or by the owner), then `hermes mcp add OfficeMCP --url http://127.0.0.1:8888/sse` and `hermes mcp test OfficeMCP` (confirm the exact SSE endpoint path — `/sse` vs `/mcp`); record the working commands in `specs/030-hermes-office-tasks/quickstart.md`
- [x] T002 Add the `hermes_office_root` config field to `src/agentic_rag_mcp/config.py` — default `"C:\\OfficeMCP"` (Windows-style string: the gate's containment root and the audit `allowed_root`; no URL fields — the bridge lives in `hermes mcp`, not the sidecar, per research R7)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The pure gate + conversation state + instructions + the tool wrapper — every story consumes these. Tests-first (Constitution II).

**⚠️ CRITICAL**: No lane work begins until this phase is green.

- [x] T003 [P] Write the failing-first gate suite `tests/unit/test_office_gate.py` from contract §2 / research R8: task-kind classification (document-write / document-read / compose-email / send-confirmation / cancel / continue), app classification (excel/word/powerpoint/outlook), work-folder containment (paths inside `C:\OfficeMCP` ok; `C:\Other\…` blocked naming the root), prompt-borne code-execution vectors (macro/script/DDE/external-link-formula requests blocked with the rule named), recipient rules (address-less compose → ask-back, never guessed), confirmation classification (send/cancel words), reason strings. Suite MUST fail (module absent)
- [x] T004 [P] Write the failing-first state suite `tests/unit/test_office_state.py` per data-model §PendingDraft/§ActiveDocument: active-document set/switch, follow-up resolution, pending-draft lifecycle (create → confirm/cancel/replace, lives until resolved, never deleted), conversation isolation (separate ids see separate state), restart-loss semantics. Suite MUST fail (module absent)
- [x] T005 [P] Write the failing-first tool suite `tests/unit/test_hermes_office_tool.py` with the Hermes client mocked per contract §3–§4: gate-blocked verdicts never call the agent and audit refusals (`operation="office-task"`, `allowed_root` = the work folder); STEP/TASK marker parsing → per-step audit entries; envelope `ok` only on `TASK: COMPLETED`; `PARTIAL`/`FAILED` → honest envelopes naming the failing step; confirm turn sends the recorded EntryID (directive contains it, envelope `ok`); compose returns `draft_pending: true` and never sends; service-down → `error` with the exact `officemcp sse …` start hint; `active_file` propagation. Suite MUST fail (tool absent)
- [x] T006 Implement `src/agentic_rag_mcp/office_gate.py` until T003 is green: pure module per contract §2 in order (classify kind/app → work-folder containment → code-exec vectors → recipient rules → confirmation/cancel classification), reusing the file lane's path-normalization semantics, outputting the gate verdict with user-readable reasons
- [x] T007 Implement `src/agentic_rag_mcp/office_state.py` until T004 is green: in-memory, thread-safe, conversation-keyed state holding `ActiveDocument` and `PendingDraft` per data-model (pending draft stores the COM EntryID + the displayed recipient/subject/body; dropped drafts are never deleted)
- [x] T008 Add `OFFICE_INSTRUCTIONS` to `src/agentic_rag_mcp/hermes_client.py` per research R3/R6 + contract §3: allowed tools (Launch, RunPython for steps, availability/file queries, Visible(true)); forbidden for lane tasks (Quit, ScreenShot, Speak, Beep, DownloadImage, Demonstrate); work-folder-only files; literal content only (no formulas/macros/DDE stored); never send email unless the directive says `SEND PENDING DRAFT <entryID> exactly as composed`; step protocol — end each step with `STEP <n>: <operation> OK/FAILED — <detail>`, report `ACTIVE FILE: <windows-path>` and `DRAFT ID: <entryID>`, end with exactly `TASK: COMPLETED/PARTIAL/FAILED`; leave the app open. `run_task` signature unchanged
- [x] T009 Wire the MCP tool `hermes_office_task(task: str, conversation_id: str)` in `src/agentic_rag_mcp/server.py` until T005 is green per contract §1–§4: gate → state-resolve (confirm/cancel against PendingDraft) → agent call via `run_task` with `OFFICE_INSTRUCTIONS` + per-task directive → parse STEP/ACTIVE FILE/DRAFT ID/TASK markers → one audit entry per step → envelope (`ok` only on COMPLETED; `draft_pending`, `active_file`) → update state. Docstring = the DSL-synced tool_description per contract §7

**Checkpoint**: `pytest tests/unit/test_office_gate.py tests/unit/test_office_state.py tests/unit/test_hermes_office_tool.py` green; existing suites still green; the tool callable in-process.

---

## Phase 3: User Story 1 — "open Excel, input 12345 at cell A1" (Priority: P1) 🎯 MVP

**Goal**: one prompt writes the cell end-to-end — workbook in `C:\OfficeMCP`, A1 verifiable, Excel left open, honest step reports, active-document follow-ups work.

**Independent Test**: quickstart §3 O1/O2 via the battery + the manual chat check.

### Tests for User Story 1

- [x] T010 [P] [US1] Add the `scenario_hermes_office_task` battery scenario to `src/agentic_rag_mcp/deploy/battery.py` (O1: "open Excel and put 12345 in cell A1" via `mcp_call("hermes_office_task", {"task": …, "conversation_id": "battery-office"})` → `ok` + `TASK: COMPLETED` + verify the workbook's A1 via stdlib `zipfile`+sheet XML under `C:\OfficeMCP` — zero new deps; O2: follow-up "also write 'hello' in B2" with the SAME conversation id → same active workbook, B2 verified; O7 audit cross-check: one truthful entry per step, `operation="office-task"`) and register it after `hermes-launch-app`

### Implementation for User Story 1

- [x] T011 [US1] DSL `dify/AGIAssistant/AGI_Assistant.yml`: classifier topic/instruction gain Office-control phrasing ("open/edit/write Word/Excel/PowerPoint/Outlook documents, cells, slides, emails" — launch-only prompts stay launch-lane); the Hermes Local Agent node gains the `hermes_office_task` tool with its `conversation_id` parameter bound to `{{#sys.conversation_id#}}` and tool_description synced from the server docstring; node instructions add the office rules additively (file/launch rules verbatim; relay drafts verbatim; never send without user confirmation)
- [x] T012 [US1] Hot-patch the sidecar (`docker cp` the changed `office_gate.py`/`office_state.py`/`hermes_client.py`/`server.py`/`config.py` + restart), sync the Dify tool cache (25→26), `deploy chatflow` — **publish to the app that owns the chat key** (the duplicate-app gotcha, DEPLOY.md row), then run T010 live and the manual chat check; record outcomes in `specs/030-hermes-office-tasks/quickstart.md`

**Checkpoint**: MVP — chat writes real Excel cells end-to-end with active-document follow-ups.

---

## Phase 4: User Story 2 — Outlook compose → confirm → send (Priority: P1)

**Goal**: the owner's email example under confirm-before-send — compose shows the draft verbatim and nothing sends until the user's chat confirmation sends the recorded EntryID exactly.

**Independent Test**: quickstart §3 O3–O5 + manual §4.

### Tests for User Story 2

- [x] T013 [P] [US2] Extend `scenario_hermes_office_task` in `src/agentic_rag_mcp/deploy/battery.py`: O3 compose ("write an email to a@b.com with subject/body …" → envelope `draft_pending: true`, draft shown verbatim, `DRAFT ID` recorded, nothing sent); O4 confirm ("send it", same conversation id → the recorded EntryID sends, `ok`, audit executed); O5 cancel (compose → "cancel that email" → draft dropped-not-deleted, `draft_pending` false)

### Implementation for User Story 2

- [x] T014 [US2] Live run of O3–O5 plus a manual conversation: compose → check the draft exists in Outlook's Drafts folder (agent report + visible in Outlook) → confirm turn → message in Sent Items; verify the audit shows composed/confirmed/sent truthfully; record in `specs/030-hermes-office-tasks/quickstart.md` §4

**Checkpoint**: outbound email is confirmation-gated end-to-end.

---

## Phase 5: User Story 3 — Refusals and honest failures (Priority: P1)

**Goal**: 100% of the refusal matrix is gate-blocked with named rules and zero executions; every failure mode answers honestly with recovery hints.

**Independent Test**: quickstart §3 O6 + §5 error checks.

### Tests for User Story 3

- [x] T015 [P] [US3] Extend `scenario_hermes_office_task` in `src/agentic_rag_mcp/deploy/battery.py` with O6 (refusal matrix: macro request, DDE/external-link formula, out-of-folder path, address-less compose, "delete my emails" → all `blocked` at the gate, zero executions, audit refusals) and the service-down probe (stop the OfficeMCP service → Office task → honest `error` carrying the exact `officemcp sse …` start hint → restart → recovers), mirroring 029's gateway-down probe

### Implementation for User Story 3

- [x] T016 [US3] Harden the Hermes node instructions in `dify/AGIAssistant/AGI_Assistant.yml`: relay pending-draft state and drafts verbatim in every answer; never re-attempt a blocked task with rephrased content (anti-smuggling); never treat silence as consent; republish via `deploy chatflow`
- [x] T017 [US3] Run the full O-matrix live including the error probes (service down, step-failure partial via a deliberately impossible step, turn-budget resume if reachable); record outcomes in `specs/030-hermes-office-tasks/quickstart.md` §5

**Checkpoint**: the security story is evidence-backed.

---

## Phase 6: User Story 4 — Word and PowerPoint parity (Priority: P2)

**Goal**: the same pattern delivers Word documents and PowerPoint slides — containment, literal content, honest steps, same refusals.

**Independent Test**: quickstart §3 W1/P1 probes.

### Tests for User Story 4

- [x] T018 [P] [US4] Extend `scenario_hermes_office_task` in `src/agentic_rag_mcp/deploy/battery.py`: W1 (create a Word document with dictated text → verify the docx XML via stdlib `zipfile` under the work folder); P1 (add a slide with dictated text → pptx slide XML check); the same refusal matrix applied to Word/PowerPoint targets

### Implementation for User Story 4

- [x] T019 [US4] Live checks via chat: Word create + PowerPoint slide; a mixed-lane prompt (an Office task + a launch/file part, each handled by its own tool, all verdicts reported); a formatting request gets the honest out-of-scope notice; record in `specs/030-hermes-office-tasks/quickstart.md`

**Checkpoint**: the four-app promise is delivered.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T020 [P] Docs sync: root `AGENTS.md` Hermes-lane feature-surface line (third lane: Office tasks, work-folder containment, confirm-before-send, audited); `DEPLOY.md` tool-count 25→26 + office prerequisite (service start command, `hermes mcp add` wiring) + troubleshooting rows (service down → start hint; tasks misrouted → the duplicate-app publish rule already documented); `README.md` office-lane section
- [x] T021 Full green sweep: `pytest tests/unit tests/integration tests/contract -q` (amend snapshot tests to the 26-tool/14-scenario surface — antv/ppt `EXISTING_TOOLS`, `CONTRACT_SCENARIOS`), `pnpm typecheck && pnpm lint && pnpm test` in `ai-chat-landing/` (untouched — must stay green), full battery live; update `specs/030-hermes-office-tasks/quickstart.md` with the recorded final O-matrix
- [ ] T022 [P] Commit (only on the owner's explicit go-ahead): source + DSL + battery + spec artifacts; audit log and user data stay out; note the hot-patch-vs-image-rebuild state in the commit message

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1**: T001 blocks all live tasks (not the code); T002 blocks Phase 2's gate (containment root)
- **Phase 2**: blocks ALL lane work; tests first — T003/T004/T005 parallel (different files), then T006 after T003, T007 after T004, T008 independent, T009 after T005–T008
- **Phases 3–6**: sequential recommended (single DSL file — never two DSL tasks in flight); battery tasks [P] alongside the DSL pair within each phase
- **Phase 7**: last; T022 additionally requires the owner's explicit go-ahead

### User Story Dependencies

- US1 (P1): after Phase 2 — no story deps. **MVP = Phases 1–3.**
- US2 (P1): builds on US1's node/battery (T013 extends T010's scenario; the confirm flow needs the pending-draft state proven in Phase 2)
- US3 (P1): extends the same scenario and node (T015 after T013's compose state exists; T016 hardens T011's instructions)
- US4 (P2): same pattern, new targets (T018/T019 after the O-matrix)

### Within Each User Story

- Battery-test task [P] before/alongside the DSL edit; DSL + republish + hot-patch + live run; record; next story.

### Parallel Opportunities

- Phase 2: T003 ∥ T004 ∥ T005 (three test files); then T006 ∥ T007 ∥ T008 (three source files)
- Phases 3–6: the battery task [P] runs alongside the DSL task of its phase
- Phase 7: T020 ∥ T021 prep

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 (bridge + config) → 2. Phase 2 (gate/state/instructions/tool green) → 3. Phase 3 (DSL + battery O1/O2 + live) → 4. **STOP and VALIDATE**: "open Excel, put 12345 in cell A1" from chat → A1 verified in the workbook, Excel open on the desktop, follow-up B2 on the same workbook.

### Incremental Delivery

1. MVP (US1) → 2. US2 email flow → 3. US3 refusals/failures → 4. US4 Word/PPT parity → 5. Polish/docs/commit. Each story keeps the previous green (battery re-run per phase).

---

## Notes

- [P] = different files, no dependencies on incomplete tasks
- The DSL (`dify/AGIAssistant/AGI_Assistant.yml`) is a single YAML file — never two DSL tasks in flight together
- Publish to the Dify app that owns the chat API key (the two-app gotcha hit 029; DEPLOY.md row) and re-sync the provider tool cache after hot-patching (db-resync now supports Dify 1.18)
- The bridge is host configuration, never repo code: `hermes mcp add/list/test` — research R2; the sidecar never talks to OfficeMCP
- The audit discriminator for office entries is `operation="office-task"` + `allowed_root` = the work folder (the 029 L9 lesson: filter by the lane's real discriminators)
- Battery multi-turn state: the battery passes `conversation_id` itself, so O2/O4/O5 test the conversation state deterministically
- 028/029 regression: their suites and battery probes stay byte-identical; B5/launch probes unchanged
- The owner starts and owns the Windows-side OfficeMCP service; the lane's honest down-error carries the exact start command
- Commit only when the owner says so (T022)

---

## Phase 8: Convergence

- [x] T023 Implement the turn-budget resume path per FR-005 / clarify pass 2 (partial) — add remaining-steps state to `src/agentic_rag_mcp/office_state.py` (per conversation), return `OP_CONTINUE` from `src/agentic_rag_mcp/office_gate.py` for resume phrases, and resolve a "continue" in `src/agentic_rag_mcp/server.py` into a resume directive replaying the unexecuted steps; extend `tests/unit/test_office_state.py` + `tests/unit/test_hermes_office_tool.py` with failing-first resume cases (stop → continue → remaining steps execute; continue with nothing pending asks back honestly)
- [x] T024 Run the full 14-scenario deploy battery green end-to-end post-030 per SC-004/T021 (partial) — `.venv/bin/python -m agentic_rag_mcp.deploy verify` all green (the office O-matrix passed standalone; the whole battery must pass as one run) and record the result in `specs/030-hermes-office-tasks/quickstart.md` §Recorded outcomes
- [x] T025 Add a mixed-lane probe for combined Office + file/launch prompts per spec Edge Cases (missing) — one battery case or unit-level assertion that a prompt combining an Office task with a file/launch part yields each lane's own verdict, all reported honestly (mirrors 029's convergence T019)
