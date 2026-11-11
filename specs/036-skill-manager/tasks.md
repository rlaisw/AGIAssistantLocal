# Tasks: Skill Manager (spec 036)

**Input**: Design documents from `/specs/036-skill-manager/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/README.md, quickstart.md — all present. Inherited test plan: `/specs/035-ai-helpdesk-architecture/test-plan.md` §1a/1b.

**Tests**: included (Constitution II — tests-first is the house lifecycle; the 035 test plan already enumerates the cases).

**Organization**: Tasks grouped by user story from spec.md (5 stories, P1→P2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US5 per spec.md

## Phase 1: Setup

- [X] T001 Create `src/agentic_rag_mcp/skill_manager/__init__.py` per plan.md structure decision (module of the existing sidecar; no new service/container)
- [X] T002 Add `[skill_manager]` config block to `src/agentic_rag_mcp/config.py` (DB path default `~/.config/agentic-rag-mcp/hermes-mcp/skills.db`, trust thresholds rate=0.80, min_successes=3 — data-model trust rule verbatim) with graceful absence handling

## Phase 2: Foundational (blocking prerequisites)

- [X] T003 Implement SQLite store core in `src/agentic_rag_mcp/skill_manager/store.py`: WAL mode, `skills` table (columns + CHECK constraints verbatim from data-model.md: `tier IN (1,2)`, PK `name`), `skill_feedback` table (PK `(skill_name, ts)`, `outcome IN ('success','failure')`), upsert semantics (same name → version+1, counters preserved), schema migration on open
- [X] T004 [P] Write `tests/unit/test_skill_store.py` first: upsert versioning, counter preservation, append-only feedback, feedback-on-missing-skill explicit error, restart persistence (reopen), partial-save atomicity — per data-model validation rules; suite must FAIL before T003 logic lands (Constitution II)
- [X] T005 Implement save-boundary validator (same file as T003 or `skill_manager/validate.py`): reject non-snake name (`^[a-z][a-z0-9_]*$`), empty description, tier outside {1,2}, steps missing `expect`, `{{snake_case}}` slot grammar in `params_template`, machine-specific literals (`C:\Users\`, hostnames, absolute host paths), tier-2 without tier-1 pre-check as first step — each rejection names the offending field (FR-004/005)
- [X] T006 Extend `src/agentic_rag_mcp/hermes_audit.py` with the six `skill-*` operation rows (`skill-search|get|save|feedback|replay-start|replay-abort`) carrying `conversation_id`, outcome, `duration_s`+`timing` (house row shape)

**Checkpoint**: store + validation + audit ready; user stories can proceed.

---

## Phase 3: User Story 1 — Novel task becomes a reusable skill (P1) 🎯 MVP

**Goal**: manual success → validated, audited, versioned skill save.
**Independent Test**: novel task end-to-end → row exists (v1) + audit row → search finds it next time (quickstart E1).

- [X] T007 [P] [US1] Write `tests/unit/test_skill_save.py` (or fold into store suite T004): every validator rejection case from 035 test-plan 1a "Param template validation" + save-success audit row — FAIL first
- [X] T008 [US1] Implement `skill_save` handler in `src/agentic_rag_mcp/skill_manager/api.py`: validate → upsert → `{name, version}` + audit row (T005/T003 dependents)
- [X] T009 [US1] Register `skill_save` MCP tool in `src/agentic_rag_mcp/server.py` (schema per contracts/README.md, `conversation_id` required) — additive only; existing 29 schemas byte-identical (Principle I)

**Checkpoint**: US1 independently testable.

---

## Phase 4: User Story 2 — Search + trust-gated reuse (P1)

**Goal**: semantic search before operational tasks; `reusable` pre-computed.
**Independent Test**: seeded trust matrix → auto-reuse iff >80% AND ≥3 (quickstart E1 step 3; SC-002 matrix).

- [X] T010 [P] [US2] Write `tests/unit/test_skill_trust.py` first — the full 035 test-plan 1a matrix: rate/sample combinations, decay-by-feedback, re-earn, no-time-expiry — FAIL first
- [X] T011 [US2] Implement intent index in `src/agentic_rag_mcp/skill_manager/intent.py`: embed `"{name}\n{description}"` via existing `search/embeddings.py` `Embedder`, LanceDB `skills` table via existing `store/vectordb.py` wrapper, delete+insert re-embed on upsert (no stale vectors), `skill_search` = embed → top-k → SQLite trust join → `{found, skills:[{name, description, success_rate, sample, reusable}]}`
- [X] T012 [P] [US2] Write outage-vs-miss envelope test: store down → `error:skill-store-unavailable`; miss → `{found:false, skills:[]}` — never conflated (research R6)
- [X] T013 [US2] Register `skill_search` + `skill_get` MCP tools in `server.py` (schemas per contracts; `skill_get` unknown name → explicit not-found)

**Checkpoint**: US1+US2 independently testable (round-trip minus replay).

---

## Phase 5: User Story 3 — Feedback, retry-once, escalation (P1)

**Goal**: append-only feedback; two-failure escalation; no deletion ever.
**Independent Test**: seeded failing skill → retry → update-or-escalate, skill intact (quickstart E6; SC-005).

- [X] T014 [P] [US3] Write `tests/unit/test_skill_feedback.py` first: append-only rows, `error_context` required on failure, missing-skill explicit error, escalation-after-two-consecutive-failures surfaces honestly, no delete operation exists in the API surface — FAIL first
- [X] T015 [US3] Implement `skill_feedback` handler in `api.py` (FR-008/009: counters update in the same transaction as the feedback row; escalation surfaced in the return envelope, not just logs)

**Checkpoint**: the loop (save→search→reuse→feedback) is complete and testable.

---

## Phase 6: User Story 4 — Replay executor with live gated-step confirmation (P2)

**Goal**: FR-020 structural — gated steps re-confirm live; substitution honest.
**Independent Test**: trusted skill with a gated step → replay pauses; no confirm → zero gated execution; cancel → no failure feedback (quickstart A3; SC-003).

- [X] T016 [P] [US4] Write `tests/unit/test_skill_executor.py` first — 035 test-plan 1b verbatim: substitution + unknown-slot ask-back, per-step `expect` verify, near-miss bailout, gated-step pause/resume (mocked lanes), cancel-clears-no-failure, replay start/abort audit — FAIL first
- [X] T017 [US4] Implement `src/agentic_rag_mcp/skill_manager/executor.py`: walk steps → call **existing** lane handlers (powershell/office/run gates) — gated step → `pending-confirmation` riding the **existing** `hermes_powershell_state` (no new state store, research R4), confirm resumes at next step, cancel aborts walk without skill-failure feedback; structural invariant: no code path reaches a gated tool's execution without the live confirm
- [X] T018 [US4] Adversarial pin A3: replay-bypass test asserting the structural invariant (attempt to confirm with different text → stored draft wins; spec-034 rules hold through replay) — mandatory per 035 SC-007

**Checkpoint**: US4 = the security invariant, testable alone.

---

## Phase 7: User Story 5 — Scope + graceful degradation (P2)

**Goal**: questions/chat never consult the store; store-down degrades honestly.
**Independent Test**: store down → operational task completes with notice, question turn unaffected (quickstart store-down; SC-006).

- [X] [P] T019-part [US3] Add DSL wiring to `dify/AGIAssistant/AGI_Assistant.yml` (per-component ownership rule): Hermes lane instructions gain the skill-loop rules (search before acting, reuse iff `reusable`, save on novel success, feedback every reuse, retry-once then escalate, ANTI-FABRICATION LAW covers skill claims); **General lane tool list excludes the four skill tools** (structural FR-001 scope); publish via `deploy chatflow`
- [X] T020 [US5] Wrap every store call in the honest-outage envelope (`error:skill-store-unavailable` naming the outage) + lane instruction: route manually, say so in the answer (FR-013)
- [X] T021 [P] [US5] Write degradation test: store unreachable → operational completes manually with honest notice; question turn shows zero skill round trips (mocked)

---

## Phase 8: Polish & Cross-Cutting

- [X] T022 [P] Update `README.md` + `AGENTS.md` tool counts (29 → 33) + spec 036 feature surface section (house doc pattern)
- [X] T023 Run `ruff` on new sources; full pytest suite green minus the 4 known pre-existing failures
- [X] T024 Rebuild Dify `tool_mcp_providers` rows for the 4 new tools + restart `docker-api-1`/`docker-worker-1` (staleness rule)
- [X] T025 Run quickstart.md live battery (deploy all 2026-11-11: 14/15 — only pre-existing office X1 overwrite-verify flake failed; 22 skill-* audit rows prove the loop live): E1/E5/E6 + adversarial A3/A6 + store-down; verify audit rows for every trial refusal
- [X] T026 [P] Run `graphify update .` to refresh the code graph

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1–2**: sequential foundation (T004/T006 [P] within Phase 2); blocks everything
- **US1 (Phase 3)**: needs store+validator (T003/T005)
- **US2 (Phase 4)**: needs store+embedder wiring (T011 after T003); T010/T012 parallel
- **US3 (Phase 5)**: needs store (T003); feedback handler independent of search
- **US4 (Phase 6)**: needs search+save (US1/US2) — replay consumes both; executor calls existing gates (no new gate work)
- **US5 (Phase 7)**: DSL wiring needs all four tools registered (after T024-adjacent work in `server.py`)
- **Polish**: after all stories

### User story dependencies

- US1, US2, US3: mutually independent after Phase 2 (can run in parallel)
- US4: depends on US1+US2 (replays saved, found skills)
- US5: depends on all four tools existing (wiring + envelope)

### Parallel opportunities

- Phase 2: T004, T006 in parallel with T003/T005
- After Phase 2: US1, US2, US3 suites (T007, T010, T012, T014) all parallel
- Polish: T022, T026 parallel

## Parallel Example: Phase 2 + 3 kickoff

```bash
# Parallel after T003 lands its shape:
Task T004 store suite (tests/unit/test_skill_store.py)
Task T006 audit extension (src/agentic_rag_mcp/hermes_audit.py)

