# Data Model — Image-Rich Chat Answers

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

The model extends existing research types; nothing is persisted to a database. All shapes are JSON that the MCP tool already returns.

## 1. ImageBlock (extended)

An immutable block inside an ordered page section.

| Field | Type | Rules |
|---|---|---|
| `type` | `"img"` | discriminator (unchanged) |
| `src` | string | absolute `http(s)` URL after `urljoin(page_url, src)`; `data:`/non-http skipped at extraction; unique within the page result |
| `alt` | string | **new.** Trimmed source `<img alt>`; `""` when the source has none; never server-generated |

Validation: a block exists only if a usable `src` exists. A `<figure>` contributes at most one block (its inner `<img>` is not double-counted); an `<img>` inside a `<figure>` is skipped in the img branch.

## 2. SourceImageRef (new, tool-facing)

A flat projection of ImageBlock, one per unique image, in document order.

| Field | Type | Rules |
|---|---|---|
| `url` | string | equals the block's absolute `src`; dedupe key across the whole hit |
| `alt` | string | block `alt`, possibly `""` |
| `heading` | string | the `heading` of the section containing the block; `""` when the section had no heading |

Projection rules:
- iterate `scrape.sections` top to bottom, blocks in order, take only `type == "img"`;
- skip URLs matching the shared noise list (`pixel`, `tracker`, `beacon`, `spacer`, `1x1`, `blank.gif`, case-insensitive);
- skip URLs already emitted (first occurrence wins);
- stop at `limit = 40`;
- `sections` empty/missing/malformed ⇒ `[]`.

## 3. ResearchHit (extended)

| Field | Type | Change |
|---|---|---|
| `title`, `url`, `snippet` | string | unchanged |
| `scrape` | object | unchanged (`sections`, `truncated`, `status`, `status_reason`) |
| `content` | string | unchanged |
| `render_html` | string | unchanged |
| `images` | `SourceImageRef[]` | **new.** Always present. `[]` for any `status != "ok"`, for `no-extractable-content`, and for pages whose content carried no images |

Invariants (contract):
1. `images` is never `null` and never omitted.
2. `images` is a subset of the hit's own blocks (no invented URLs, no cross-hit borrowing).
3. Order equals document order; duplicates appear once.
4. `len(images) <= 40`.
5. Existing fields keep name, type, and meaning.

## 4. PageImageList (fetch tool, unchanged)

`fetch_url` keeps `images: string[]` of absolute URLs (no alt, no heading). Rationale: adding objects would break the existing contract; the search tool supplies alt.

## 5. VisibleAnswerImageBudget (behavioral, in the finalizer)

Not a stored entity — a rule applied to answer text.

| Concept | Definition |
|---|---|
| Counted image | a markdown image `![alt](url)` in the user-visible answer, outside any ` think` … `</think>` block |
| Exempt | URLs matching `/mcp-action/screenshots/` (approved captures, health evidence) |
| Cap | 10 counted images; 11th and later are removed |
| Non-destructive | surrounding text, links (non-image), headings, and line structure are preserved; only image markdown and its cleanup whitespace are removed |

## 6. State transitions

- Research page: `ok` → images projected; `blocked` / `fallback` / `failed` / `not-attempted` → `images: []` (was: no image field at all).
- Answer turn: model output → finalizer → visible answer. Finalizer never changes an answer's factual content; it only enforces the image budget.
- Repeated question: no state is stored; the model re-uses earlier tool results in the conversation, and their image URLs remain valid inputs.
