# MCP-Action — Test Report

**Feature**: `047-mcp-action`
**Started**: 2026-11-20

## T003 — Baseline before MCP-Action implementation

### Python unit + contract

Command: `.venv/bin/python -m pytest tests/unit tests/contract -q`

Result: **808 passed, 3 failed, 186 warnings in 275.07 seconds**.

The following failures occurred before any MCP-Action tool or behavior was registered and are recorded as pre-existing:

1. `tests/contract/test_antv_contract.py::test_tools_list_grows_21_to_23` — expected stale tool count 26; current server advertises 58.
2. `tests/contract/test_ppt_contract.py::test_tools_list_grows_16_to_21` — expected stale tool count 26; current server advertises 58.
3. `tests/contract/test_web_research_contract.py::test_web_research_limit_capped_at_max_pages` — stale expected page cap 3; current result count 6.

### Frontend

Commands: `pnpm test && pnpm typecheck && pnpm lint` in `ai-chat-landing/`.

- Vitest: **25 files / 185 tests passed**.
- TypeScript: **passed**.
- ESLint: **0 errors, 1 pre-existing warning** at `scripts/stop-button-check.mjs:16:7` (`ONLY` unused).

## Implementation evidence

Later task evidence is appended below as tasks complete.

## T012 — Live Dify draft/cancel contract gate (PASS with owner-approved scope)

The additive sidecar was redeployed and the MCP registry synchronized. Both Dify apps were published only by explicit ID:

- `194e1edf-2eba-442c-b10b-231bebb79c37`
- `7863fbe2-47f8-48c9-b096-6f7da8536b08`

The live probe `RUN_MCP_ACTION_DIFY_CONTRACT=1 .venv/bin/python -m pytest tests/integration/test_mcp_action_dify_contract.py -q -s` produced:

| Lane | Evidence | Result |
|---|---|---|
| General cloud | `dialogue_count=1 → 2`; exact raw query/conversation; final draft `pending-confirmation`; final next-turn `cancelled`; active-agent-only honesty result | **PASS** |
| General local | Repeated local-model draft/cancel attempts did not reliably dispatch `mcp_action`; one cancel answer leaked `{"name":"status","arguments":{}}` as text instead of a tool call | **FAIL — hard stop** |
| Hermes | `dialogue_count=1 → 2`; exact raw query/conversation; final draft `pending-confirmation`; final next-turn `cancelled`; active-agent-only honesty result | **PASS** |

Integration fixes validated during the probe:

- Added instruction-level runtime bindings for raw query, conversation ID, and dialogue count.
- Extended honesty parsing for actual Dify `tool_responses[]`, CALL-shaped entries, and wrapped `tool response: {…}.` JSON.
- Added a narrow MCP-Action override to prevent infographic-only substitution on MCP-Action turns.
- Updated the probe to distinguish actual tool responses from agent thoughts, deduplicate repeated representations, allow validation-only retries, and permit the next turn to use any one wired answering agent.

No `confirm` call was enabled by implementation and no printer, Word, or document mutation occurred during these probes.

### Owner decision and final result

The owner selected **Cloud + Hermes only**. General-local was restored exactly to its original DSL and is excluded from MCP-Action. The specification, plan, contracts, quickstart, tasks, and static tests now record that boundary.

Final command: `RUN_MCP_ACTION_DIFY_CONTRACT=1 .venv/bin/python -m pytest tests/integration/test_mcp_action_dify_contract.py -q -s`

Final result: **2 passed in 46.79 seconds**.

- General cloud: `dialogue_count=1→2`, draft pending, immediate cancel cancelled, guard active-agent-only — **PASS**.
- Hermes: `dialogue_count=1→2`, draft pending, immediate cancel cancelled, guard active-agent-only — **PASS**.
- General-local: original behavior retained, no MCP-Action tool or offer — **OUT OF SCOPE BY OWNER DECISION**.

T012 is complete and execution work may proceed on the two approved lanes.

## T033 — US1 deterministic validation (PASS)

