# Data Model: Chat attachment upload + analysis (043)

Runtime-only objects; nothing persisted.

## Entities

### Attachment (client → attach route → chat route)
| Field | Type | Rules |
|---|---|---|
| name | string | the original filename; shown on the composer chip and in the preamble |
| type | string | one of the 8 format families (pdf, docx, doc, xlsx, xls, pptx, txt, csv, json, xml) |
| bytes | binary | ≤ **20 MB** (refused above, named in the message); in-memory only |

Lifecycle (composer): selected → extracting (`/api/attach` in flight) → ready (chip shows name + chars, removable) → sent (chip clears; one-shot) | error (inline honest message, chip removed, message text preserved).

### Extraction result (attach route response)
| Field | Type | Rules |
|---|---|---|
| chars | number | length of extracted text before the preamble cap |
| text | string | the extracted content (full; the preamble caps what reaches the model) |
| truncated | boolean | true only when the preamble cap applies at injection time |
| note | string? | honest edge notes: "no readable text (scanned/image-only PDF — OCR is not enabled)", legacy `.ppt` refusal guidance, etc. |

### Chat request extension (client → chat route)
`{ query, conversationId, aiModel, attachments?: [{name, type, chars, text, truncated, note?}] }` — **the field is absent when no attachment exists**, and the upstream Dify body is then byte-identical to today (pinned).

### Preamble (chat route → Dify query)
| Segment | Rule |
|---|---|
| header | `[Attached file: <name> (<type>, <N> characters extracted)]` (+ `[content truncated at 24,000 characters — the file is longer]` and/or the extraction note when present) |
| content | the extracted text, bounded to 24,000 chars |
| footer | `[End of attached file content]` then `---` then `User question: <owner text or "(analyze this file)" when empty>` |

## State transitions

- Send without attachment → unchanged path (no preamble; body identical).
- Send with attachment, no question text → the preamble carries `(analyze this file)` as the question (edge case: the file is still analyzed).
- Extraction error → the composer keeps the typed text, removes the chip, shows the honest reason inline; nothing is sent with a broken attachment (FR-004/005/006).

## Relationships

One message → at most one attachment → one extraction result → one preamble. Every attempt is UI-level only; no server-side record survives the request (privacy posture, clarified 2026-11-17).