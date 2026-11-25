# Contract — Web Research Image Payload (additive v1)

**Feature**: 050-image-rich-chat-answers | **Applies to**: MCP tool `web_research` (`hits[].images`), MCP tool `fetch_url` (`images`), and the answer policy that consumes them.

This contract is **additive**. Every existing field keeps its name, type, and meaning (constitution I). A consumer written before this feature must keep working unchanged.

## 1. `web_research` hit — new field

```json
{
  "title": "Trace Guide",
  "url": "https://docs.example/trace",
  "snippet": "How to trace a message.",
  "scrape": {"url": "...", "sections": [...], "truncated": false, "status": "ok", "status_reason": null},
  "content": "Trace a message\n...",
  "render_html": "<!DOCTYPE html>...",
  "images": [
    {"url": "https://docs.example/img/trace-step1.png", "alt": "Open the Trace dialog", "heading": "Trace a message"},
    {"url": "https://cdn.example.com/img/trace-results.png", "alt": "", "heading": "Understand the results"}
  ]
}
```

Schema:

| Field | Type | Required | Notes |
|---|---|---|---|
| `url` | string (absolute http/https) | yes | unique within the hit's `images` |
| `alt` | string | yes | may be `""`; never invented by the server |
| `heading` | string | yes | may be `""` |

Rules:

1. `images` MUST be present on every hit, including fallback/blocked/failed/not-attempted pages.
2. `images` MUST be `[]` when the page was not scraped successfully or contained no usable images.
3. `images` MUST NOT contain URLs absent from that hit's own section blocks.
4. `images` MUST be in document order; duplicates appear once (first occurrence).
5. `images` MUST NOT exceed 40 entries.
6. `images` MUST NOT include tracker/noise URLs (`pixel`, `tracker`, `beacon`, `spacer`, `1x1`, `blank.gif`).
7. `alt` MUST equal the trimmed source `<img alt>` or `""`.

## 2. `fetch_url` — unchanged

`images` remains `string[]` of absolute URLs, in page order, noise-filtered, deduplicated. No `alt`, no objects, no heading. Adding objects here is a breaking change and is forbidden by this feature.

## 3. Answer policy contract (prompt + finalizer)

The published chatflow must satisfy all of:

| ID | Invariant |
|---|---|
| C-01 | General lanes (cloud and local) contain the identical binding image block. |
| C-02 | Hermes and PPT-Master prompts do not contain it. |
| C-03 | A visual answer with available source images inlines at least 3 and at most 10 visible images. |
| C-04 | Every inlined image URL appeared in a tool result of the same conversation. |
| C-05 | Every inlined image has non-empty alt text in the final answer. |
| C-06 | Images sit with the text they illustrate, in source order. |
| C-07 | Hidden reasoning image references are neither counted nor stripped. |
| C-08 | `/mcp-action/screenshots/` images are exempt from the cap. |
| C-09 | Text-only topics yield an answer with zero images. |
| C-10 | A visual topic with no usable source images yields a text-only answer that states this. |

## 4. Compatibility test obligations

- `tests/contract/test_web_research_contract.py` keeps every existing assertion; new assertions cover `images` presence, type, dedupe, order, and `[]` on non-ok scrapes.
- A consumer test (chatflow JSON serialization of tool results) proves a hit with 40 image refs still serializes into the tool list without breaking JSON parsing; newlines/quotes inside `alt` must be escaped by the existing serializer (see the `mcp_action` Dify-binding regression for the failure mode).
- `fetch_url` contract test asserts `images` elements are strings, not objects.