- Focused Python unit/DSL/regression suites: **348 passed**.
- Screenshot route contracts: **8 passed**.
- Additive MCP schema + deployment battery contracts: **12 passed** (one existing embedding FutureWarning).
- Frontend: **26 files / 188 tests passed**; TypeScript passed; `mcp-action-check.mjs` syntax passed.
- ESLint: **0 errors**, one pre-existing `ONLY` warning in `scripts/stop-button-check.mjs`.
- Ruff on MCP-Action production and integration files passed. A broader run including `deploy/battery.py` reports only its pre-existing BLE001/ISC004/RUF059/FURB167 findings outside the one-line tool-surface change.
- `git diff --check`: **passed**.

All US1 implementation gates are green for owner-present live validation.

## T034 — US1 live integration + browser acceptance (PASS)

### Integration

Command: `RUN_MCP_ACTION_E2E=1 MCP_ACTION_TEST_PRINTER='HP LaserJet M610 TCPIP' .venv/bin/python -m pytest tests/integration/test_mcp_action_e2e.py -q -rs`

Final result: **8 passed, 2 environment skips in 241.64 seconds**.

Verified live:

- Decline/orphan/generic follow-up does not execute.
- Confirmed default-printer changes and repeat/already-active handling are read back independently.
- Modified confirmation requires a fresh proposal before execution.
- Settings is verified with host-side `WaitFor` on `Printers & scanners`.
- Screenshot capture returns one valid PNG; deployed URLs return image bytes with `no-store`.
- Original default is restored/retained as `HP LaserJet M610 TCPIP`.

Environment skips: no case-insensitive duplicate printer exists, and `LegacyDefaultPrinterMode=1` (manual mode) makes the managed-default-specific case inapplicable.

### Browser CDP

Command: `RUN_MCP_ACTION_E2E=1 MCP_ACTION_ALLOW_PRINTER_CHANGE=1 MCP_ACTION_TEST_PRINTER='Microsoft Print to PDF' MCP_ACTION_MODIFIED_PRINTER='HP LaserJet M610 TCPIP' node ai-chat-landing/scripts/mcp-action-check.mjs`

All **5 journeys passed**:

1. Default-printer no.
2. Orphan yes.
3. Ordinary generic follow-up.
4. Default-printer yes + repeated yes.
5. Modified yes-but-other + fresh yes.

Evidence: before `HP LaserJet M610 TCPIP` → after `Microsoft Print to PDF`; `duplicateExecution=false`; `oldProposalExecuted=false`; screenshot HTTP 200 + `no-store`, 286,610 bytes, `naturalWidth=1920`; modified journey screenshot 286,108 bytes; restoration unchanged.

### Managed-default disclosure follow-up

Early read-only probing recorded `LegacyDefaultPrinterMode=0`; later acceptance observed `1`. The proposal/result caveat was strengthened to disclose explicitly that choosing a manual default may turn off **Let Windows manage my default printer** and that the change may not persist. All **45 reviewed-action tests pass** with the stronger disclosure. This text-only change rides the next sidecar redeploy.

## T046 — US2 deterministic + US1 regression validation (PASS)

- Combined Python unit/DSL/regression suites: **496 passed**.
- Screenshot route + MCP/deploy contracts: **25 passed** (10 pre-existing warnings).
- Live integration battery: **23 tests collected** successfully.
- Frontend: **26 files / 188 tests passed**; TypeScript passed; Word CDP script syntax passed.
- ESLint: **0 errors**, one pre-existing `ONLY` warning.
- Ruff on all MCP-Action, Windows, Office, server, and integration files: **passed**.
- `git diff --check`: **passed**.

Ready for owner-present Word/duplex live validation.

## T047 — US2 live integration + browser acceptance (PASS by per-case evidence)

### Integration

The final per-case evidence covers all required journeys. Repeated attempts to run all 23 cases in one process were interrupted by Windows session disconnections (`qwinsta` = `Disc`), which produce `CONTROL_UNAVAILABLE`; those environment failures are not counted as code failures. After RDP reconnection and scheduled-task recovery, the remaining E06 case passed (`1 passed, 22 deselected in 280.81 seconds`).

Verified across the passing batches:

