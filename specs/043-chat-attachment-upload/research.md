# Research: Chat attachment upload + analysis (043)

Created: 2026-11-17. Codebase-grounded (files read: `app/api/chat/route.ts`, `app/page.tsx` composer, `package.json`, `vitest.config.ts`; the shipped `scripts/*.mjs` CDP pattern).

## R1: Extraction location — the Next.js API route (in-memory)

**Decision**: extract server-side in `ai-chat-landing`, in a new `app/api/attach/route.ts`; the chat route injects the extracted text into the Dify `query` as a structured preamble.

**Rationale**: the chatflow is text-only (`inputs: {}`; the route posts `{inputs, query, response_mode, conversation_id, user}`). Client-side extraction would ship ~1–2 MB of parser bundles to the browser for a single-user tool; Dify-native file variables would need DSL surgery + a file-input node + re-publish for the same outcome. Server-side extraction keeps the change inside the app, uses Node-native parser libraries, and leaves the chatflow untouched. The extracted text rides the existing streaming path — no new transport.

**Alternatives considered**: (a) Dify `/v1/files/upload` + `files[]` on chat-messages — the app's own extraction is then needed anyway to ground the prompt, plus chatflow changes; rejected. (b) Client-side pdf.js/mammoth bundles — rejected (bundle weight, duplicated logic). (c) A sidecar tool call from the chatflow — rejected (new lane + DSL for plain text analysis).

## R2: Per-format extractors (server libraries, one per format family)

| Format | Library | Note |
|---|---|---|
| PDF | `pdf-parse` (import `pdf-parse/lib/pdf-parse.js` to avoid the package's debug self-test) | text layers only — scanned PDFs yield empty text → the honest "no readable text" note |
| Word `.docx` | `mammoth` (`extractRawText`) | modern format |
| Word `.doc` | `word-extractor` | legacy binary; a parse failure → honest unknown-format error |
| Excel `.xlsx`/`.xls`, CSV | `xlsx` (SheetJS) — sheets → CSV text | CSV may also take the plain-text path (it is text) |
| PowerPoint `.pptx` | `jszip` + a slide-text walk (`ppt/slides/slide*.xml`, `a:t` runs) | ~15 lines, no pptx-specific lib needed |
| PowerPoint `.ppt` (legacy) | — | no viable pure-JS extractor; honest refusal naming the save-as-.pptx remedy |
| TXT / JSON / XML | `fast-xml-parser` only for XML well-formedness/pretty output; TXT/JSON read as UTF-8 text (with a JSON parse for a helpful malformed error) | |

**Rationale**: each library is the standard tool for its format; no custom binary parsing except the small pptx slide walk.

## R3: Injection contract — structured preamble, capped at 24k chars

**Decision**: the chat route prepends to the user's question:
```
[Attached file: <name> (<type>, <N> characters extracted)]
<extracted text>

[End of attached file content]
---
User question: <the owner's text>
```
The text is bounded to **24,000 characters** (~6k tokens) with `[content truncated at 24,000 characters — the file is longer]` inserted when it happens (FR-008: the answer must not imply full coverage). Zero attachments → the request body is byte-identical to today (FR-007 pinned by a test).

**Rationale**: the preamble is model-readable, states provenance explicitly, and both edge notes ride inside it so the LLM cannot fabricate coverage. 24k chars keeps the largest 20 MB document's analysis inside the answer window while leaving room for the answer.

## R4: Server-side validation (trust boundary)

**Decision**: `/api/attach` validates (in order): size ≤ **20 MB** (413), extension on the 8-format allowlist (415), and a magic sniff where cheap — PDF must start `%PDF-`; zip-based families must start `PK` (docx/xlsx/pptx) — mismatch → 415 with the honest reason. Empty files → 422 ("file is empty"). Extraction failures (corrupt archive, malformed JSON/XML, legacy .ppt, encrypted PDF) → 422 with the specific honest reason. All errors are JSON `{error}` rendered inline by the composer.

**Rationale**: the picker's `accept` is a convenience, not a boundary — a renamed file or a direct POST must be refused server-side; the sniff catches the common mismatch class without a full content-type trust.

## R5: Test strategy (the owner's explicit requirement)

**Decision** — `quickstart.md` is the runnable test plan:
- **Unit (vitest, node env)**: `lib/attach/formats` (allowlist, size gate at exactly 20 MB ±1 byte, sniff mismatch), `preamble` (structure, the truncation flag at 24k ±1, empty-text note), `extract` (one tiny fixture per format asserting a unique token in the output; error fixtures asserting the honest notes), `app/api/attach` route (400/413/415/422 shapes with mocked FormData) and `app/api/chat` route (byte-identical body without attachments — a request-shape pin).
- **E2E (CDP, `scripts/attachment-check.mjs`)**: real browser, real Dify — set the file via `DOM.setFileInputFiles`, assert the chip, send, assert the streamed answer contains the fixture's unique token (`RELIABILITY_CHECK_42`), assert the chip clears after send; the error battery drives the same input with an unsupported file and an oversized temp file and asserts the inline honest errors; plus the text-only regression send.
- **Error handling** is a named layer in both suites (the list above), not an afterthought.