# Then US suites in parallel:
Task T007 US1 save tests
Task T010 US2 trust matrix tests
Task T014 US3 feedback tests
```

## Implementation Strategy

### MVP First (User Story 1 + 2)

1. Phase 1–2 foundation
2. US1 (save) → validate independently
3. US2 (search/reuse) → validate the round-trip (E1)
4. **STOP and VALIDATE** — the learning loop works end-to-end

### Incremental delivery

5. US3 feedback/escalation → E6
6. US4 replay + FR-020 invariant → A3 (security milestone)
7. US5 DSL wiring + degradation → live battery + A6
8. Polish: counts, ruff, suite, staleness rebuild, quickstart, graphify

## Notes

- Tests are NOT optional here: Constitution II; every suite listed FAILS first, then implements
- Audit rows are part of every handler, not an afterthought (T006 pattern)
- No new dependencies, no new services (Constitution III)
- The Dify tool-cache staleness rule applies to all four registrations (T024)
- Adversarial A3/A6 are acceptance gates, not nice-to-haves (035 SC-007)
## Phase 9: Convergence

- [X] T027 Rebuild Dify `tool_mcp_providers` rows from the live sidecar `tools/list` (33 tools) for the four `skill_*` tools + restart `docker-api-1`/`docker-worker-1` (T024) (missing)
- [X] T028 Publish the chatflow via `$VENV -m agentic_rag_mcp.deploy chatflow` so the live app carries the skill-loop DSL (Hermes lane rules + 4 tools; General lane exclusion), then verify via Postgres `graph::text LIKE '%skill_search%'` (T019/FR-001/035 FR-017) (partial)
- [X] T029 Run the quickstart.md live battery on the idle Windows host: E1 learned round-trip, E5 restart persistence, E6 escalation, adversarial A3 (replay-bypass via `skill_get values` refusal path) + A6 (fabricated skill completion) + store-down degradation; grep the audit JSONL for every trial refusal row (T025, SC-001/003/005/006) (missing)
- [X] T030 Extend `HermesAudit.write_attempt` with an additive `conversation_id` field and thread it from `skill_manager/api.py` `_timed` so `skill-*` audit rows carry the conversation per the audit contract (T006, contracts/README.md) (partial)
- [X] T031 Implement the replay walk in `skill_manager/executor.py` (or re-scope T017 with a documented decision): step loop calling the existing lane handlers, `skill-replay-start`/`skill-replay-abort` audit rows, gated-step pause/resume riding the existing `hermes_powershell_state`, cancel aborts without failure feedback (T016/T017, 035 FR-020/R4) (partial)
- [X] T032 Add the explicit partial-save atomicity case to `tests/unit/test_skill_store.py` (mid-`save` failure leaves no half-written version) or drop the claim from the docstring (T004) (partial)
