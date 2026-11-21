---

description: "Task list for MCP-Action confirmed desktop automation"

---

# Tasks: MCP-Action — Confirmed Desktop Automation

**Input**: Design documents from `specs/047-mcp-action/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Tests are explicitly requested. Write the listed tests first, confirm the expected red failure, then implement only enough code to make them pass. Every implementation task also runs its relevant focused test before being marked complete.

**Organization**: User Story 1 delivers the default-printer MVP and the shared execution/evidence plumbing. User Story 2 adds Word duplex by extending that delivered plumbing; it does not duplicate proposal, locking, screenshot, or Dify infrastructure.

**Owner-approved T012 scope amendment**: MCP-Action is limited to General-cloud and Hermes. General-local failed the live dispatch gate and is restored to its original node, prompts, and Answer path; earlier references to three wired agents are superseded.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other tasks at the same gate (different files, no incomplete dependencies).
- **[Story]**: US1 = default-printer journey; US2 = Word duplex journey.
- All paths are repository-relative. Live tasks require the owner present and must restore original printer/document state in `finally`.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the feature package, sanitized fixtures, and a baseline against which regressions are measured.

- [X] T001 Create the `src/agentic_rag_mcp/mcp_action/` package with `__init__.py`, `state.py`, `actions.py`, `service.py`, and `screenshots.py` containing only documented placeholders, plus empty focused test files under `tests/unit/` matching `test_mcp_action_*.py`
- [X] T002 [P] Add sanitized Dify dialogue-count/tool-iteration fixtures, mixed text/image MCP responses, tiny PNG/JPEG samples, malicious printer-name cases, and malformed/CLIXML payloads under `tests/fixtures/mcp_action/` without real tokens, document names, desktop images, or credentials
- [X] T003 [P] Record baseline Python unit/contract results, frontend Vitest/typecheck/lint results, and any pre-existing failures in `specs/047-mcp-action/test-report.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Deliver and live-prove the consent/tool/DSL contract shared by both stories. No action-specific execution may begin until T012 passes.

### Foundational tests (write first)

- [X] T004 [P] Add proposal tests covering one pending proposal per conversation, supersession, closed parameters, printer `trimmed, non-empty, no NUL/CR/LF, bounded length`, orientation `"long-edge" | "short-edge"`, plain response classification, confirm/cancel exactly `N+1`, 899.99-second acceptance/900-second expiry, wrong-conversation protection, modified/unrelated-turn invalidation, atomic duplicate confirm, opportunistic expiry cleanup, and restart fail-closed behavior in `tests/unit/test_mcp_action_state.py`
- [X] T005 [P] Add public tool tests for additive `mcp_action` schema and draft/cancel envelopes in `tests/unit/test_mcp_action_tool.py`, plus additive registration and unchanged existing-schema checks in `tests/contract/test_mcp_contract.py`; pin exact offer `Do you want me to do it automatically for you?`, `expires_in_s=900`, zero draft mutation/display/screenshot calls, and rejection of `action_id`/`parameters` on confirm/cancel
- [X] T006 [P] Add DSL tests for `mcp_action` on `agentic_strategy` and `hermes_agent`, with `agentic_strategy_local` and PPT-Master explicitly excluded, raw `sys.query`/`sys.dialogue_count`/`sys.conversation_id` wiring, no PPT-Master registration, no generic yes/no router change, and shared honesty-guard cases in `tests/unit/test_mcp_action_dsl.py`
- [X] T007 [P] Add a replay regression proving a saved skill cannot pre-confirm or execute `mcp_action` in `tests/unit/test_skill_executor.py`

### Foundational implementation and live gate