- US1 integration: **8 passed, 2 environment skips**.
- Word direct/duplex journeys: long-edge, short-edge, already-active, unsupported printer/capability, Office/Windows offline, transport failure, concurrency, duplicate/orphan confirmation, access/capability handling, and restoration all passed in their final targeted runs.
- E06: final cross-agent draft/cancel/confirm/repeat case passed with loaded screenshot and restored default.
- Environment-only skips remain: no duplicate printer, managed-default-specific case in manual mode, and access-denied-specific case not reproducible on this printer/user.
- Read-only validation now retries one transient malformed/CLIXML/transport failure only; mutation never retries blindly. All **100 reviewed-action tests pass**.

A final read-only state check after RDP reconnection reports:

- Current default printer: `Brother HL-L2375DW series (redirected 1)`.
- HP duplex: `TwoSidedLongEdge`.

### Browser CDP — Word

Command: `RUN_MCP_ACTION_E2E=1 MCP_ACTION_ALLOW_WORD_DUPLEX=1 MCP_ACTION_DUPLEX_PRINTER='HP LaserJet M610 TCPIP' node ai-chat-landing/scripts/mcp-action-check.mjs --word-only`

All **6 journeys passed**:

1. Word no.
2. Long-edge (already active).
3. Short-edge.
4. Modified long→short with fresh confirmation.
5. Already-active long-edge + repeated confirmation (`duplicateExecution=false`).
6. Unsupported Office procedure (manual only, no offer).

Every execution case independently read back the expected duplex, showed Word Print Preview, preserved the disposable unsaved marker with `Saved=false`, reported `printJobs=unchanged`, and loaded a `no-store` screenshot with `naturalWidth=1920`. Modified confirmation also produced a loaded screenshot. Original duplex remained `TwoSidedLongEdge` after the suite.

### Operational note

The Windows session disconnected during several long combined runs. Recovery used RDP reconnection plus the documented `windows-mcp-server` scheduled-task restart. No environment outage was treated as a successful test, and no fabricated success was accepted.

## T048 — Full deterministic and Dify contract validation (pre-remediation checkpoint)

- Pre-remediation checkpoint: **1,223 passed, 3 failed, 187 warnings in 288.88 seconds**. The three failures were the pre-existing baseline failures recorded in T003; they were later repaired under “Analysis remediation” below.
- Dify live contract: **2 passed in 43.60 seconds**. General-cloud and Hermes both show `dialogue_count=1→2`, pending draft, immediate cancellation, and active-agent-only guard output.
- Frontend: **26 files / 188 tests passed**; TypeScript passed; ESLint has one pre-existing `ONLY` warning.
- Ruff on all MCP-Action, Windows, Office, server, and integration files passed; `git diff --check` passed.

## T049 — Cross-story concurrency, expiry, and evidence (PASS)

- E17 concurrent Word actions: **passed** with serialized execution and queue timing.
- E18 simultaneous identical confirmations: **passed** — exactly one real execution, one blocked duplicate, restored duplex, real display/screenshot, marker and print-job preservation.
- E19 exact-900-second expiry: **passed** — blocked with zero executor/display/screenshot calls and no duplex change.
- E20 screenshot route/evidence: repeated GET + `no-store`, invalid/expired-token 404, and browser-loaded screenshots verified by the 8 route contracts and CDP evidence.

## T052 — Documentation (COMPLETE)

Added spec-047 MCP-Action sections to `AGENTS.md` and `ai-chat-landing/AGENTS.md` covering scope, consent/expiry, serialization, read-back, screenshot privacy/capability-URL caveat, source/test paths, deployment commands, and live-test safety. Unrelated documentation was unchanged.

## T050 — Deployment and headless battery (COMPLETE with documented scenario mismatch)

Used the safe equivalent of `deploy all` because its chatflow helper selects by the shared app name:

1. `.venv/bin/python -m agentic_rag_mcp.deploy redeploy` — sidecar healthy; **59 tools** synchronized.
2. Manual draft update + publish by explicit IDs `194e1edf-2eba-442c-b10b-231bebb79c37` and `7863fbe2-47f8-48c9-b096-6f7da8536b08`.
3. `.venv/bin/python -m agentic_rag_mcp.deploy verify` — **14/16 passed**, with project cleanup.

