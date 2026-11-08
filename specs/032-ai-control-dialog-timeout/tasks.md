# Tasks: AI Control Dialog Timeout

**Input**: Design documents from `/specs/032-ai-control-dialog-timeout/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: No repo test tasks — the behavior is visual timing inside the third-party Windows service; validation is the quickstart.md measurement protocol. The WSL suite (346 tests) must stay green (final phase).

**Organization**: Tasks grouped by user story. The patch target lives OUTSIDE this repository (the installed WindowsMCP tool); repo deltas are documentation only.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)

## Path Conventions

- Patch surface: `C:\Users\RLWC145\AppData\Roaming\uv\tools\windows-mcp\Lib\site-packages\windows_mcp\desktop\control.py` (WSL view: `/mnt/c/Users/RLWC145/AppData/Roaming/uv/tools/windows-mcp/Lib/site-packages/windows_mcp/desktop/control.py`)
- Repo delta: `DEPLOY.md` only

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Safe patching baseline

- [X] T001 Create a backup of the patch target before editing: copy `.../windows_mcp/desktop/control.py` to `.../windows_mcp/desktop/control.py.orig-032` (exact-file snapshot enables honest reversion, FR-005)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: None — this feature has no shared infrastructure beyond the backup. Phase skipped by design (no repo code, no schema, no interfaces).

---

## Phase 3: User Story 1 - Dialog auto-dismisses in ~3 seconds (Priority: P1) 🎯 MVP

**Goal**: The "AI is controlling this computer" notice clears within ~3 s of the AI's last desktop action (was up to ~15 s via the control-lease tail).

**Independent Test**: Quickstart V1 — run two consecutive desktop tasks (e.g., "open chrome, type www.google.com" in the chat), time the notice: disappears ≤ ~3 s after the AI's last action; typing still completes and verifies.

### Implementation for User Story 1

- [X] T002 [US1] Patch the control-lease tail in `.../windows_mcp/desktop/control.py`: change `self._lease_until = time.monotonic() + 15.0` (line ~317, in `end_call`) to `+ 3.0` — do NOT touch any `10.0` constant (user-revert/wait-for-idle window, owner decision: unchanged) and add a one-line trailing comment: `# patched for spec 032 (notice clears ~3s); re-apply after tool upgrade`
- [X] T003 [US1] Restart the service via the `windows-mcp-server` scheduled task and verify health: SSE `http://127.0.0.1:8800/sse` responds 200 and a `ControlStatus` probe returns `{"state":"ready","generation":1}` (fresh generation proves the new code loaded)
- [X] T004 [US1] Live-verify quickstart V1: two consecutive desktop tasks in the chat; notice clears ≤ ~3 s after the AI's last action both times; each task's typing still completes and verifies end-to-end

**Checkpoint**: The MVP is done — the notice is shortened and desktop tasks still work.

---

## Phase 4: User Story 2 - Safety behavior unchanged (Priority: P2)

**Goal**: Take-over, the 10-second wait-for-idle window, and consent gating behave exactly as before the patch.

**Independent Test**: Quickstart V2 + V3 — during an AI desktop action, physical input reverts control instantly; `ControlStatus.wait_seconds` counts down from 10 unchanged; Ctrl+Alt+Shift+Backspace interrupts immediately.

### Verification for User Story 2

- [X] T005 [US2] Verify quickstart V2: while a desktop task runs, provide physical input (mouse move/keypress) → control reverts instantly, and `ControlStatus.wait_seconds` reports a countdown from 10 (unchanged — proves the `10.0` constants were not touched)
- [X] T006 [US2] Verify quickstart V3: press Ctrl+Alt+Shift+Backspace during an active AI action → gated actions stop immediately

**Checkpoint**: Safety parity proven; both stories independently satisfied.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, persistence, and suite health

- [X] T007 [P] Document the patch in `DEPLOY.md` (WindowsMCP section): what changed (`control.py` lease tail 15.0 → 3.0), why (spec 032), the backup file, and the re-apply step after any windows-mcp upgrade/reinstall (FR-002/FR-005)
- [X] T008 Verify quickstart V4: restart the scheduled task once more and re-run V1 — the ~3 s behavior persists (the patch lives in the installed files the task relaunches); note V5: if the tool is upgraded/reinstalled, the notice reverting to ~15 s is the observable failure signal (detected by re-running V1)
- [X] T009 Run the WSL suite `pytest tests/unit` (346 expected green — no repo code touched) and commit + push the DEPLOY.md note and spec artifacts

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — T001 first (blocks the patch task)
- **US1 (Phase 3)**: Depends on T001 (backup before edit); T002 → T003 → T004 sequential
- **US2 (Phase 4)**: Depends on T003 (a running patched service to verify against); T005/T006 can run in parallel
- **Polish (Phase 5)**: T007 parallelizable anytime after T002; T008 after T004; T009 last

### User Story Dependencies

- **US1 (P1)**: The whole feature (patch + restart + live verification)
- **US2 (P2)**: Verification-only — depends on US1's running service, but is an independent acceptance pass, not new code

### Within Each User Story

- Backup before patch; patch before restart; restart before live verification

### Parallel Opportunities

- T005 ‖ T006 (two independent safety probes)
- T007 ‖ T004 (documentation vs live verification, different files)

---

## Parallel Example: User Story 2

```bash
# Launch both safety probes together:
Task: "Verify quickstart V2 (wait_seconds from 10 unchanged)"
Task: "Verify quickstart V3 (takeover shortcut instant)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. T001 (backup) → T002 (patch) → T003 (restart + health) → T004 (live timing)
2. **STOP and VALIDATE**: the notice clears in ~3 s on two consecutive tasks

### Incremental Delivery

1. MVP (US1) → notice shortened, tasks still work
2. US2 verification → safety parity proven
3. Polish → documented, persistent, suite green

---

## Notes

- [P] tasks = different files, no dependencies
- Do NOT touch the `10.0` constants in `control.py` (lines 151/207/214/226-228) — owner decision A
- The patch is outside this repo: the only repo deltas are `DEPLOY.md` and this spec directory
- Re-apply check after any windows-mcp upgrade/reinstall is part of T007's documentation