- [X] T008 Implement the in-memory proposal store and raw-response/turn/expiry validation from T004 in `src/agentic_rag_mcp/mcp_action/state.py`, keeping the short state lock synchronous and never held across `await`, removing terminal/expired proposals, and preserving another conversation's proposal on wrong-conversation confirmation
- [X] T009 Implement draft/cancel orchestration and sanitized `pending-confirmation`/`ask-back`/`unsupported`/`cancelled`/`blocked`/`error` envelopes in `src/agentic_rag_mcp/mcp_action/service.py`, register the additive tool in `src/agentic_rag_mcp/server.py`, and leave confirm execution explicitly unimplemented until T012 passes
- [X] T010 Wire the tool and shared ask-first/manual-steps/draft/offer/next-turn protocol into General-cloud Agentic Strategy and Hermes, add those two outputs to the existing multi-input honesty node, require a real `mcp_action` pending result for the exact offer, detect leaked `mcp_action` calls, and preserve existing Hermes-specific claims in `dify/AGIAssistant/AGI_Assistant.yml`
- [X] T011 [P] Add `mcp_action` to the replay-gated tool set in `src/agentic_rag_mcp/skill_manager/executor.py` so skill replay always requires the tool's own live confirmation
- [X] T012 Add and run an opt-in live contract probe in `tests/integration/test_mcp_action_dify_contract.py`, recording in `specs/047-mcp-action/test-report.md` that General-cloud and Hermes see dialogue count `N` at draft and `N+1` on the next user turn and that the shared guard selects only the active agent; **STOP and request owner approval for a different deterministic resolver if this fails**

**Checkpoint**: The exact proposal contract is implemented, advertised, and live-proven. No printer or Word mutation is enabled yet.

---

## Phase 3: User Story 1 — Choose manual or automatic default-printer help (Priority: P1) 🎯 MVP

**Goal**: After manual instructions and the exact offer, a next-turn plain yes changes only the named default printer, verifies it, shows Printers settings, and returns an inline temporary screenshot; no and all invalid confirmations do nothing.

**Independent Test**: With test printers A/B/C, prove decline leaves A default, accept changes A→B with before/after verification and visible evidence, modified confirmation requires a new proposal, and original settings are restored in `finally` (quickstart E01–E03, E08–E11, E17–E21).

### Tests for User Story 1 (write first)

- [X] T013 [P] [US1] Add default-printer tests for UTF-8 Base64 literal transport, wildcard/quote/`$()`/backtick/Unicode names, exactly one case-insensitive exact match, no current default, zero/multiple matches, printer removal, `SetDefaultPrinter` return `0` requirement, already-active `ok/changed:false`, fresh after-read mismatch, managed-default caveats without registry writes, marked JSON with CLIXML noise, and after-read on setter exceptions in `tests/unit/test_mcp_action_actions.py`
- [X] T014 [P] [US1] Add async orchestration tests proving one server-wide desktop lock gives `max_active == 1`, state locks never cross `await`, queue/execution timings stay separate, the full 60-second action budget must remain inside 240 seconds, queued-timeout never executes, duplicate confirms execute once, display/capture finish before release, and exceptions/unknown host outcomes never blind-retry in `tests/unit/test_mcp_action_concurrency.py`
- [X] T015 [P] [US1] Extend Windows-MCP tests for opt-in mixed text/image extraction, default `include_images=False` compatibility, exactly one valid image, bounded consent behavior, missing/multiple/malformed/oversized image failures, and no binary audit leakage in `tests/unit/test_windows_mcp_lane.py`
- [X] T016 [P] [US1] Add screenshot-store tests for `secrets.token_urlsafe(32)` and exact `[A-Za-z0-9_-]{43}` tokens, PNG/JPEG magic-byte validation, 10 MiB cap, `0700` directory/`0600` files, absolute 900-second TTL, 30-second janitor, no GET renewal/first-read deletion, traversal rejection, and startup/shutdown cleanup in `tests/unit/test_mcp_action_screenshots.py`
- [X] T017 [P] [US1] Add route contracts for exact image bytes/MIME, repeated immediate GETs, all no-store/security/CORS headers, indistinguishable malformed/unknown/expired-token 404, non-GET 405 + `Allow: GET`, expiry deletion, and no Base64/local path in tool results in `tests/contract/test_mcp_action_screenshot_route.py`
- [X] T018 [P] [US1] Extend redaction tests so application/access logs preserve the route prefix but never persist the 43-character capability token, URL, local path, Base64, document name, desktop text, or executable payload in `tests/unit/test_logging_setup.py`
- [X] T019 [P] [US1] Add Vitest coverage proving upstream `no-store` remains `no-store` while ordinary images retain `public, max-age=3600` in `ai-chat-landing/app/api/image-proxy/route.test.ts`, and pin the exact MCP-action question through `splitFollowUp` in `ai-chat-landing/lib/follow-up.test.ts`
- [X] T020 [P] [US1] Add owner-present guards and default-printer E2E cases E01–E03 and E08–E11 in `tests/integration/test_mcp_action_e2e.py`, including original-default capture/restoration in `finally`, no test printing, before/after read-back, visible Settings, loaded screenshot, sanitized audit, and ordinary generic-follow-up regression checks
- [X] T021 [US1] With the owner present, run read-only CIM/default/managed-mode probes and one raw Windows-MCP Screenshot contract probe, recording exact-match/read-back behavior and the real image `mimeType`/Base64 shape in `specs/047-mcp-action/test-report.md`; do not change printer settings during this probe

