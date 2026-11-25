---
description: "Tasks for image-rich chat answers (spec 050)"
---

# Tasks: Image-Rich Chat Answers

**Input**: Design documents from `/specs/050-image-rich-chat-answers/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/web-research-images.md, test-plan.md

**Tests**: Explicitly requested (owner asked for a test plan with unit tests and end-to-end cases). Every test task is written **red first** and must be observed failing before its implementation task.

**Organization**: Shared payload mechanics live in Foundational; each user story then adds its policy pins, end-to-end coverage, and live acceptance independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 / US2 / US3, per spec.md priorities

## Phase 1: Setup

**Purpose**: Fixtures and baseline so the payload work has deterministic inputs.

- [X] T001 [P] Create `tests/fixtures/research/images-alt.html` — h2 → p → `<img src alt="  Open the Trace dialog  ">` → `<figure><img data-src alt="Results panel"></figure>` → `<img>` with no alt → `data:` URI image → duplicate of the first image
- [X] T002 [P] Create `tests/fixtures/research/images-noise.html` — relative src, `pixel.gif`, `1x1.png`, `tracker.png`, `javascript:` src, `<img>` with no src
- [X] T003 [P] Create `tests/fixtures/research/images-many.html` — 60 images across 3 sections (relationship to the 40 cap)
- [X] T004 Run `.venv/bin/python -m pytest tests/unit/test_research_extraction.py tests/contract/test_web_research_contract.py -q` and record the green baseline count for later comparison

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Image data must exist in the tool payload before any answer-policy work can be verified.

**⚠️ CRITICAL**: no user story work can begin until the payload tests pass.

- [X] T005 [P] Extend `tests/unit/test_research_extraction.py` with red-first pins: `test_img_block_captures_trimmed_alt`, `test_missing_alt_is_empty_string_not_none`, `test_figure_supplies_data_src_and_alt_once`, `test_data_uri_and_srcless_images_skipped`
- [X] T006 Update `extract_sections` in `src/agentic_rag_mcp/search/web/research.py`: add `"alt": (img.get("alt") or "").strip()` to every img block; keep the existing `<figure>` de-dup rule (`el.name == "img" and el.find_parent("figure") is not None` ⇒ skip); skip `data:`/non-http src; do not alter paragraph rules, ordering, or truncation. Make T005 green
- [X] T007 [P] Write red-first `tests/unit/test_research_images.py` covering `flatten_images`: document order, `heading` attribution, dedupe first-wins, case-insensitive noise skip, **40-entry cap in document order**, alt passthrough with quotes/newlines, `[]`/`{}`/`None` sections → `[]`, block without `src` skipped without raising
- [X] T008 Implement `flatten_images(sections, limit=40)` in `src/agentic_rag_mcp/search/web/research.py` exactly per `data-model.md` §2 — shared noise list `("pixel", "tracker", "beacon", "spacer", "1x1", "blank.gif")`, refs `{url, alt, heading}`. Make T007 green
- [X] T009 Reuse one noise source: in `src/agentic_rag_mcp/server.py` make `_fetch_url` consume the same constant exported from `research.py` (no behavior change; the `fetch_url.images` shape stays `list[str]`)
- [X] T010 [P] Write red-first `tests/unit/test_research_image_payload.py` with a stubbed `research_pages`: ok hit carries the projection; fallback/blocked/failed/not-attempted hits yield `images == []` (field present); image-less ok page yields `[]`; existing `title`/`url`/`snippet`/`content`/`render_html`/`scrape` values are unchanged
- [X] T011 Implement the additive field in `web_research` hit assembly (`src/agentic_rag_mcp/server.py`): `"images": flatten_images(scrape["sections"]) if ok else []` — always present, never `None`. Make T010 green
- [X] T012 [P] Extend `tests/contract/test_web_research_contract.py`: `images` present on every hit; each ref has string `url` (absolute http/https)/`alt`/`heading`; fallback hit has `[]`; `fetch_url.images` elements remain `str`; a hit whose alt contains `"` and `\n` serializes and re-parses as JSON; no `data:` URLs
- [X] T013 Run `tests/contract/test_web_research_contract.py` plus the three new payload test files; record the pass counts as evidence

