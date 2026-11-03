---
description: "Task list for Office Save Anywhere (feature 031)"
---

# Tasks: Office Save Anywhere — user-named save locations on any folder

**Input**: Design documents from `/specs/031-office-save-anywhere/`

**Prerequisites**: plan.md ✓, spec.md ✓ (3 user stories, all P1), research.md ✓ (R1–R5), data-model.md ✓, contracts/hermes-office-save-anywhere.md ✓ (delta against 030), quickstart.md ✓

**Tests**: Requested at plan time ("original plan + create test cases and add error handling") and mandated by Constitution II — failing-first gate/tool amendments; the battery probe as the live gate.

**Organization**: Grouped by user story (US1 P1 save-anywhere, US2 P1 overwrite honesty, US3 P1 everything-else-unchanged). All three stories share the gate amendment — the build is foundational-then-stories (the 029/030 pattern).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story the task belongs to
- Exact file paths in every description

## Path Conventions

Sidecar Python at repo root: `src/agentic_rag_mcp/`, tests in `tests/unit/`, battery in `src/agentic_rag_mcp/deploy/battery.py`, DSL artifact `dify/AGIAssistant/AGI_Assistant.yml`.

---

## Phase 1: Setup

**Purpose**: Nothing to install or configure — the amendment rides the 030 stack. One verification task only.

- [x] T001 Verify the live prerequisites once and record in `specs/031-office-save-anywhere/quickstart.md` §Prerequisites: the OfficeMCP service reachable at `http://127.0.0.1:8888`, the gateway up (`/v1/models` → 200), the sidecar healthy on :28080, and `C:\temp\test` writable from the agent (it is the file lane's root, reached as `/mnt/c/temp/test` — the owner's chosen S1 probe location)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The failing-first amendment suites + the gate inversion — every story consumes these. Tests-first (Constitution II).

**⚠️ CRITICAL**: No story work begins until this phase is green.

- [x] T002 [P] Amend the failing-first gate suite `tests/unit/test_office_gate.py` per research R5 / contract §1: the owner's exact case (*"create a PowerPoint file named test1 with the text Hello and save it to C:\temp\test"*) MUST become `ok` (currently `blocked` — the failing-first proof); `D:\projects\report.docx` named → `ok`; a punctuated second-drive path (`D:\docs.`) → `ok` (the `fail-to-save-file` tolerance, location-agnostic); the **retired-refusal check**: no gate reason string contains "outside the Office work folder" (the `no-powerpoint-tool` actionable-hint assertion and its test retire); the content rules still fire wherever the target lives (macro request with a `D:\` path → blocked; DDE → blocked; `=`-formula content → blocked; formatting → blocked). Suite MUST fail against the current gate
- [x] T003 [P] Amend the failing-first tool suite `tests/unit/test_hermes_office_tool.py` per contract §2/§4: a task naming `D:\projects\notes.docx` → the directive passed to the (mocked) client carries the named location; a mocked OS permission-denied error → `error` envelope with the OS message relayed verbatim + an audit `error` entry; a successful save at a named location → the audit's `normalized_path` is the named target. Suite MUST fail against the current gate
- [x] T004 Implement the gate amendment in `src/agentic_rag_mcp/office_gate.py` until T002 is green per contract §1: remove the work-folder containment block entirely — extracted path tokens become the **SaveTarget** riding on the verdict (normalized via the shared `normalize_path`); no path token → the directive uses the default folder exactly as today; the code-exec, executables-only, formatting, and email checks untouched (they are content rules, not location rules)
- [x] T005 Wire the SaveTarget through `src/agentic_rag_mcp/server.py` until T003 is green per contract §2: the directive for a named-location task carries the normalized target verbatim ("save at exactly this location; create missing parent folders as needed; report the full saved path in ACTIVE FILE:"); the `hermes_office_task` docstring (the DSL-sync source) loses "document work is confined to the Office work folder (default C:\OfficeMCP)" and gains "save or read at any location the user names — any drive, any folder; unnamed saves use the default work folder" (FR-008)
- [x] T006 Add the overwrite/elevation/OS-error rules to `OFFICE_INSTRUCTIONS` in `src/agentic_rag_mcp/hermes_client.py` per research R2 / contract §2: "if the task names an existing file, update it and report honestly that an existing file was replaced; if the application holds unsaved interactive changes for it, ask back before writing; never elevate privileges — if the OS denies a write, relay the exact error in your step report"

