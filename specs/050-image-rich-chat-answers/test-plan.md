# Test Plan — Image-Rich Chat Answers

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Contract**: [contracts/web-research-images.md](./contracts/web-research-images.md) | **Date**: 2026-11-25

## Strategy

Four layers, each proving something the layer above cannot:

1. **Unit (pytest)** — extraction alt capture, projection invariants, hit assembly, error degradation.
2. **Static artifact pins (pytest)** — the published chatflow must contain the binding policy in exactly the general lanes, and the finalizer must contain the cap; the cap's JavaScript is executed, not just grepped.
3. **Contract (pytest)** — `web_research` / `fetch_url` response schemas stay backward-compatible with additive `images`.
4. **End-to-end (CDP + live prompts)** — the user actually sees ≥3 images on a how-to, ≤10 on a gallery, and 0 on a text-only question, on both apps.

Every non-trivial case is written **red first**: run the new test against current code/DSL and record the failure before implementing.

## Layer 1 — Unit tests

### New fixtures (`tests/fixtures/research/`)

| Fixture | Contents |
|---|---|
| `images-alt.html` | h2 → p → `<img src alt="  Open the Trace dialog  ">` → `<figure><img data-src="…lazy.png" alt="Results panel"></figure>` → `<img>` (no alt) → `<img src="data:image/png;base64,...">` → duplicate of the first img |
| `images-noise.html` | relative `src`, `pixel.gif`, `1x1.png`, `tracker.png`, a `javascript:` src, an `<img>` with no src |
| `images-many.html` | 60 images across 3 sections (cap test) |
| `images-none.html` | headings + paragraphs only |

### `tests/unit/test_research_extraction.py` (extend)

| Test | Pins |
|---|---|
| `test_img_block_captures_trimmed_alt` | blocks carry `alt`, whitespace trimmed (FR-010) |
| `test_missing_alt_is_empty_string_not_none` | `alt == ""`, key present |
| `test_figure_supplies_data_src_and_alt_once` | one block per figure; inner img not double-counted |
| `test_data_uri_and_srcless_images_skipped` | no block for `data:`, none for missing src |
| `test_existing_order_and_noise_pins_unchanged` | the four existing tests keep passing |

### `tests/unit/test_research_images.py` (new)

`flatten_images(sections, limit=40)`:

| Test | Pins |
|---|---|
| `test_document_order_and_heading_attribution` | refs follow sections/blocks order; `heading` = containing section (FR-001) |
| `test_duplicates_appear_once_first_wins` | dedupe by URL across sections |
| `test_noise_urls_skipped_case_insensitive` | shared noise list applies (FR-001) |
| `test_cap_at_40_in_document_order` | 60 images → first 40 |
| `test_alt_passthrough_including_quotes_and_newlines` | no mutation; JSON serializer handles escaping later |
| `test_empty_and_malformed_sections_yield_empty_list` | `[]`, `{}`, `None` inputs → `[]`, no exception |
| `test_block_without_src_is_skipped_defensively` | malformed block cannot crash the projection |

### `tests/unit/test_research_image_payload.py` (new)

Stubbed `research_pages` + fake provider, asserting hit assembly (server.py):

| Test | Pins |
|---|---|
| `test_ok_hit_has_images_projection` | `hit["images"]` matches sections (FR-001/003) |
| `test_non_ok_scrapes_yield_empty_images_list` | fallback/blocked/failed/not-attempted → `[]` present (FR-002) |
| `test_image_less_page_yields_empty_list` | ok scrape, zero images → `[]` |
| `test_existing_hit_fields_unchanged` | `snippet`/`content`/`render_html`/`scrape` identical to pre-change values (FR-020) |

### `tests/unit/test_image_prompt_pins.py` (new)

Static DSL inspection, modeled on `test_ask_before_answering.py`:

| Test | Pins |
|---|---|
| `test_binding_block_in_both_general_prompts` | `Agentic Strategy` and `Agentic Strategy (Local)` contain: `ANSWER FORMAT — IMAGES (binding)`, `BINDING:`, `CAP: an answer MUST NOT inline more than 10 images`, `plan silently`, `SELF-CHECK`, `Never invent an image URL`, `web_research also returns a flat images array` (FR-005–FR-015, FR-016) |
| `test_block_precedes_citations` | index(IMAGES) < index(`ANSWER FORMAT — CITATIONS:`) in both prompts |
| `test_exactly_one_images_block_per_general_prompt` | no duplicated paste |
| `test_operational_lanes_excluded` | `Hermes Local Agent`, `PPT-Master`, `PPT-Master (Local)` do **not** contain the binding block (FR-016) |
| `test_soft_default_wording_removed` | `ANSWER FORMAT — IMAGES (default)` and its "Fetch as many as are useful" wording are gone |

### `tests/unit/test_image_cap_dsl.py` (new)

Extract the `honesty_check` code node and execute it with `node -e` (same runner shape as `test_mcp_action_dsl.py`: pass `code` + `inputs`, read `result`).

| Test | Pins |
|---|---|
| `test_cap_keeps_first_ten_visible_images` | 12 markdown images → first 10 survive, 11th/12th removed (FR-008) |
| `test_think_block_images_not_counted_or_stripped` | 3 visible + 8 inside ` think…</think>` → all 3 kept, think content byte-identical (FR-011) |
| `test_screenshot_urls_exempt` | 12 `/mcp-action/screenshots/` images all kept (FR-017) |
| `test_unbalanced_think_tags_clamp_at_zero` | stray `</think>` then visible images → still counted, no negative depth |
| `test_answer_without_images_unchanged` | text/links/headings preserved exactly |
| `test_cleanup_does_not_leave_triple_newlines` | removal leaves at most one blank line run |

