---
description: "Task list for Hermes Program Launch Lane (feature 029)"
---

# Tasks: Hermes Program Launch Lane — Windows Apps from Chat

**Input**: Design documents from `/specs/029-hermes-launch-programs/`

**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/hermes-launch-app.md ✓, quickstart.md ✓

**Tests**: Requested at plan time ("original plan + create test cases and add error handling") and mandated by Constitution II — unit suites failing-first; battery scenario + error matrix as live gates.

**Organization**: Grouped by user story (US1 P1 name-launch, US2 P1 no-args/shell refusal matrix, US3 P2 full-path launch). Stories share the gate module + Hermes node, so the build is foundational-then-lanes (028 pattern).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story the task belongs to
- Exact file paths in every description

## Path Conventions

Sidecar Python at repo root: `src/agentic_rag_mcp/`, tests in `tests/unit/`, battery in `src/agentic_rag_mcp/deploy/battery.py`, DSL artifact `dify/AGIAssistant/AGI_Assistant.yml`.

---

## Phase 1: Setup

**Purpose**: Environment verification + the one shared constant the tool consumes — everything else the lane depends on already exists from spec 028.

- [x] T001 Verify live prerequisites once and record in `specs/029-hermes-launch-programs/quickstart.md` §Prerequisites: `curl -H "Authorization: Bearer <key>" http://172.17.0.1:8642/v1/models` lists `hermes-agent`; sidecar `agentic-rag` reachable on :28080; `/mnt/c` mounted (028 assumptions hold)
- [x] T002 Add the `LAUNCH_INSTRUCTIONS` constant to `src/agentic_rag_mcp/hermes_client.py` per research R1 / contracts §3: launch exactly the stated target (name or full path) with NO arguments and NO command line, never a script or shortcut; if the target cannot be found or fails to start report that honestly; report exactly what was observed (started fresh / already running-activated / failed with reason). `run_task` signature unchanged.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The pure launch gate + the tool wrapper — every story consumes these. Tests-first (Constitution II).

**⚠️ CRITICAL**: No lane work begins until this phase is green.

- [x] T003 [P] Write the failing-first launch-gate suite `tests/unit/test_hermes_launch_gate.py` from research R6 / data-model §LaunchRequest: name targets (bare, quoted, filler-stripped — "open excel on my computer"), path targets (`C:\Windows\System32\notepad.exe` ok; mixed separators/case normalized; `.bat/.cmd/.ps1/.lnk/.vbs/.js/.msi` → blocked naming the executables-only rule), argument matrix (`--flag`, `/flag`, `key=value`, quoted argument strings, `;`/`|`/`&` chaining → blocked naming the no-arguments rule), shell phrasing (powershell/cmd/bash/"command line"/terminal → blocked), no-target ask-back (FR-011), multi-target ask-back (one target per request — never both), smuggled second instruction ("open notepad and also run powershell"). Suite MUST fail (module absent)
- [x] T004 [P] Write the failing-first tool suite `tests/unit/test_hermes_launch_tool.py` with the Hermes client mocked at the trust boundary (respx on httpx): blocked verdicts never call the client and write one audit entry `operation="launch-app"`, `allowed_root=""`, decision `blocked`; client failures (unreachable / timeout / 401 / non-200 / empty output) → `error` envelope with the recovery hints + audit `error`; success → `ok` + audit `executed` with outcome; envelope shapes `{status, decision?, result?, reason?, target?}` per contracts §1. Suite MUST fail (tool absent)
- [x] T005 Implement `src/agentic_rag_mcp/hermes_launch_gate.py` until T003 is green: pure module — classify launch verbs (open/launch/start/run) and strip fillers, extract ONE target (path token via the existing `hermes_gate` normalization helpers, or bare application name), apply the contract §2 pipeline in order (no-target ask-back → executables-only: path targets MUST end `.exe` post-normalization, scripts/shortcuts blocked → no-arguments/no-shell → one-target-per-request ask-back), return `LaunchVerdict` (decision/operation=`launch-app`/target/kind=name|path/reason)
- [x] T006 Wire the MCP tool `hermes_launch_app(task: str)` in `src/agentic_rag_mcp/server.py` until T004 is green per contracts §1–§4: gate → exactly one audit entry at the verdict point (`HermesAudit` unchanged; `operation="launch-app"`, `allowed_root=""`) → blocked: honest envelope with reason, never call the client; allowed: `hermes_client.run_task(cfg, sanitized_task, instructions=LAUNCH_INSTRUCTIONS)` → relay result + audit `executed` with outcome; failure: honest envelope + recovery hint + audit `error`. Docstring = the DSL-synced tool_description per contracts §7

**Checkpoint**: `pytest tests/unit/test_hermes_launch_gate.py tests/unit/test_hermes_launch_tool.py` green; existing suites still green; the tool is callable in-process.

---

## Phase 3: User Story 1 — Launch a desktop app from chat (Priority: P1) 🎯 MVP