Passing scenarios include health, tools surface, deck roundtrip/export, honest errors, Chat UI, backend stop, Hermes file/launch/Office, ask-first, ANTV chart/infographic, and chart-in-deck.

- `chat-journey` initially found no deck link, then passed on isolated rerun with HTTP 200.
- `office-routing` fails its `real-block-setup` because the scenario does not answer the spec-045 workbook/worksheet clarification before expecting a gate refusal. The direct `hermes_office_task` gate still returns the exact `Blocked:` formatting refusal. The scenario/spec-045 mismatch is documented rather than changing unrelated ask-first behavior.
- MCP-Action-only Office exclusions now explicitly preserve `hermes_office_task` routing; **91 DSL tests passed** with that preservation pin.

## T051 — Final CDP and performance acceptance (PASS)

### Default printer (`--default-only`)

All **5 journeys passed**: no, orphan, ordinary follow-up, yes + repeated yes, and modified yes. Actual before/after read-back was correct, `duplicateExecution=false`, `oldProposalExecuted=false`, both success screenshots returned HTTP 200 + `no-store`, and restoration returned the original default.

Durations: 14.8–64.1 seconds per full browser journey (including model time, not just service execution).

### Word (`--word-only`)

All **6 journeys passed**: no, long-edge, short-edge, modified long→short, already-active + repeated confirmation, and unsupported Office procedure.

Durations: 34.3–78.8 seconds per full browser journey, all under the 90-second Word budget in these samples. Every execution case showed Print Preview, preserved the unsaved marker (`Saved=false`), reported `printJobs=unchanged`, and returned HTTP 200 + `no-store` screenshots with `naturalWidth=1440`. Repeated confirmation reported `duplicateExecution=false`. Original duplex remained `TwoSidedLongEdge`.

The browser timings include model generation and rendering and are not used to claim the service-side 95% performance percentile. Execution/queue timings remain separately available in tool results; no performance claim is fabricated from this small sample.

## T053 — Knowledge and code indexes (COMPLETE)

- `ccc index`: **1,049 files**, 6 added, 0 reprocessed, **0 errors**; 44,310 chunks.
- codebase-memory: `ready`, **14,823 nodes / 31,573 edges**; coverage report retained as best-effort only.
- Graphify manual incremental runbook after the documented saved-semantic-node guard: **10,905 nodes / 17,613 edges / 904 communities / 123 hyperedges**. Guarded export passed; saved semantic nodes and hyperedges were preserved, and manifest/cost were updated.
- `graph.html`: automatic aggregation to 904 community nodes + 1,488 cross-community edges.
- Intermediate Graphify/chunk files were cleaned up. No `--force` was used.

## T054 — Final requirement, evidence, and cleanup reconciliation

### Validation snapshot before analysis remediation

- Pre-remediation Python suite: **1,233 passed, 3 failed, 187 warnings in 324.11 seconds**. Those three baseline failures were subsequently repaired; see “Analysis remediation” below for the final green run.
- Frontend: **188 tests passed**, TypeScript passed, one pre-existing ESLint warning.
- Dify consent contract: **2 passed**.
- Live browser acceptance: **5 default-printer + 6 Word journeys passed**.
- E17 serialization, E18 duplicate confirmation, and E19 exact-900-second expiry all passed; E20 screenshot route/privacy contracts passed.

### Functional requirements

| Requirements | Evidence and result |
|---|---|
| FR-001–FR-003 | Tailored manual steps precede the exact offer; unsupported/out-of-scope procedures do not receive it — **met**. |
| FR-004–FR-010 | Conversation-scoped stored proposal, next-turn raw-response confirmation, modification invalidation, no/cancel/orphan/repeat handling, missing-info ask-backs — **met by 102 state tests, live Dify N→N+1, and CDP journeys**. |
| FR-011–FR-013 | Only two fixed reviewed actions exist; no arbitrary command/COM/GUI execution; printer-wide duplex and managed-default side effects are disclosed — **met**. |
| FR-014 | Before/after system read-back, not pixels, is authoritative for every reported success — **met live**. |
| FR-015–FR-017 | Settings/Print Preview display, inline screenshot, and separate state/verification/display/capture outcomes including partial failures — **met**. |
| FR-018–FR-021 | Unsaved documents preserved; safety boundaries/permission errors retained; one pending proposal per conversation; sanitized append-only audit — **met**. |
| FR-022–FR-025 | Existing direct-action/Hermes Office behavior preserved; one desktop lock; 15-minute expiry; General-local/PPT excluded per owner decision — **met**. |