**Checkpoint**: `pytest tests/unit/test_office_gate.py tests/unit/test_hermes_office_tool.py` green; the 028 file-lane and 029 launch-lane suites still green (the shared `normalize_path` is untouched); existing suites unaffected.

---

## Phase 3: User Story 1 — Save to any folder the user names (Priority: P1) 🎯 MVP

**Goal**: the owner's exact previously-impossible request — *"create a PowerPoint with 'Hello', file name test1, save to c:\temp\test"* — completes end-to-end: the file exists at the named location, the answer names the full path, the audit records the target (SC-001).

**Independent Test**: quickstart §3 S1 via the battery.

### Tests for User Story 1

- [x] T007 [P] [US1] Add the S1 probe to `scenario_hermes_office_task` in `src/agentic_rag_mcp/deploy/battery.py`: the owner's exact prompt via `mcp_call` → `ok` + `/mnt/c/temp/test/test1.pptx` verified via stdlib `zipfile` (the slide XML contains "Hello"); amend O6 by retiring the out-of-folder refusal case (4 of 5 remain: macros, DDE, address-less, mailbox-delete); O7's audit cross-check unchanged (`allowed_root = C:\OfficeMCP` stays the lane discriminator)

### Implementation for User Story 1

- [x] T008 [US1] Update the DSL Hermes-node office-rule line in `dify/AGIAssistant/AGI_Assistant.yml`: "document work is confined to the Office work folder" → "save or read at any location the user names — any drive, any folder; unnamed saves use the default work folder" (the third and last wording surface per contract §5)
- [x] T009 [US1] Hot-patch the sidecar (`docker cp` the changed `office_gate.py`/`server.py`/`hermes_client.py` + restart), republish via `.venv/bin/python -m agentic_rag_mcp.deploy chatflow` (publish to the app that owns the chat key), run T007 live + the manual chat check (*"save it to D:\docs\"* at any drive); record outcomes in `specs/031-office-save-anywhere/quickstart.md`

**Checkpoint**: MVP — chat saves to any named folder end-to-end.

---

## Phase 4: User Story 2 — Overwrite an existing file the user names (Priority: P1)

**Goal**: naming an existing file updates it with an honest "replaced" report; an unsaved-changes conflict asks back; nothing is silently discarded (SC-003).

**Independent Test**: quickstart §4 (create-then-update in one conversation) + the T003 mocked OS-error case already pins the relay.

### Tests for User Story 2

- [x] T010 [P] [US2] Add the overwrite probe to `scenario_hermes_office_task` in `src/agentic_rag_mcp/deploy/battery.py`: two calls in one conversation — create `C:\OfficeMCP\overwrite_probe.docx` with text "v1", then update the same named file with text "v2" → second call `ok`, the file's `word/document.xml` contains "v2" AND the step report text contains "replac" (the honest overwrite report); the audit holds entries for both

### Implementation for User Story 2

- [x] T011 [US2] Live-run T010 plus the manual re-ask check (the same prompt twice in the Chat UI — the second answer says the existing file was replaced); the unsaved-changes ask-back is instruction-enforced (T006) — verify via a live turn with a document open and dirty in Word, expecting an ask-back not a write; record outcomes in `specs/031-office-save-anywhere/quickstart.md` §4

**Checkpoint**: overwrites are honest and conflict-safe.

---

## Phase 5: User Story 3 — Everything else stays exactly as it was (Priority: P1)

**Goal**: the amendment widened one thing only — the refusal matrix, the file lane, the launch lane, and all other office rules are byte-identical (SC-004, FR-005).

**Independent Test**: quickstart §2 + §3's unchanged matrix.

### Tests for User Story 3

- [x] T012 [P] [US3] Regression sweep: `pytest tests/unit tests/integration tests/contract -q` — every 028/029/030 suite green with only the one amended assertion from T002/T003 differing; the refusal matrix cases (macro/DDE/formatting/address-less/mailbox-delete) produce the same reasons as pre-031 (assertion-level: the reason strings are unchanged)

### Implementation for User Story 3

- [x] T013 [US3] Full live battery (`.venv/bin/python -m agentic_rag_mcp.deploy verify`): all scenarios green — the 028 file-task B1–B5 and 029 launch L1–L9 probes byte-identical, the office O-matrix green with S1 in and the out-of-folder case out; the office-routing guard green; record in `specs/031-office-save-anywhere/quickstart.md` §Recorded outcomes

**Checkpoint**: the scope-widening is proven to have widened one thing only.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T014 [P] Docs sync: `DEPLOY.md` — update the lane-root-mismatch troubleshooting row (bug `no-powerpoint-tool`) to reflect that named locations now work (the row's advice becomes historical: "fixed by spec 031"); `README.md` office-lane section — "confined to the Office work folder" → "any named location; default C:\OfficeMCP"; `AGENTS.md` feature-surface line likewise
- [x] T015 [P] Error-handling live checks per quickstart §5: a save into a permission-protected location (`C:\Windows\System32\...`) → the OS's exact error relayed honestly (never fabricated); a deep path with missing parents → created as needed or the honest failure; a nonexistent drive → honest failure naming the location; record outcomes in `specs/031-office-save-anywhere/quickstart.md`
- [ ] T016 Commit (only on the owner's explicit go-ahead): the 031 source + DSL + battery + spec artifacts, folding in the still-uncommitted 029/030 work and the five bug-fix sets (`office-routing-flake`, `ppt-fail-change-background`, `no-powerpoint-tool`, `ppt-no-response` re-validation, `fail-to-save-file`) — one commit closes the whole held T022 umbrella; note the hot-patch-vs-image-rebuild state in the message

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1**: immediate; T001 blocks the live tasks (T009+) but not the code
- **Phase 2**: blocks ALL story work; T002 ∥ T003 (different test files), then T004 after T002, T005 after T003, T006 independent
- **Phases 3–5**: sequential recommended (single DSL file — never two DSL tasks in flight); battery tasks [P] alongside
- **Phase 6**: last; T016 additionally requires the owner's explicit go-ahead (it also closes 029/030's held T022)

### User Story Dependencies

- US1 (P1): after Phase 2 — no story deps. **MVP = Phases 1–3.**
- US2 (P1): builds on US1's battery base (T010 extends the same scenario; the overwrite rules are already in T006's instructions)
- US3 (P1): pure regression — after US1/US2 land, proves the freeze

### Within Each User Story

- Battery-test task [P] before/alongside the DSL edit; hot-patch + republish + live run; record; next story.

### Parallel Opportunities

- Phase 2: T002 ∥ T003, and T006 independent of both
- Phase 3: T007 (battery file) ∥ T008 (DSL file)
- Phase 4: T010 ∥ T011 prep; Phase 5: T12/T13 are one sweep
- Phase 6: T014 ∥ T015

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 (verify) → 2. Phase 2 (failing-first suites → gate amendment → wording) → 3. Phase 3 (DSL + battery S1 + live) → 4. **STOP and VALIDATE**: *"create a PowerPoint with 'Hello', file test1, save to c:\temp\test"* from chat → the file exists at the named location, the answer names it, the audit records it.

### Incremental Delivery

1. MVP (US1) → 2. US2 overwrite honesty → 3. US3 regression freeze → 4. Polish/docs/commit. Each story keeps the previous green.

---

## Notes

- [P] = different files, no dependencies on incomplete tasks
- The DSL is a single YAML file — never two DSL tasks in flight together
- Publish to the Dify app that owns the chat API key (the two-app gotcha from 029)
- The shared `normalize_path` in `hermes_gate.py` is UNTOUCHED by this feature (its `fail-to-save-file` trailing-punctuation fix already landed) — the 028 file lane's tests must stay byte-identical
- The audit writer is untouched (research R3): `ACTIVE FILE` already carries the true target; `allowed_root` stays the configured default as the battery's lane discriminator
- The MCP-transport flakiness (DEPLOY.md row) is environmental and unchanged — the recovery procedure documented there applies
- Commit only when the owner says so (T016)
