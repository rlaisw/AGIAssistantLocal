# Implementation Plan: Image-Rich Chat Answers

**Branch**: `050-image-rich-chat-answers` | **Date**: 2026-11-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/050-image-rich-chat-answers/spec.md`

## Summary

Make visual chat answers carry several real source images instead of 0–1. Three changes, in dependency order: (1) the sidecar's `web_research` payload gains, per hit, an additive `images: [{url, alt, heading}]` projection of the ordered page sections it already extracts, and the section extractor starts capturing `<img alt>`; (2) both general-lane strategy prompts (cloud and local) get the same binding image policy — visual questions must be illustrated, ≤10 images quality-gated by relevance, alt always, plan silently, self-check — replacing today's soft "try to include images" wording; (3) the existing `honesty_check` JavaScript finalizer enforces the 10-image cap deterministically over visible answer text, excluding hidden reasoning and captured screenshots. No chat-UI, PDF-export, knowledge-base, attachment, or Hermes/PPT-lane behavior changes.

The user's request adds two explicit deliverables on top of the base plan: a test plan covering unit tests and end-to-end cases (`test-plan.md`), and error handling designed in rather than discovered in production (see "Error Handling Design" below and `research.md` D6).

## Technical Context

**Language/Version**: Python 3.12 (sidecar); JavaScript inside the Dify code node; no new languages

**Primary Dependencies**: existing — httpx, BeautifulSoup4/lxml (extraction), MCP Python SDK, Dify chatflow engine, pytest, `node` (already used by DSL tests and CDP scripts). No new dependency.

**Storage**: none new — images ride in existing tool responses; DSL and prompts live in `dify/AGIAssistant/AGI_Assistant.yml`

**Testing**: pytest (unit + contract), existing `node -e` DSL-JavaScript runner pattern (`tests/unit/test_mcp_action_dsl.py`), CDP acceptance script in `ai-chat-landing/scripts/`, live prompt verification in fresh conversations

**Target Platform**: WSL2 sidecar container behind Dify; local Chat UI (Next.js) rendering markdown; Windows host untouched

**Project Type**: single repository — Python MCP service + Dify chatflow artifact + Next.js chat UI

**Performance Goals**: research payload stays page-bounded (≤3 pages by default, ≤40 image refs per hit, no added network calls); prompt/finalizer add no measurable latency; no change to research timeouts (15 s per page, 30 s overall)

**Constraints**: existing tool-response fields keep name/type/meaning (constitution I); payload additive only; images never invented or server-generated; the finalizer must not strip reasoning-local image references or `/mcp-action/screenshots/` URLs; both apps share identical prompts; publish by explicit app ID

**Scale/Scope**: 2 prompt copies per lane across 2 mirrored apps (4 strings total), 1 extractor change, 1 payload projection, 1 finalizer function, ~4 new test files + 1 CDP script, ~0 UI changes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Contract Preservation (non-negotiable) | PASS — `images` is additive on `web_research` hits; `fetch_url.images` stays `list[str]`; contract tests pin existing fields. No breaking change, so no amendment. |
| II. Tests-First | PASS — plan requires red-first unit/contract pins and a live acceptance script before implementation; full suite green is an exit gate (see `test-plan.md`). |
| III. Minimal Dependencies | PASS — no new dependency; extraction/httpx/bs4/node all present. |
| IV. Honest Answers (non-negotiable) | PASS by design — alt comes only from the source or the model's description of surrounding text; URLs only from tool results; no source images ⇒ explicit text-only statement; no server-side captioning. Error paths return empty lists with honest reasons instead of omissions. |
| V. Spec-Driven Replacement | PASS — the soft `ANSWER FORMAT — IMAGES (default)` wording is replaced, not appended; nothing else is retired. |

**Complexity Tracking**: none — no violations, no new services, no new storage.

## Error Handling Design

The feature's honesty surface is where images enter an answer, so failure handling is explicit at each boundary (mirrors `research.md` D6):

| Boundary | Failure | Required behavior |
|---|---|---|
| Extraction | `src` missing, `data:`/`javascript:` URI, relative path, duplicate image across sections, image inside `<figure>` | drop or absolutize per existing noise rules; exactly one block per real image; alt `""` when absent; never raise — a page that fails to parse yields `sections: []` (existing behavior) |
| Projection | hit has no scrape, blocked/timeout/failed page, `sections` empty or malformed | `images: []` — field always present, never `null`/omitted; never synthesize from snippet or title |
| Payload | more than ~40 images on a page | ordered, deduplicated, truncated at the 40 cap (document order wins) |
| Prompt | model sees a visual question with no tool images | text-only answer that says images were not available; no invented URL/alt |
| Finalizer | hidden reasoning contains image markdown; unbalanced ` think` / `</think>` tags; captured screenshots | never counted, never stripped; depth clamped at 0; `/mcp-action/screenshots/` URLs exempt |
| Finalizer | >10 visible images after model output | trim images 11+ (and any blank-line debris) before the answer is shown; answer text preserved |
| Deployment | one app/lane keeps old prompt; sidecar not rebuilt | checklist gates: both app IDs verified in Postgres, sidecar image rebuilt, deploy `verify` green |
| Rendering | dead/blocked image URL; PDF export proxy failure | native alt text remains visible; existing proxy/export failure path is unchanged and out of scope |

## Project Structure

### Documentation (this feature)

```text
specs/050-image-rich-chat-answers/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── test-plan.md         # Unit + end-to-end + error-handling test plan
├── contracts/
│   └── web-research-images.md
└── tasks.md             # /speckit.tasks output (not created here)
```

### Source Code (repository root)

```text
src/agentic_rag_mcp/
├── search/web/research.py     # extract_sections alt capture; flatten_images; IMG_SKIP share
└── server.py                  # web_research hit assembly: additive images field