### Success criteria

| Criterion | Result |
|---|---|
| SC-001–SC-003 | Exact supported offers, no unintended negative-path execution, and read-back-backed success all passed their acceptance cases. |
| SC-004 | **Met by T056**: 20/20 samples per action, default-printer p95 **23.723s < 60s**, Word duplex p95 **3.249s < 90s**, with queue wait reported separately and original settings restored. |
| SC-005 | State, verification, display, and screenshot outcomes are reported independently for ok/partial/error cases. |
| SC-006 | Exact wording and before/after clarity passed deterministic checks; a formal participant-rated 90% comprehension study was **not performed**. |
| SC-007 | Concurrent confirmations are serialized, and duplicate/stale confirmations are blocked without duplicate execution. |

### Environment-blocked / external notes

- No duplicate-printer environment exists for the case-insensitive duplicate test.
- Managed-default-specific acceptance is inapplicable in manual mode; the proposal/result now explicitly warns that choosing a manual default may turn off Windows-managed defaulting.
- The access-denied-specific duplex case is not reproducible on the approved HP printer; permission and capability failures remain covered by unit and unsupported-printer paths.
- Long combined runs were interrupted by Windows RDP disconnection. Passing per-case evidence was used instead of claiming a single uninterrupted 25-case live run.
- `office-routing` remains an outdated scenario/spec-045 setup mismatch; the direct Hermes gate refusal works, and `chat-journey` passed on rerun.
- Formal participant UX scoring remains an external acceptance item, not a fabricated pass.

### Cleanup and final state

- Word marker documents: **0 remaining**; T040-created blank candidates: **0 remaining**. Eight other documents were not touched.
- Host screenshot store: **0 artifacts**; container screenshot store: **0 artifacts**. Host expired cleanup removed 27 artifacts.
- Final default printer: `Brother HL-L2375DW series (redirected 1)`.
- Final HP duplex: `TwoSidedLongEdge`.
- No temporary screenshots, test-owned Word markers, unrestored duplex changes, or unresolved dishonest-success findings remain.
- All 57 tasks are complete; `git diff --check` passes.

## T055 — Sanitized audit outcomes and timings (COMPLETE)

- Added `display_s` and `screenshot_s` alongside queue/execution/total timings; skipped stages are `null`.
- Audit outcome now includes action/status plus `verification=…`, `display=…`, and `screenshot=…` without image URLs/tokens/paths/bytes or desktop text.
- Updated `data-model.md` and `contracts/mcp-action.md`.
- **50 focused service/concurrency tests passed** at that checkpoint.

## T056 — Service-side 20-run latency benchmark (COMPLETE)

Opt-in benchmark: `RUN_MCP_ACTION_E2E=1 RUN_MCP_ACTION_BENCHMARK=1 ... -k t056_default|t056_word`.

| Action | Samples | p95 execution | p95 queue wait | Target | Restoration |
|---|---:|---:|---:|---:|---|
| Windows default printer | 20/20 | **23.723 s** | ~0.000012 s | 60 s — **PASS** | restored |
| Word printer duplex | 20/20 | **3.249 s** | ~0.000014 s | 90 s — **PASS** | restored |

Each sample used actual setter/read-back/display/capture and required `ok`, `verified`, `displayed`, and `captured`. Sanitized samples and timings are in `specs/047-mcp-action/benchmark-results.json`.

The initial default run encountered one transient unavailable result and was rerun; the Word foreground failure was fixed with one supported `App switch` plus fresh COM revalidation before the successful 20-sample run.

## T057 — Capture scope and regional evidence (COMPLETE)