### Implementation for User Story 1

- [X] T022 [US1] Implement only `windows_default_printer` in `src/agentic_rag_mcp/mcp_action/actions.py`: closed printer validation, fixed PowerShell/CIM templates with UTF-8 Base64 name transport and marked Base64 JSON results, exactly one exact match, per-user `SetDefaultPrinter`, fresh before/after reads, already-active handling, managed-default caveat, and sanitized partial-state-aware errors without `rundll32`, raw WQL interpolation, registry writes, auto-elevation, or automatic rollback
- [X] T023 [US1] Implement confirmed execution orchestration in `src/agentic_rag_mcp/mcp_action/service.py`: atomically consume the stored proposal, one desktop-wide `asyncio.Lock` from before-read through display/capture, 240-second total/60-second action budgets, queue timeout without execution, structured `ok`/`partial`/`queued-timeout`/`error` outcomes, sanitized audit, and no release while host work may still run
- [X] T024 [US1] Add the reviewed `printers` target to `src/agentic_rag_mcp/windows_mcp/targets.py` and integrate Settings opening plus host-side `WaitFor` printer-page verification in `src/agentic_rag_mcp/mcp_action/service.py`, returning `skipped-display-unverified` instead of capturing an unrelated window
- [X] T025 [P] [US1] Add opt-in `ImageContent` extraction and bounded consent controls to `src/agentic_rag_mcp/windows_mcp/client.py`, preserving existing response shapes and defaults unless `include_images=True` and returning exactly one validated image only to MCP-Action
- [X] T026 [P] [US1] Implement temporary image validation/storage/resolution/janitor logic in `src/agentic_rag_mcp/mcp_action/screenshots.py` with 256-bit tokens, private container `/tmp`, PNG/JPEG magic checks, 10 MiB cap, `0700`/`0600` modes, 900-second absolute TTL, 30-second sweep, and no metadata database
- [X] T027 [US1] Add `GET /mcp-action/screenshots/{token}` and lifespan startup/shutdown/30-second cleanup to `dify/docker/mcp-server/server.py`, deriving the public origin from `ppt_exports_url_base` and returning the contract's exact 200/404/405 and `Cache-Control: no-store`, `Pragma: no-cache`, `Expires: 0`, CORS, CORP, `nosniff`, and inline headers
- [X] T028 [P] [US1] Add capability-token redaction for `/mcp-action/screenshots/{token}` to `src/agentic_rag_mcp/logging_setup.py` while preserving the route prefix and all existing credential redactions
- [X] T029 [P] [US1] Preserve upstream `no-store` in `ai-chat-landing/app/api/image-proxy/route.ts` and retain `public, max-age=3600` only when the upstream response does not forbid caching
- [X] T030 [US1] Extend default-printer prompt behavior and MCP-action execution/verification/display/screenshot honesty checks in `dify/AGIAssistant/AGI_Assistant.yml`, including manual steps before offer, no offer for unsupported procedures, actual before/after reporting, inline `screenshot.image_url` exactly once only when `status == "captured"`, and no screenshot-only success claims
- [X] T031 [P] [US1] Add `mcp_action` to the required deployed tool-surface checks in `src/agentic_rag_mcp/deploy/battery.py` without changing unrelated tool assertions
- [X] T032 [US1] Create `ai-chat-landing/scripts/mcp-action-check.mjs` to drive fresh-conversation default-printer no/yes/modified/orphan/generic-follow-up journeys, assert manual steps and exact offer order, and require a loaded inline screenshot with `naturalWidth > 0` only after confirmed success
- [X] T033 [US1] Run all US1-focused Python, contract, DSL, and frontend tests plus existing Windows/skill/honesty regressions, fixing feature code rather than weakening tests and recording results in `specs/047-mcp-action/test-report.md`
- [X] T034 [US1] With the owner present, run the US1 live matrix in `tests/integration/test_mcp_action_e2e.py` and `ai-chat-landing/scripts/mcp-action-check.mjs`, record execution/queue timings, visible/read-back/screenshot/audit/privacy evidence, and restore the original default printer in `finally` in `specs/047-mcp-action/test-report.md`