## Layer 2 — Contract tests (`tests/contract/test_web_research_contract.py`, extend)

| Test | Pins |
|---|---|
| `test_web_research_schema_v2` (existing) | all v2 assertions unchanged (FR-020) |
| `test_hits_carry_images_field` | `images` is a list on every hit; each ref has `url`/`alt`/`heading` strings |
| `test_fallback_hit_has_empty_images` | fallback hit → `[]` |
| `test_fetch_url_images_remain_strings` | `fetch_url.images` elements are `str`, not objects (contract §2) |
| `test_tool_result_json_survives_alt_quotes_and_newlines` | a hit whose alt contains `"` and `\n` still serializes and re-parses as JSON (Dify tool-list crash class) |
| `test_images_urls_are_absolute_http` | no `data:`, no scheme-less |

## Layer 3 — End-to-end (CDP, `ai-chat-landing/scripts/image-rich-check.mjs`, new)

Drives the real Chat UI through CDP (`CDP_URL`, default `http://localhost:9240`), one fresh conversation per scenario, then counts rendered `img` elements inside the assistant's answer and reads their `alt`/`src`.

| Case | Env | Assertions |
|---|---|---|
| How-to | `PROMPT=<how-to>`, `MIN_IMAGES=3` | count ≥ 3; every image has non-empty alt and non-empty `src`; no `src` starting with `data:`; first image appears before the last 30% of the answer text (grouping smoke) |
| Overview | `PROMPT=<overview>`, `MIN_IMAGES=2` | count ≥ 2; not all images after the final heading-of-last-comparison (cluster check) |
| Gallery | `PROMPT=<gallery>` | 1 ≤ count ≤ 10 |
| Text-only | `PROMPT=What is the capital of France?` | count == 0 |
| Cap visual | default run | after the gallery case, assert no answer in the run exceeds 10 |

The script prints a per-case JSON line (`{case, visible, with_alt, empty_src, pass}`) and exits non-zero on any failure. It also accepts `--smoke` to run only the text-only case (fast, no long generation).

## Layer 4 — Live model acceptance (both apps)

Run the four prompts in the table in [quickstart.md](./quickstart.md) §6 on **each** app ID, fresh conversation per prompt, answering at most one clarifying question. Record visible counts (snapshot the answer text; strip ` think` blocks if inspecting raw).

Additional live checks:

1. Repeat the how-to question in the same conversation; images from earlier research remain inline (FR-014).
2. Ask a visual question whose sources genuinely have no images (e.g. a topic with text-only documentation); answer states this and shows 0 images (FR-013).
3. Ask for a chart plus images ("…and show me a chart"); verify chart image plus source images stay ≤ 10 combined (FR-008).

## Error-handling test matrix

| Failure | Test proving the behavior |
|---|---|
| No alt on source | `test_missing_alt_is_empty_string_not_none` |
| Relative / node_modules-style noise URLs | `test_noise_urls_skipped_case_insensitive`, `test_img_block_captures_trimmed_alt` |
| `data:` or missing src | `test_data_uri_and_srcless_images_skipped` |
| Duplicate image | `test_duplicates_appear_once_first_wins` |
| Page not scraped / blocked / timed out | `test_non_ok_scrapes_yield_empty_images_list` |
| Page had no images | `test_image_less_page_yields_empty_list` |
| Huge gallery page | `test_cap_at_40_in_document_order`, CDP gallery ≤ 10 |
| Malformed sections/blocks | `test_empty_and_malformed_sections_yield_empty_list`, `test_block_without_src_is_skipped_defensively` |
| Alt containing quotes/newlines | `test_tool_result_json_survives_alt_quotes_and_newlines` |
| Hidden-reasoning images | `test_think_block_images_not_counted_or_stripped` |
| More than 10 visible images | `test_cap_keeps_first_ten_visible_images`, CDP gallery case |
| Screenshot evidence | `test_screenshot_urls_exempt` |
| Unbalanced think tags | `test_unbalanced_think_tags_clamp_at_zero` |
| Dead/blocked image URL | CDP `empty_src` check + alt presence; no UI fallback exists by design |
| One lane missed / one app missed | `test_operational_lanes_excluded` + Postgres prompt check per app in quickstart §3 |

## Commands and gates

```bash
# red-first, then green
.venv/bin/python -m pytest tests/unit/test_research_images.py \
  tests/unit/test_research_image_payload.py tests/unit/test_image_prompt_pins.py \
  tests/unit/test_image_cap_dsl.py tests/unit/test_research_extraction.py -q
.venv/bin/python -m pytest tests/contract -q
.venv/bin/python -m pytest tests/unit tests/contract -q        # full gate
node --check ai-chat-landing/scripts/image-rich-check.mjs      # script syntax
```

Release gates (all must hold):

- [ ] New tests were run red before their implementation and are green after.
- [ ] Full `tests/unit tests/contract` suite green; no existing assertion weakened.
- [ ] Sidecar rebuilt; both app IDs show the prompt marker in Postgres.
- [ ] CDP script passes all five cases; live four-prompt matrix passes on both apps.
- [ ] No chat-UI source change required; `pnpm typecheck`/`lint` untouched (only a new `scripts/*.mjs` added).

## Out of test scope

- Knowledge-base and attachment answers (explicitly unchanged).
- Server-side captioning/vision (not implemented).
- PDF-export visual regression beyond confirming existing images still export (covered by spec 013's suite).
- Model quality beyond image policy (answer correctness is covered by existing live batteries).