dify/AGIAssistant/AGI_Assistant.yml
    # agentic_strategy + agentic_strategy_local instruction prompts (IMG policy)
    # honesty_check JS node (capInlineImages finalizer)

tests/
├── fixtures/research/         # existing fixtures + new alt/noise cases
├── unit/
│   ├── test_research_extraction.py     # extend: alt capture, figure dedupe
│   ├── test_research_images.py         # NEW: flatten_images order/dedupe/cap/noise
│   ├── test_research_image_payload.py  # NEW: hit assembly, empty-list guarantees
│   ├── test_image_prompt_pins.py       # NEW: binding lines in both general lanes only
│   └── test_image_cap_dsl.py           # NEW: node -e execution of the finalizer cap
└── contract/
    └── test_web_research_contract.py   # extend: additive images schema, fetch images unchanged

ai-chat-landing/scripts/
└── image-rich-check.mjs       # NEW: CDP acceptance — visible-image counting, cap, alt, text-only

windows/ …                     # untouched
ai-chat-landing/app/…          # untouched (rendering + image proxy already work)
```

**Structure Decision**: single-project layout already in place. The sidecar owns extraction/projection; the chatflow artifact owns policy and the default-on cap; tests follow the existing unit/contract/CDP split.

## Phase 0 — Research (see `research.md`)

All unknowns resolved there. Headline decisions: additive per-hit `images` projection (never a new tool), alt captured at extraction with `""` default, one shared `IMG_SKIP` list, a single binding prompt block inserted before citations in **both general lanes**, deterministic cap inside the existing `honesty_check` node (skipping think blocks and screenshot routes), and verification by the four live prompts plus a CDP script.

## Phase 1 — Design (see artifacts)

- `data-model.md` — `SourceImageRef`, extended `ImageBlock`, `ResearchHit.images`, `VisibleAnswerImageBudget`
- `contracts/web-research-images.md` — additive schema, invariants, empty-list guarantees
- `quickstart.md` — runnable validation sequence (unit → contract → deploy → CDP → four live prompts)
- `test-plan.md` — FR→test matrix, red-first unit tests, E2E cases, error-handling matrix, acceptance gates

## Post-Design Constitution Re-check

| Principle | Post-design result |
|---|---|
| I | PASS — schema additive; `fetch_url` shape untouched; existing contract tests unchanged except additive assertions |
| II | PASS — every behavior has a named check in `test-plan.md`, written before implementation |
| III | PASS — no dependency added |
| IV | PASS — error matrix above; no fabricated URL/alt path exists; finalizer cannot invent content |
| V | PASS — replacement of the soft block, single source of truth per app |

## Next

`/speckit.tasks` → task list from these artifacts; implementation order: tests (red) → extractor/projection → sidecar rebuild → prompts (both apps) → finalizer → publish by explicit IDs → CDP + live verification.