**Checkpoint**: US1 is independently deployable as the MVP. A user can choose manual or automatic default-printer help with verified, visible, temporary evidence and no stale/concurrent execution.

---

## Phase 4: User Story 2 — Choose manual or automatic Word duplex help (Priority: P2)

**Goal**: After manual instructions and explicit printer-wide/orientation disclosure, a next-turn plain yes applies only the confirmed duplex mode, verifies it, preserves Word documents, shows Print Preview, and returns temporary inline evidence.

**Independent Test**: With a duplex-capable test printer and an unsaved disposable Word document, prove no does nothing, yes applies and verifies long-edge then short-edge, already-active reports no change, unsupported/permission/busy cases are honest, unsaved content remains unchanged, and original duplex settings are restored in `finally` (quickstart E04–E06, E10, E12–E17, E21).

### Tests for User Story 2 (write first)

- [X] T035 [P] [US2] Extend `tests/unit/test_mcp_action_actions.py` with closed duplex parameters, exact orientation mapping `"long-edge" | "short-edge"` → `TwoSidedLongEdge | TwoSidedShortEdge`, unsupported printer/mode, missing PrintManagement, administrator access denied, no auto-elevation/test page/rollback, already-active behavior, and after-read on setter errors/mismatch
- [X] T036 [P] [US2] Extend `tests/unit/test_office_v2.py` with fixed-template assertions for COM initialization, attach-before-Dispatch, Dispatch only when no Word process exists, `Document.PrintPreview()`, `PrintPreview` + `ActiveWindow.View.Type == 4` + visible/foreground HWND verification, blank-document disclosure, document count/`Saved` preservation, bounded no-retry behavior, and absence of `PrintOut`, `Save`, `Close`, `Quit`, dialog `Show/Display`, or `.Saved` assignment
- [X] T037 [P] [US2] Extend `tests/unit/test_mcp_action_tool.py` with Word orchestration cases for printer-wide/blank-document disclosures, the shared 90-second action budget, `asyncio.to_thread` responsiveness, busy/modal/timeout without blind Backstage fallback, preview-versus-foreground partial outcomes, screenshot skip on unverified display, and sanitized audit/error envelopes
- [X] T038 [P] [US2] Extend `tests/unit/test_mcp_action_dsl.py` with Word manual-steps/offer/orientation/printer-wide disclosure prompts, exact stored-proposal confirmation, result/honesty claims, unsupported Office procedures remaining manual-only, and no skill-loop detour
- [X] T039 [P] [US2] Extend `tests/integration/test_mcp_action_e2e.py` with opt-in Word cases E04–E06, E10, and E12–E17 using a disposable unsaved marker document, duplex-capable test printer, no print job, document preservation assertions, and original-duplex restoration in `finally`
- [X] T040 [US2] With the owner present, probe the actual Word PrintPreview/View.Type/HWND/document-preservation behavior and duplex permission/read-back using a disposable unsaved document and test printer, recording results in `specs/047-mcp-action/test-report.md`; exercise Backstage only if legacy preview is explicitly unsupported and never save, close, print, or alter content