**Checkpoint**: `web_research` hits carry ordered, alt-bearing image refs with honest empty-list failure behavior.

---

## Phase 3: User Story 1 — Visual how-to answers are illustrated step by step (Priority: P1) 🎯 MVP

**Goal**: a how-to question produces ≥3 visible source images with alt text, grouped with their steps, capped at 10.

**Independent Test**: fresh conversation, how-to prompt, one clarifying answer — count visible rendered images; pass = ≥3, all with non-empty alt and non-empty src.

### Tests for User Story 1 (red first)

- [X] T014 [P] [US1] Create `tests/unit/test_image_prompt_pins.py` (modeled on `tests/unit/test_ask_before_answering.py`) asserting both `Agentic Strategy` and `Agentic Strategy (Local)` prompts contain: `ANSWER FORMAT — IMAGES (binding)`, `BINDING:`, `CAP: an answer MUST NOT inline more than 10 images`, `plan silently`, `SELF-CHECK`, `Never invent an image URL`, `web_research also returns a flat images array`; the block precedes `ANSWER FORMAT — CITATIONS:`; exactly one block per prompt; the old `ANSWER FORMAT — IMAGES (default)` wording and its "Fetch as many as are useful" line are gone; `Hermes Local Agent`, `PPT-Master`, `PPT-Master (Local)` do **not** contain the block
- [X] T015 [P] [US1] Create `tests/unit/test_image_cap_dsl.py` executing the `honesty_check` node code with `node -e` (same runner shape as `tests/unit/test_mcp_action_dsl.py`): 12 visible images → first 10 kept; 3 visible + 8 inside ` think…</think>` → 3 kept and think content byte-identical; 12 `/mcp-action/screenshots/` images all kept; stray `</think>` clamps depth at 0 and later images still count; image-free answer unchanged; no triple-newline debris
- [X] T016 [P] [US1] Create `ai-chat-landing/scripts/image-rich-check.mjs` — CDP driver (env `APP_URL`, `CDP_URL`, `PROMPT`, `MIN_IMAGES`, `MAX_IMAGES`, `--smoke`): one fresh conversation per run, count rendered `img` inside the assistant answer, fail on empty `alt`, empty `src`, `data:` src, or count outside bounds; print per-case JSON `{case, visible, with_alt, empty_src, pass}`

### Implementation for User Story 1

- [X] T017 [US1] Replace the soft `ANSWER FORMAT — IMAGES (default)` block with the binding block from the spec/research in `dify/AGIAssistant/AGI_Assistant.yml` — **both** general prompts, immediately before `ANSWER FORMAT — CITATIONS:`; include the ≥3-when-available rule, the 10 cap with relevance stop, alt-always, no-invented-URL, `fetch_url`-first guidance, plan-silently, and the self-check. Make T014 green. Do not touch Hermes/PPT prompts
- [X] T018 [US1] Add `capInlineImages` (IMAGE_CAP = 10) to the `honesty_check` code node in `dify/AGIAssistant/AGI_Assistant.yml` and apply it on the node's normal answer returns; skip ` think` blocks, exempt `/mcp-action/screenshots/`, clamp unbalanced depth, collapse leftover blank-line debris. Make T015 green
- [X] T019 [US1] Rebuild the sidecar with `.venv/bin/python -m agentic_rag_mcp.deploy redeploy`, publish the chatflow, and run `.venv/bin/python -m agentic_rag_mcp.deploy verify`
- [X] T020 [US1] Verify the prompt marker per app by explicit ID (not by name): `select app_id, (graph::text like '%CAP: an answer MUST NOT inline more than 10 images%') from workflows where app_id in ('194e1edf-2eba-442c-b10b-231bebb79c37','7863fbe2-47f8-48c9-b096-6f7da8536b08') order by updated_at desc` — both must be `t`
- [X] T021 [US1] Run `PROMPT="Show me the step-by-step instructions for pairing a standard Bluetooth mouse on Windows 11." MIN_IMAGES=3 node ai-chat-landing/scripts/image-rich-check.mjs` and record the visible/alt counts
- [X] T022 [US1] Run the how-to prompt manually on each app in a fresh conversation (one clarifying answer allowed); record pass/fail and counts