**Goal**: "open notepad" through the chat launches Notepad on the Windows desktop in the same turn (no confirmation round-trip, FR-013), the answer confirms the launch, audit holds an `executed` entry, within the Hermes call timeout (SC-001 amended — measured 10–230 s, agent-turn bound).

**Independent Test**: quickstart §3 L1 via the battery + the manual chat check ("can you open Excel?").

### Tests for User Story 1

- [x] T007 [P] [US1] Add the `scenario_hermes_launch_app` battery scenario to `src/agentic_rag_mcp/deploy/battery.py` (L1: `mcp_call("hermes_launch_app", {"task": "open notepad"})` → status ok, < 60 s, audit tail shows an `executed` entry with `operation:"launch-app"`, optionally corroborated via host-side `tasklist.exe`) and register it in the scenario list after `hermes-file-task`

### Implementation for User Story 1

- [x] T008 [US1] Extend the `intent_router` classifier prompt in `dify/AGIAssistant/AGI_Assistant.yml`: the "Hermes file task" class becomes the local-machine class — its instruction gains launch phrasing ("…or wants a program/application launched, started, opened, or run on their Windows computer, by name or full path") per contracts §5; existing class ids/handles unchanged
- [x] T009 [US1] Wire the tool into the `hermes_agent` node in `dify/AGIAssistant/AGI_Assistant.yml`: add the `hermes_launch_app` MCP tool entry (provider `agentic-rag`, tool_description synced from the server docstring — all copies updated) and extend the node instructions additively (file rules verbatim from 028 + launch rules: pick `hermes_launch_app` for program launches; mixed prompts may call each tool for its part; relay verdicts verbatim; never claim direct desktop access; PowerShell/shell requests still declined per the tool verdict)
- [x] T010 [US1] Republish via `.venv/bin/python -m agentic_rag_mcp.deploy chatflow`, hot-patch the running sidecar (`docker cp` the new `hermes_launch_gate.py`/`hermes_client.py`/`server.py` + restart container), run T007 live, and do the manual chat check ("can you open Excel?" → Excel starts in the same turn); record outcomes in `specs/029-hermes-launch-programs/quickstart.md`

**Checkpoint**: MVP — chat launches real Windows programs end-to-end.

---

## Phase 4: User Story 2 — Launch arguments and shell commands are refused, never executed (Priority: P1)

**Goal**: The refusal matrix (arguments, command lines, shell phrasing, script/shortcut paths, smuggled instructions) is refused with the rule named; zero processes started with refused elements; audit records every block (SC-002/SC-005).

**Independent Test**: quickstart §3 L3–L5 via the battery + the Phase 2 unit matrix already green.

### Tests for User Story 2

- [x] T011 [P] [US2] Extend `scenario_hermes_launch_app` in `src/agentic_rag_mcp/deploy/battery.py` with the refusal probes: L3 "run a PowerShell command that lists processes" → blocked; L4 "launch outlook --dangerous-flag" → blocked (no-arguments rule); L5 "run C:\temp\setup.bat" → blocked (executables-only rule, file may exist); assert audit `blocked` entries in order and no executed launch carrying any refused element

### Implementation for User Story 2

- [x] T012 [US2] Harden the Hermes agent node instructions in `dify/AGIAssistant/AGI_Assistant.yml`: relay blocked reasons verbatim; never re-attempt a blocked launch with rephrased targets or a different spelling (anti-smuggling); relay ask-backs verbatim; republish via `deploy chatflow`
- [x] T013 [US2] Run the extended battery live including the error probe (stop the Hermes gateway → launch prompt → honest `error` envelope + recovery hint per FR-008; restart gateway) and record the outcomes in `specs/029-hermes-launch-programs/quickstart.md` §5

**Checkpoint**: The security story is complete and evidence-backed.

---

## Phase 5: User Story 3 — Launch any tool on the machine by full path (Priority: P2)

**Goal**: Non-Start-menu tools launch by full `.exe` path; nonexistent/non-executable paths fail honestly naming the path (SC-003); routing regressions stay green (SC-004, FR-010 mapping).

**Independent Test**: quickstart §3 L2/L6–L9 via the battery; 028's B5 file-tool probes still blocked.

### Tests for User Story 3

- [x] T014 [P] [US3] Extend `scenario_hermes_launch_app` in `src/agentic_rag_mcp/deploy/battery.py` with: L2 full-path launch (`run C:\Windows\System32\notepad.exe` → ok, that exact program); L6 `launch C:\nope\missing.exe` → `error` naming the path, nothing started; L7 "open it" → ask-back; L8 "open notepad and calculator" → ask-back (one target per request); L9 audit cross-check — exactly one `operation:"launch-app"` entry per L1–L8 attempt, decisions in order, none fabricated

### Implementation for User Story 3