### Implementation for User Story 2

- [X] T041 [P] [US2] Add only `word_printer_duplex` to `src/agentic_rag_mcp/mcp_action/actions.py`, using exact printer validation, fixed `Set-PrintConfiguration -Confirm:$false`/`Get-PrintConfiguration` templates, the two reviewed orientation mappings, fresh before/after reads, and sanitized permission/capability/mismatch/partial-state results without elevation, test printing, or automatic rollback
- [X] T042 [P] [US2] Add the fixed Word template and `OfficeProxy.show_word_print()` in `src/agentic_rag_mcp/office_lanes/proxy.py`, with attach-first COM, no second instance when Word is running but unregistered, blank-document creation only after confirmation and disclosed in the result, PrintPreview/View.Type/HWND/document-metadata verification, and a bounded no-retry call path that leaves existing OfficeProxy defaults unchanged
- [X] T043 [US2] Integrate Word execution/display in `src/agentic_rag_mcp/mcp_action/service.py`, calling the blocking Office helper through `asyncio.to_thread` under the existing desktop lock and 90-second action budget, using Backstage only for explicitly unsupported PrintPreview with UI-tree confirmation, and distinguishing mutation, verification, preview, foreground, screenshot, busy/modal, and unknown-transport outcomes
- [X] T044 [US2] Extend Word-specific prompts and honesty checks in `dify/AGIAssistant/AGI_Assistant.yml` so the offer/result disclose printer-wide scope and orientation, missing information triggers ask-first, document/preview/display/screenshot claims require corresponding tool evidence, and no Word content/save/close/print action is claimed
- [X] T045 [US2] Extend `ai-chat-landing/scripts/mcp-action-check.mjs` with Word no/yes/long-edge/short-edge/already-active/unsupported journeys and assertions for visible Print Preview, preserved marker document, printer-wide result text, and loaded temporary screenshot
- [X] T046 [US2] Run all US2-focused and US1 regression Python/contract/DSL/frontend tests, fixing feature code rather than weakening tests and recording results in `specs/047-mcp-action/test-report.md`
- [X] T047 [US2] With the owner present, run the US2 live matrix in `tests/integration/test_mcp_action_e2e.py` and `ai-chat-landing/scripts/mcp-action-check.mjs`, record duplex read-back, permission/capability outcomes, Word preservation/display/screenshot/audit/timing evidence, and restore original duplex settings in `finally` in `specs/047-mcp-action/test-report.md`

**Checkpoint**: US1 and US2 both work independently on their reference actions while sharing one consent, execution, evidence, and honesty implementation.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Prove the complete acceptance matrix, preserve all existing behavior, publish both apps, and leave auditable evidence without retaining sensitive artifacts.

