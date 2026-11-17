# Contracts: Chat attachment upload + analysis (043)

## POST /api/attach (new)

**In**: multipart/form-data, one field `file`.
**Validation order**: size ≤ 20 MB → extension on the 8-format allowlist → magic sniff (PDF `%PDF-`; docx/xlsx/pptx `PK`) → non-empty.
**Out 200**: `{ok: true, filename, type, chars, text, truncated: false, note?}`
**Out (honest JSON errors, rendered inline by the composer)**:
| Status | When | Message shape |
|---|---|---|
| 413 | file > 20 MB | `"This file is 23.4 MB — the maximum attachment size is 20 MB."` |
| 415 | extension not in the 8-format list | names the supported list |
| 415 | magic sniff mismatch (e.g. `.pdf` that starts `PK`) | `"The file content does not match its .pdf extension."` |
| 422 | empty file | `"This file is empty — there is nothing to analyze."` |
| 422 | extraction failure (corrupt archive, malformed JSON/XML, legacy `.ppt`, encrypted PDF) | the specific honest reason (e.g. legacy `.ppt`: `"Legacy PowerPoint (.ppt) text cannot be extracted — save it as .pptx and attach that."`) |
| 422 | scan-only PDF (empty text layer) | `ok` with `note: "no readable text … OCR is not enabled"` — the chip still attaches; the preamble carries the note (the honest path, not a silent drop) |

## POST /api/chat (extended)

**In**: existing `{query, conversationId, aiModel}` **plus optional** `attachments: [{name, type, chars, text, truncated, note?}]`.
**Out**: unchanged streaming contract.
**Rule**: when `attachments` is absent/empty, the upstream Dify body is byte-identical to today (pinned by a request-shape test). When present, `query` becomes the structured preamble (R3 in research.md) — header, bounded content (24,000 chars), footer, then the owner's question (or `(analyze this file)`).

## Composer UI contract (page.tsx)

- Paperclip click → hidden `<input type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.json,.xml">` → native picker.
- Selected file → chip: filename, spinner while extracting, remove (×) before send; new selection replaces the old one (one attachment).
- Client pre-checks (fast feedback, server still authoritative): extension allowlist + 20 MB.
- Inline honest errors (the house's inline-error pattern): never a silent drop; the typed message text survives every error.
- Send: extract first (chip must be `ready` or absent), then chat with the attachment payload; the chip clears on send (one-shot).
- Text-only send: unchanged (no attachment → no payload field, no UI change).

## Backward-compatibility pins

- No attachment → identical Dify request body (unit-pinned).
- Existing streaming/stop/model-selector/history behaviors untouched.
- No chatflow/DSL changes.