- [x] T015 [US3] Live checks + regression sweep per quickstart §4–§5: already-running honest relay (launch Notepad twice — answer reports what the agent observed, never "started fresh"); unresolvable name → honest error naming the app; 028's B5 direct `hermes_file_task` decline probes still blocked (contracts §6 — defense in depth); classifier routing: chat "open notepad" lands on the Hermes branch; chat-journey/antv/stop scenarios unchanged; record outcomes in `specs/029-hermes-launch-programs/quickstart.md`

**Checkpoint**: All three stories functional; full battery green.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T016 [P] Docs sync: root `AGENTS.md` Hermes-lane feature-surface line (adds the launch capability: any executable by name or full `.exe` path; no arguments, no shell, no scripts/shortcuts; audited), `DEPLOY.md` tool-count line 24 → 25 + troubleshooting row (launch blocked → the no-arguments/executables-only rules), `README.md` lane bullet
- [x] T017 Full green sweep: `pytest tests/unit tests/integration tests/contract -q` (existing 351+ green — no weakened tests), `pnpm typecheck && pnpm lint && pnpm test` in `ai-chat-landing/` (untouched — must stay green), full battery live; update `specs/029-hermes-launch-programs/quickstart.md` with the recorded final L-matrix results
- [x] T018 [P] Commit: source + DSL + battery + spec artifacts; leave the audit log and `~/.hermes/.env` out (user data, never committed); note the pending sidecar image rebuild in the commit message (docker cp hot-patch caveat)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1**: immediate; T002 blocks Phase 2's T006 (the tool passes `LAUNCH_INSTRUCTIONS`)
- **Phase 2**: blocks ALL lane work; T005 after T003 and T006 after T004 (tests fail first); T003 ∥ T004 (different files)
- **Phases 3–5**: sequential recommended (each republishes the DSL — never two DSL tasks in flight); within a phase, battery tasks [P] run alongside DSL work
- **Phase 6**: last

### User Story Dependencies

- US1 (P1): after Phase 2 — no story deps. **MVP = Phases 1–3.**
- US2 (P1): builds on US1's scenario + node (T011 extends T007's scenario; T012 hardens T009's instructions)
- US3 (P2): builds on US1/US2's scenario + node (T014 extends the same scenario; T015 asserts the FR-010 probe mapping)

### Within Each User Story

- Battery-test task before the DSL edit (assert the current gap), DSL + republish + hot-patch, live run, then next story.

### Parallel Opportunities

- Phase 2: T003 ∥ T004 (different files)
- Phase 3: T007 (battery file) ∥ T008/T009 (DSL — single file, sequential pair)
- Phase 4: T011 ∥ T012 prep; Phase 5: T014 ∥ T015 prep
- Phase 6: T016 ∥ T017 prep

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 (verify + instructions constant) → 2. Phase 2 (gate green, tool wrapped) → 3. Phase 3 (DSL wiring + battery L1 + live) → 4. **STOP and VALIDATE**: "open notepad" launches Notepad from chat, audit shows `executed` — chat-driven program launch works.

### Incremental Delivery

1. MVP (US1) → 2. US2 refusal battery → 3. US3 full-path reach + regressions → 4. Polish/docs/commit. Each story keeps the previous green (battery re-run per phase).

---

## Notes

- [P] = different files, no dependencies on incomplete tasks
- The DSL (T008/T009/T012) is a single YAML file — never two DSL tasks in flight together
- Sidecar changes reach the running container via `docker cp` (AGENTS.md); the image rebuild stays pending — note it in the commit
- The Hermes key lives in `~/.hermes/.env` and `~/.config/agentic-rag-mcp/config.toml` only — never in the DSL, answers, or repo
- No new config fields (research R3): `hermes_api_url/key/timeout_s/audit_path` already exist; the launch tool takes no allowed-root
- FR-010 probe mapping (contracts §6): 028's B5 direct file-tool decline probes stay blocked — the flip lives in `hermes_launch_app` + the classifier routing check
- Battery scenario must not depend on spec-026 model state — the lane works for any configured model
- Commit after each phase or logical group

---

## Phase 7: Convergence

- [x] T019 Add a mixed-prompt probe for the combined launch+file case — one battery case or gate-level unit test for "open Notepad and create notes.txt in C:\temp" asserting each part is handled by its own lane rule and both verdicts are reported honestly, per spec Edge Cases (missing)
- [x] T020 Ratify or revert the implementation-phase additions beyond the specced surface — `tool_sync.SUPPORTED_DB_RESYNC` widened to Dify 1.18 (schema validated live; provider cache 24→25) and the three snapshot-test amendments (antv/ppt `EXISTING_TOOLS` sets, `CONTRACT_SCENARIOS`) — justification recorded in `specs/029-hermes-launch-programs/quickstart.md` §Recorded outcomes 2026-11-01; ratify with a spec-011 note or revert (unrequested)
- [x] T021 Fix or document the Answer-node merge rendering on Dify 1.18: Hermes-branch answers carry a literal "agentic_strategy.textagentic_strategy_local.text" prefix because non-run branch references render literally — pre-existing (reproduces on the 028-era DSL) and it degrades US1's answer presentation (partial)