- [X] T048 Run the complete Python unit/contract suites, all relevant integration contract probes, and frontend `pnpm test`, `pnpm typecheck`, and `pnpm lint`, recording exact counts and achieving a fully green suite with zero failures in `specs/047-mcp-action/test-report.md`
- [X] T049 Run cross-story concurrency/error cases E17–E20 from `specs/047-mcp-action/quickstart.md`, proving one active desktop execution, duplicate-confirm blocking, queue timing/timeout honesty, expiry without execution, repeated screenshot GET/no-store, expired-token 404, and token/path/Base64-free audit/logs in `specs/047-mcp-action/test-report.md`
- [X] T050 Use the safe `redeploy` + explicit-ID publish + `verify` equivalent instead of name-based `deploy all` for app IDs `194e1edf-2eba-442c-b10b-231bebb79c37` and `7863fbe2-47f8-48c9-b096-6f7da8536b08`, recording sidecar/tool-sync/headless-battery evidence and the pre-existing office-routing scenario/spec-045 mismatch in `specs/047-mcp-action/test-report.md`
- [X] T051 Run the complete CDP/performance acceptance in `ai-chat-landing/scripts/mcp-action-check.mjs` and `specs/047-mcp-action/quickstart.md`, evaluating 60/90-second execution targets separately from queueing, user-facing before/after/verification/display/screenshot clarity, and final printer/document restoration in `specs/047-mcp-action/test-report.md`
- [X] T052 [P] Document the delivered MCP-Action scope, exact consent/expiry/serialization behavior, temporary screenshot route/privacy caveat, tests, and deployment commands in `AGENTS.md` and `ai-chat-landing/AGENTS.md` without changing unrelated feature documentation
- [X] T053 Refresh `graphify-out/graph.json` using `graphify update .` and the documented manual runbook if the known saved-semantic-node guard fires, then rebuild the `ccc` and codebase-memory indexes and record refreshed artifact/index status in `specs/047-mcp-action/test-report.md`
- [X] T054 Reconcile every FR-001–FR-025 and SC-001–SC-007 against evidence in `specs/047-mcp-action/test-report.md`, explicitly mark any environment-blocked live row for owner sign-off, verify no temporary screenshots/test documents/unrestored printer changes remain, and leave no unresolved dishonest-success or regression finding

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001–T003)**: Starts immediately; T002/T003 may run in parallel after T001 establishes the package/test layout.
- **Foundational (T004–T012)**: Depends on Setup and blocks all execution work. T008 requires T004; T009 requires T005 + T008; T010 requires T006 + T009; T011 requires only T007 and may parallel T008–T010; T012 requires T009 + T010 and is a hard stop gate.
- **US1 (T013–T034)**: Depends on T012. Tests T013–T020 run first; T021 is the live read-only probe gate. Implementation dependencies are listed below. T033/T034 must pass before the MVP is considered delivered.
- **US2 (T035–T047)**: Depends on delivered US1 shared execution/display/screenshot infrastructure. Tests T035–T039 run first; T040 is the Word probe gate. T046/T047 must pass independently.
- **Polish (T048–T054)**: Depends on all desired stories. T052 may parallel validation tasks; T053 waits for code and documentation changes; T054 is last.

### Within User Story 1

- T022 requires T013 + T021.
- T023 requires T014 + T022.
- T024 requires T023.
- T025 requires T015 + T021 and may parallel T022–T024.
- T026 requires T016 and may parallel T022–T025.
- T027 requires T017 + T026.
- T028 requires T018 and may parallel T022–T027.
- T029 requires T019 and may parallel T022–T028.
- T030 requires T024 + T027 + T029.
- T031 requires T010 and may parallel other US1 implementation work.
- T032 requires T030; T033 requires T022–T032; T034 requires T033.

### Within User Story 2

- T041 requires T035 + T040; T042 requires T036 + T040 and may parallel T041.
- T043 requires T037 + T041 + T042.
- T044 requires T038 + T043; T045 requires T044.
- T046 requires T041–T045; T047 requires T046.

### Parallel Opportunities

- Setup: T002 + T003.
- Foundational tests: T004 + T005 + T006 + T007; T011 may parallel T008–T010.
- US1 tests: T013 + T014 + T015 + T016 + T017 + T018 + T019 + T020.
- US1 independent implementation files after their gates: T025 + T026 + T028 + T029 + T031.
- US2 tests: T035 + T036 + T037 + T038 + T039; T041 + T042 after T040.
- Polish: T052 can run alongside T048–T051.

