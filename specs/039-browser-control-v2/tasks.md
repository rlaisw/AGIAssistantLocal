# Tasks: Browser Control v2 (spec 039)

**Input**: Design documents from `/specs/039-browser-control-v2/`

**Prerequisites**: plan.md, spec.md (5 user stories), research.md (R1–R5), data-model.md, contracts/README.md, test-plan.md, quickstart.md — all present.

**Tests**: included (Constitution II — tests-first house lifecycle; the spec's test-plan.md is an explicit deliverable).

**Organization**: Tasks grouped by user story from spec.md. US1 (workflow) spans the verb set; US2–US5 are the per-verb stories mapped to their phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US5 per spec.md

## Phase 1: Setup

- [X] T001 Create `tests/unit/test_browser_control_v2.py` with the schema-boundary pins from test-plan.md §1: key allowlist rejects unknown keys; wait bound 1..30 (0 and 60 rejected); form requires ≥1 field — expected RED
- [X] T002 [P] Create the local e2e fixture form page `tests/fixtures/workflow_form.html` (a name input, a country `<select>` with Hong Kong among options, a submit button that echoes a result) for the E1 battery

## Phase 2: Foundational (blocking prerequisites)

- [X] T003 Extend `src/agentic_rag_mcp/browser_lanes/proxy.py` with the shared `_screenshot_after_action()` helper: fires the engine's screenshot tool best-effort after any verb; a screenshot failure NEVER fails the action; returns the artifact reference (research R4)
- [X] T004 [P] Write the proxy verb pins in `tests/unit/test_browser_control_v2.py`: ask-back honesty (option/target not found lists what IS available), read-back by DISPLAYED value, sensitive values excluded from all log surfaces, screenshot-after-action firing order, unavailable/malformed engine envelopes — expected RED (mock transport)
- [X] T005 Implement the six proxy verb methods in `src/agentic_rag_mcp/browser_lanes/proxy.py` per contracts/README.md: `select(target, option)`, `type(target, text)`, `form(fields)`, `press_key(key)` (allowlist Enter/Escape/Tab/Arrow*), `tabs(action, target?)`, `wait(condition, text?, bound_s 1..30)` — each: engine call → read-back verify (where mechanical) → screenshot helper → honest ask-back/error envelopes; sensitive values never in summary/reason text

**Checkpoint**: proxy verbs green on mocks; ready for the tools.

---

## Phase 3: User Stories 2+3 — select and type/form (P1) 🎯 MVP core verbs

**Goal**: the two missing verbs that block real workflows.
**Independent Test**: quickstart E2/E3 — select-by-label lands the visible option; form-fill reports per-field honest results.

- [X] T006 [P] [US2] Register `browser_select_v2(target, option, conversation_id)` in `src/agentic_rag_mcp/server.py` — audit `browser-select-v2`; ask-back lists available options; screenshot ref in the return
- [X] T007 [P] [US3] Register `browser_type_v2(target, text, conversation_id)` + `browser_form_v2(fields, conversation_id)` in `src/agentic_rag_mcp/server.py` — typed values EXCLUDED from audit outcome text (R5); read-back verified; per-field results for form
- [X] T008 [P] [US4] Register `browser_press_key_v2(key, conversation_id)` in `server.py` — boundary allowlist enforced server-side too (defense in depth)

**Checkpoint**: the core verbs callable through the deployed sidecar (after the Phase 5 rebuild).

---

## Phase 4: User Stories 4+5 — tabs, wait, and the E1 workflow (P1/P2)

**Goal**: the workflow-complete surface + the headline battery.
**Independent Test**: quickstart E1 — the full navigate → type → select → click → read workflow with per-step screenshots.

- [X] T009 [P] [US4] Register `browser_tabs_v2(action, target?, conversation_id)` in `server.py` — one action per call; honest not-found lists open tabs
- [X] T010 [P] [US5] Register `browser_wait_v2(condition, text?, bound_s, conversation_id)` in `server.py` — bounded; honest timeout naming the awaited text
- [X] T011 [US1] Add the six tools to `dify/AGIAssistant/AGI_Assistant.yml` (Hermes lane list + tool descriptions with the verb vocabulary + the per-step screenshot presentation rule) — the browser-action routing rule from 2026-11-13 unchanged; YAML-plain-scalar-safe (no colon-space)
- [X] T012 [US1] Extend `tests/integration/test_browser_a2.py` with the A2 cases from test-plan.md §3: injected option text, pre-filled "ignore previous instructions" fields, page-instructed verb use — zero actions from content, honest reports, audit rows

**Checkpoint**: the full surface wired; adversarial pins in.

---

## Phase 5: Polish & Cross-Cutting

- [X] T013 Rebuild + publish: `.venv/bin/python -m agentic_rag_mcp.deploy redeploy` (47 → 53 tools) + `deploy chatflow` (the six tools + rules) — the Dify tool-cache staleness rule applies
- [X] T014 Live battery (E1 navigate/type/select/click/read ALL OK, E5 wait + honest timeout OK, sensitive value written+masked, not logged) per quickstart/test-plan: E1 the full workflow on the T002 fixture page (per-step screenshots presented in order), E2 select-by-label, E4 tabs, E5 wait-for + honest timeout, the sensitive-field check (value absent from audit JSONL) — record durations in the audit rows
- [X] T015 [P] Run `ruff` on touched sources + full pytest suite green minus the 3 known pre-existing failures; commit + push

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1–2**: T001/T002 [P] alongside; T003 → T004 → T005 sequential (the helper before the verbs)
- **Phase 3–4**: the tool registrations (T006–T010) [P] after T005; the DSL (T011) after all six exist; T012 parallel with T011 (different files)
- **Polish**: T013 after all phases; T014 after T013; T015 last

### User story dependencies

- US2/US3/US4 (the verbs): mutually independent after Phase 2
- US5 (wait/tabs): independent
- US1 (the workflow + E1 battery): needs all six verbs (T006–T010) + the DSL wiring
- US-4 screenshots: implemented once as the T003 helper (shared by all verbs)

### Parallel opportunities

- T006 ∥ T007 ∥ T008 ∥ T009 ∥ T010 (each tool is an independent server.py block, no shared state beyond the existing proxy singleton)
- T002 ∥ T001; T012 ∥ T011

## Implementation Strategy

### MVP First

1. Phase 1–2 foundation (helper + verbs, red-first pins)
2. The core verbs (select, type/form) — Phase 3 → validate E2/E3
3. **STOP and VALIDATE** the core verbs live

### Incremental delivery

4. Tabs/wait + the DSL + A2 — Phase 4 → validate E4/E5 + A2
5. Rebuild/publish + the full E1 workflow battery — Phase 5 (the headline: per-step screenshots)

## Notes

- Tests are NOT optional (Constitution II); the suites are red-first
- The screenshot helper fires on EVERY verb call — the owner-required step capture (FR-010) is implemented once, shared
- Sensitive values: excluded from summary/audit/error surfaces at THREE layers (proxy, tool, description) — pinned in T004
- The E1 fixture (T002) keeps the battery hermetic — no public sites needed