- `ScreenshotCapture` now probes the focused window with the installed `UIAutomationClient` .NET API and uses `Screenshot(region=[left, top, right, bottom])` for valid bounds.
- Falls back honestly to full display when bounds are unavailable or regional capture fails; `capture_scope` and optional `region_fallback` are returned and disclosed to agents.
- The host does not have `csc.exe`, so the initial `Add-Type` approach was replaced with `AutomationElement.FocusedElement` and parent-window bounds.
- A deployed capture returned `capture_scope=foreground-window`; its public route returned HTTP 200, `Cache-Control: no-store, max-age=0`, and `image/png`.
- All **54 focused capture/service/concurrency tests** and **92 DSL tests** passed at that checkpoint.

## Final convergence validation

- Final full Python suite: **1,245 passed, 0 failed, 187 warnings in 286.23 seconds**.
- Final `ccc` index: **1,047 indexed files / 1,059 listed**, zero errors, 28,563 chunks.
- Final codebase-memory: **14,952 nodes / 31,983 edges**, status `ready`.
- Final Graphify guarded export: **11,011 nodes / 17,606 edges / 961 communities / 126 hyperedges**; aggregated HTML exported with 961 community nodes + 1,426 cross-community edges. Saved semantic nodes and hyperedges were preserved.
- Final Word marker/probe cleanup completed. Host screenshot cleanup removed 60 expired artifacts and container cleanup removed the last deployed test image; both stores are empty.
- Final default printer remains `Brother HL-L2375DW series (redirected 1)`; final HP duplex remains `TwoSidedLongEdge`.
- All **57 tasks** are complete. No new runtime dependency was added, no commit or push was performed, and no post-implementation hooks are registered.

## Analysis remediation — 2026-11-21

The `/speckit.analyze` findings were remediated:

- Restored spec 003's research-page contract: `research_max_pages` default **3**, hard cap **5** (`src/agentic_rag_mcp/config.py`).
- Replaced two stale exact-global tool-count assertions with additive-preservation checks in `test_antv_contract.py` and `test_ppt_contract.py`; later additive tools no longer make historical contracts fail.
- Corrected six MCP-Action task module paths and T024 WaitFor/T048 green-suite wording in `tasks.md`.
- Updated plan drift: General-cloud + Hermes only, WaitFor printer-page verification, direct-write/managed-default wording, and the Dify contract test in the test tree.

Final verification after remediation:

- Complete Python suite: **1,245 passed, 0 failed, 187 warnings in 286.23 seconds**.
- Frontend: **26 files / 188 tests passed**; TypeScript passed; ESLint has one pre-existing `ONLY` warning.
- The constitution's 100%-green quality gate is now satisfied.

## T021 — Owner-present read-only Windows contract probe (PASS)

Date: 2026-11-20. An inline Python probe used 60-second waits and the existing Windows-MCP transport. No printer setting or registry value was changed; neither `SetDefaultPrinter` nor `Set-PrintConfiguration` was present in the probe command. No implementation or test files were changed.

### CIM exact-match, default read-back, and managed mode

- The existing `windows_mcp.client.call_tool` PowerShell lane returned `status=ok` in **5.475 s**, with no truncation and no consent wait surfaced by the wrapper. Its marked `MCP_ACTION_JSON:<Base64 UTF-8 JSON>` payload decoded and parsed successfully.
- CIM reported **6 installed printers**. The lowercase query `microsoft print to pdf`, transported as UTF-8 Base64 and compared to enumerated `Win32_Printer.Name` values with case-insensitive PowerShell `-eq`, produced **exactly one** canonical match: **`Microsoft Print to PDF`**. Microsoft Print to PDF is therefore installed.
- Two fresh CIM default-printer reads both returned **`HP LaserJet M610 TCPIP`**. The immediate read-back values were consistent, with one current per-user default and no mutation between reads.
- `HKCU\Software\Microsoft\Windows NT\CurrentVersion\Windows\LegacyDefaultPrinterMode` was read successfully as **DWORD 0**. This is interpreted as **Windows-managed default behavior enabled**, so a verified immediate default change may not persist. The value was only read; no registry write or mode change occurred.