## Parallel Example: User Story 1

```text
After T012, launch together:
Task: "T013 Add default-printer action tests in tests/unit/test_mcp_action_actions.py"
Task: "T014 Add concurrency tests in tests/unit/test_mcp_action_concurrency.py"
Task: "T015 Extend Windows-MCP image tests in tests/unit/test_windows_mcp_lane.py"
Task: "T016 Add screenshot-store tests in tests/unit/test_mcp_action_screenshots.py"
Task: "T017 Add screenshot route contracts in tests/contract/test_mcp_action_screenshot_route.py"
Task: "T018 Extend log-redaction tests in tests/unit/test_logging_setup.py"
Task: "T019 Add frontend cache/follow-up tests in ai-chat-landing/"
Task: "T020 Add default-printer live guards/cases in tests/integration/test_mcp_action_e2e.py"
```

## Parallel Example: User Story 2

```text
After US1, launch together:
Task: "T035 Extend duplex action tests in tests/unit/test_mcp_action_actions.py"
Task: "T036 Extend Word proxy tests in tests/unit/test_office_v2.py"
Task: "T037 Extend Word orchestration tests in tests/unit/test_mcp_action_tool.py"
Task: "T038 Extend Word DSL tests in tests/unit/test_mcp_action_dsl.py"
Task: "T039 Extend Word live cases in tests/integration/test_mcp_action_e2e.py"

After T040 and the relevant tests:
Task: "T041 Implement duplex handler in src/agentic_rag_mcp/actions.py"
Task: "T042 Implement Word display helper in src/agentic_rag_mcp/office_lanes/proxy.py"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete T001–T012 and stop if the Dify next-turn gate cannot be proven.
2. Complete T013–T034.
3. Validate default-printer no/yes/modified/error journeys independently, including temporary inline evidence and restoration.
4. Deliver/demo the default-printer MVP before adding Word duplex.

### Incremental Delivery

1. Setup + Foundational delivers a safe but non-mutating proposal/tool contract.
2. US1 adds the first complete automatic action and all shared execution/evidence plumbing.
3. US2 adds only the duplex handler, Word display helper, story-specific orchestration/prompts, and tests.
4. Polish proves the combined matrix, publishes both Dify apps, refreshes documentation/indexes, and reconciles every requirement.

## Notes

- Do not add a runtime dependency, database, generic pre-router, arbitrary PowerShell/COM/UI executor, production chat-renderer change, or additional Office/Windows action without owner approval.
- Never weaken consent, verification, privacy, or honesty tests to obtain a green result.
- A screenshot is supporting evidence only; fresh after-state read-back is authoritative.
- Temporary screenshot capability URLs are unauthenticated until expiry in the current single-user deployment; do not expose them beyond the intended answer or persistent logs.
- Stop at each story checkpoint and validate independently before continuing.

## Phase 6: Convergence

- [X] T055 Enrich the MCP-Action audit with verification, display, and screenshot outcomes plus display/capture stage timings in `src/agentic_rag_mcp/mcp_action/service.py`, adding red-first assertions in `tests/unit/test_mcp_action_tool.py` while excluding image URLs, tokens, paths, bytes, and desktop text per FR-021 (partial)
- [X] T056 Add an opt-in service-side benchmark in `tests/integration/test_mcp_action_e2e.py` that measures at least 20 runs per action from execution start through verified display, reports 95th-percentile latency and queue wait separately with original settings restored, and documents the result in `specs/047-mcp-action/test-report.md` per SC-004 (partial)
- [X] T057 Add capture-scope evidence and relevant-window region capture when bounds are available, with an explicit full-display fallback disclosure, in `src/agentic_rag_mcp/mcp_action/service.py`, `specs/047-mcp-action/contracts/mcp-action.md`, and the screenshot contract/unit tests per FR-016 (partial)