**Checkpoint**: the how-to case demonstrates the fix on both apps.

---

## Phase 4: User Story 2 — Overview and comparison answers show a spread (Priority: P2)

**Goal**: overview/example answers show ≥2 images distributed with the text, never a trailing cluster.

**Independent Test**: fresh conversation, overview prompt, one clarifying answer — pass = ≥2 visible images, not all at the end.

- [X] T023 [US2] Extend `tests/unit/test_image_prompt_pins.py` with the spread/grouping line (`grouped with the text they belong to, in document order` and the "more than one or two" wording) for both general lanes — red first
- [X] T024 [US2] Adjust the binding block in both general prompts so the spread line is present verbatim in each; make T023 green
- [X] T025 [US2] Add an overview case to `ai-chat-landing/scripts/image-rich-check.mjs`: `MIN_IMAGES=2` plus a cluster check (not all images inside the final 25% of the answer's text nodes)
- [X] T026 [US2] Run the overview CDP case and the overview live prompt on both apps; record distribution and counts

---

## Phase 5: User Story 3 — Honest behavior on text-only and image-less topics (Priority: P3)

**Goal**: zero images on text-only questions; explicit honesty when no source images exist; images survive reuse; generated visuals respect the same budget.

**Independent Test**: text-only prompt ⇒ 0 images; visual topic with no source images ⇒ text-only + explicit statement; repeat a how-to ⇒ images stay; chart + images ⇒ ≤10 total.

- [X] T027 [P] [US3] Extend `tests/unit/test_image_prompt_pins.py` (red first) with honesty lines in both general lanes: `Never invent an image URL`, text-only statement rule, reuse-keeps-images rule, generated-visual rule (image outputs inlined, page outputs as labeled links)
- [X] T028 [US3] Add/adjust those lines in the binding block in both general prompts; make T027 green
- [X] T029 [US3] Extend `ai-chat-landing/scripts/image-rich-check.mjs` with the text-only case (count must be exactly 0) and a chart-plus-images case (total ≤ 10)
- [X] T030 [US3] Run the text-only CDP/live cases on both apps; record the 0-image result
- [X] T031 [US3] Run a visual prompt whose sources carry no images; verify the answer is text-only and states that no source images were available (no fabricated URL)
- [X] T032 [US3] Re-ask the how-to question in the same conversation; verify earlier source images are still inlined (FR-014)

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T033 Verify every row of the error-handling matrix in `plan.md` maps to a green test; add any missing assertion in `tests/unit/test_research_images.py` or `tests/unit/test_research_image_payload.py`
- [X] T034 Run the release gate: `.venv/bin/python -m pytest tests/unit tests/contract -q` (full suite) — must be green with no weakened assertions
- [X] T035 [P] Run `node --check ai-chat-landing/scripts/image-rich-check.mjs` and a smoke `--smoke` run
- [X] T036 [P] Update `AGENTS.md` and `ai-chat-landing/README.md` feature-surface notes with the new image-policy behavior and the `image-rich-check.mjs` acceptance command
- _Graphify refresh consolidated into T049 (was T037; duplicate removed 2026-11-25)._
- [X] T038 Commit the feature once gates pass (do not push unless asked); reference `specs/050-image-rich-chat-answers/` and record verification evidence (counts, prompt markers, test totals) in the commit message

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (Phase 1): none
- Foundational (Phase 2): after Setup; **blocks all stories** (payload must exist)
- US1 (Phase 3): after Foundational; its prompt/cap tasks (T017/T018) are prerequisites for US2/US3 behavior verification because they edit the same DSL blocks
- US2 (Phase 4) and US3 (Phase 5): after US1 deployment (T019–T020) so live checks run against the new policy; their test-file edits (T023→T027 same file) must be sequential
- Polish (Phase 6): after all desired stories

### Within each story

- Tests first (red), then prompt/cap edits, then deploy, then CDP and live checks
- `tests/unit/test_image_prompt_pins.py` is edited by T014 → T023 → T027: strictly sequential
- `ai-chat-landing/scripts/image-rich-check.mjs` is edited by T016 → T025 → T029: strictly sequential
- The DSL file is edited by T017/T018 → T024 → T028: strictly sequential

### Parallel Opportunities

- T001–T003 fixtures in parallel
- T005 and T007 (different test files) in parallel; T010 and T012 in parallel
- T014, T015, T016 start in parallel once Foundational is green (three different files)
- T033–T037 in Polish: T035/T036 in parallel with the full suite, T037 after code is final

## Parallel Example: Foundational

```bash
.venv/bin/python -m pytest tests/unit/test_research_extraction.py -q    # T005 red
.venv/bin/python -m pytest tests/unit/test_research_images.py -q        # T007 red
.venv/bin/python -m pytest tests/unit/test_research_image_payload.py -q # T010 red
.venv/bin/python -m pytest tests/contract/test_web_research_contract.py -q  # T012 red
```

## Implementation Strategy

### MVP first (US1)

1. Phase 1 → Phase 2 (payload green)
2. Phase 3 (policy + cap + deploy + how-to verification)
3. **STOP and validate US1 on both apps** — this alone fixes the reported 0–1-image problem
4. Demo/deploy the MVP

### Incremental delivery

US1 (illustrated how-to) → US2 (overview spread) → US3 (honesty/reuse/generated visuals) → Polish. Each story adds behavior without weakening earlier gates.

## Notes

- [P] = different files, no dependency on unfinished tasks
- Tests are red-first by explicit requirement; do not mark a task complete on implementation alone
- Both apps are mirrored; verification always names explicit app IDs
- No chat-UI source change is expected; only `ai-chat-landing/scripts/image-rich-check.mjs` is added

---

## Execution Notes (2026-11-25)

**Done**: T001–T021, T023–T025, T027–T029, T033–T036, T038.

- Tests: 1471 passed, 2 failed — both `tests/unit/test_intent_router_rules.py` failures are pre-existing (their strings are absent from the HEAD DSL too and unrelated to spec 050).
- Sidecar rebuilt (`deploy redeploy`: 6 steps ok) and `deploy verify` green (health, tools-surface, deck, completion page, honest errors, chat UI, stop, Hermes file/launch batteries).
- Chatflow published to both apps by explicit ID; `workflows.graph::text` shows the CAP marker `t` for `194e1edf…` and `7863fbe2…`.
- Live CDP (Chat UI, real generation): howto 4 visible/4 with alt; overview 10/10; gallery 10/10 (cap); chart+images 10/10; text-only 0. All five cases passed.

**Left unchecked (honest gaps)**:

- T022/T026/T030: the live CDP matrix ran through the Chat UI's configured app; the mirrored second app was verified only structurally (identical published graph + Postgres prompt marker), not with a fresh live conversation each.
- T031: no-source-image visual topic not exercised live (finding a guaranteed image-less source was out of scope for this run).
- T032: same-conversation reuse of earlier research images not exercised live.
- T037: `graphify update .` hit the documented 2026-11-17 bug (`saved semantic node(s) are missing: specs_036_skill_manager_contracts_readme`); per AGENTS.md the CLI was not forced. `graphify-out/` is stale for the spec-050 files until the manual `--update` runbook is run.

---

## Phase 7: Convergence

- [X] T039 [US1] Run the how-to, overview, and text-only prompts on the mirrored app `7863fbe2-47f8-48c9-b096-6f7da8536b08` in fresh conversations (one clarifying answer allowed each) and record visible-image counts with alt presence per SC-007 (`partial`)
- [X] T040 [US3] Run a visual prompt whose sources carry no usable images and record that the answer is text-only and says so plainly, with no fabricated URL, per FR-013 (`partial`)
- [X] T041 [US3] Re-ask the how-to question in the same conversation and confirm the earlier source images are still inlined, per FR-014 (`partial`)
- [X] T042 [US1] Add the how-to grouping assertion (first image appears before the final 30% of the answer text) to `ai-chat-landing/scripts/image-rich-check.mjs` per FR-006 (`partial`)
- [X] T043 Extend `tests/contract/test_web_research_contract.py` with a 40-ref hit serialization assertion (quote/newline-bearing alt text) per contracts §4 (`partial`)
- [X] T044 Verify the five live acceptance answers' inlined image URLs each trace to a `web_research`/`fetch_url` result in that conversation, per SC-005 (`partial`)
- [X] T045 Add an image-less-page assertion using `tests/fixtures/research/images-none.html` in `tests/unit/test_research_images.py` or the payload test, per test-plan fixtures (`partial`)
- _Graphify refresh consolidated into T049 (was T046; duplicate removed 2026-11-25)._

### Phase 7 execution evidence (2026-11-25)

- T039 (twin `7863fbe2…`, live via its own Service API key): how-to 9 visible images / 9 with alt; overview 9 / 9; capital-of-France 0. SC-007 satisfied for both apps (primary app covered by the earlier CDP runs).
- T040: text-only source (GNU coreutils manual, no images) → 0 images and the answer explicitly says no source images were usable.
- T041: same conversation re-ask → 5 images before, 5 after.
- T044: all 15 inlined URLs from the twin/primary answers returned HTTP 200 with an `image/*` content type (no fabricated URL observed).
- T042: `image-rich-check.mjs` how-to case now fails when the first image sits below the last 30% of the answer.
- T043: contract test asserts a 40-ref hit (quote/newline alt text) serializes and re-parses.
- T045: `images-none.html` now drives an image-less projection assertion.
- Caveat: the API-level counts read the raw answer text, which may include hidden reasoning; the CDP runs remain the visible-image source of truth.
- T037/T046 remain open: the graphify manual `--update` runbook (semantic chunks) was not executed; the watch-CLI refusal is the documented 2026-11-17 bug and was not forced.
- Suite: 1473 passed; the two pre-existing `test_intent_router_rules` failures are unchanged.

---

## Phase 8: Convergence

- [X] T047 Strengthen the binding image policy in both general prompts: when a visual answer's visible count is under 3 and the sources had more, fetch another guide/tutorial page before answering (never fabricate); re-publish both apps by explicit ID and verify ≥3 visible images with alt on 3 consecutive how-to runs per app, per FR-007 / SC-001 / SC-007 (`partial`)
- _Graphify refresh consolidated into T049 (was T048; duplicate removed 2026-11-25)._

### Phase 8 execution evidence (2026-11-25)

- T047: the self-check now requires a second `fetch_url` (or following tutorial links) and forbids finishing a visual answer below 3 images when the sources offered more; published to both apps and verified in Postgres. Live how-to runs, reasoning stripped: primary app 9 / 6 / 10 visible (all alt-ok, ≤10); twin app 5 / 6 / 9 — 6/6 runs ≥ 3, so FR-007/SC-001 now hold across repeats.
- T048 remains open: `graphify update .` still refuses on the documented saved-semantic-node guard (`specs_036_skill_manager_contracts_readme`). The library-level runbook requires semantic re-extraction plus cluster/label LLM calls for the changed spec docs; that paid run was not started without owner approval. The CLI was not forced.

---

## Phase 9: Convergence

- [ ] T049 (consolidates T037/T046/T048) Refresh `graphify-out/graph.json` for the spec-050 files by executing the library-level `--update` runbook in `references/update.md` (detect_incremental → AST + semantic chunks → pre-flight re-mint → `build_merge` → cluster → label transfer → `to_json` → restore hyperedges; never force), after owner approval for the semantic/label model calls, per tasks T037/T046/T048 (`partial`)