### Raw Screenshot MCP contract

- Using the existing `sse_client(BRIDGE_SSE_URL, headers=_headers())` and `ClientSession` plumbing, `Screenshot` was invoked **exactly once** with `{}`. It returned in **0.485 s**, `isError=false`, with no `USER_CONTROL` wait or consent refusal and no retry.
- The response contained **2 content blocks**: one `text` block and one `image` block. Text/desktop content was not retained in this report.
- The real image block had **`mimeType=image/png`**, a present string containing valid Base64, **343,274 decoded bytes**, and PNG magic **`89 50 4e 47 0d 0a 1a 0a`**. The Base64 and decoded image bytes were inspected only in memory and were not written to the report or logs.

## T040 — Owner-present Word/duplex contract probe (PARTIAL)

Date: 2026-11-20. Two independent, bounded, single-attempt probes were run with the owner present. The Word probe used the existing `OfficeProxy` SSE transport primitives directly with a fixed inline `RunPython` template and a 30-second timeout, deliberately bypassing the retrying `call()` loop. The separate read-only Windows PowerShell probe used a 30-second command timeout, one consent attempt, and no retry. No implementation, unit-test, integration-test, or `tasks.md` changes were made.

### Word Print Preview and document evidence

- Transport completed in **5.740 s**, with exactly **one** `RunPython` attempt and a parsed fixed-template result. COM initialization succeeded.
- No `WINWORD.EXE` process was present when COM attach failed, so the no-Word branch started Word with `DispatchEx`; `started_word=true`, `attached_existing=false`. The running-but-COM-unregistered branch was **not exercised**. No second instance was started alongside an existing Word process.
- Word had **0 documents before** the probe. The template therefore created exactly **one blank document** through `Documents.Add()` and disclosed `blank_created=true`; afterward the count was **1**. No content was typed. The new unmodified blank document's COM `Saved` flag was **`true`**; it was not saved to disk and no `.Saved` assignment or save call occurred.
- Document metadata read-back was `before_count=0`, `after_count=1`, `before_saved=[]`, `after_saved=[true]`: `count_ok=true`, `saved_ok=true`, and `documents_preserved=true`. There were no pre-existing documents, so preservation of an existing document's content/`Saved` flag was **not exercised**. No document names, paths, or text were returned or logged.
- `Document.PrintPreview()` completed. Independent read-back returned **`PrintPreview=true`** and **`ActiveWindow.View.Type=4`** (`view_type_ok=true`).
- The active Word HWND was **857142** and `IsWindowVisible` plus `word.Visible` returned **`window_visible=true`**. After the ALT tap and `SetForegroundWindow`, `GetForegroundWindow` returned **267728**, so **`foreground=false`** and actual foreground verification **failed**. No Backstage/`ExecuteMso` fallback was attempted.
- No print, `PrintOut`, save, close, quit, dialog `Show`/`Display`, content edit, or existing-document mutation was performed. The new blank document and Word preview were left open for the owner.

### Read-only printer duplex and administrator capability

- PowerShell completed in **2.721 s**, with exactly **one** attempt and no output truncation. CIM produced exactly **one** case-insensitive exact match for **`HP LaserJet M610 TCPIP`**.
- `PrintManagement` is available. `Get-PrintConfiguration -PrinterName 'HP LaserJet M610 TCPIP'` succeeded and reported **`DuplexingMode=TwoSidedLongEdge`**.
- The current Windows principal's `IsInRole(Administrator)` returned **`false`**. Administrator-dependent setter capability is therefore **not established**; this was a read-only probe and no access-denied setter outcome was inferred or fabricated.
- No `Set-PrintConfiguration`, `SetDefaultPrinter`, registry write, elevation, rollback, or test-page print was attempted.

### Blockers / remaining live evidence

1. **Foreground verification failed**: Word Print Preview was visible but was not the actual foreground HWND.
2. **Existing-document preservation remains unproven in this run**: Word initially contained no documents, so only the permitted blank-document branch was exercised.
3. **Duplex mutation permission remains unproven**: the host principal was not in the Administrator role and, by instruction, no setter was called.
