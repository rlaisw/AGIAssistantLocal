# Implementation Plan: Chat attachment upload + analysis (043)

## Summary

Activate the composer's paperclip (currently a dead ghost button) so the owner can attach a PDF, Word, Excel, PowerPoint, TXT, CSV, JSON, or XML file, and have the answer grounded in that file's **genuine extracted text**. Extraction happens server-side in the Next.js app (in-memory, no persistence), because the Dify chatflow is text-only today (`inputs: {}`) — the extracted text is injected into the query as a structured preamble, so the LLM analyzes it through the existing streaming pipeline with zero chatflow/DSL changes. The owner's explicit requirement — unit tests + end-to-end cases + error handling — is delivered as `quickstart.md` (the test plan) and tasks.

## Technical Context

**Language/Version**: TypeScript / Node (Next.js 16.4.2, React 19) inside `ai-chat-landing/`; pnpm.

**Primary Dependencies (new, each doing real format work — no hand-rolled parsers)**: `pdf-parse` (PDF text), `mammoth` (Word .docx raw text), `word-extractor` (legacy .doc), `xlsx` (SheetJS: .xlsx/.xls/.csv tables → CSV text), `jszip` (.pptx slides → text runs from `ppt/slides/*.xml`), `fast-xml-parser` (XML well-formedness + pretty output). All server-only (imported exclusively from the API route).

**Storage**: none — files and extracted text live in memory for one request; per the clarified privacy posture, content travels to the configured LLM provider exactly like chat text, with no server persistence.

**Testing**: vitest (node env — `lib/**/*.test.ts` + `app/api/**/*.test.ts` already wired) for pure-logic units and per-format extraction against tiny fixtures; a CDP acceptance script `scripts/attachment-check.mjs` (the `landing-check.mjs` pattern) for end-to-end; the error-handling battery rides both layers.

**Target Platform**: the local chat UI (`pnpm dev`/`start`) → existing `app/api/chat/route.ts` → Dify.

**Project Type**: web app sub-project — UI composer + two API routes + pure-logic lib modules.

**Performance Goals**: extraction + send inside the 30 s answer target (SC-001) for typical documents (a few pages / few hundred rows); the 20 MB cap keeps extraction bounded.

**Constraints**: 20 MB cap (FR-005, confirmed 2026-11-17); one attachment per message; 8 formats (FR-001); text-only sends byte-identical (FR-007); the injected content is capped at **24,000 characters** (~6k tokens) with the truncation named in the preamble (FR-008); scan-only PDFs yield an honest "no readable text" (OCR out of scope).

**Scale/Scope**: ~4 new lib modules + 1 new API route + composer changes + 2 deps-level test suites + 1 CDP script.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **One runnable check per non-trivial behavior**: format matrix, size gate, preamble builder + truncation naming, each extractor (fixture-backed), the route's honest 422s — all unit-pinned; the E2E proves attach→answer grounding. PASS by design.
- **Measured, not assumed**: SC-001 latency measured in the E2E (time from send to first grounded answer); SC-002 eight fixtures; SC-003 refusal battery 100%. PASS.
- **Lazy engineering**: extraction is server-side in the existing app (no Dify DSL surgery, no new service); each format uses a proven library; the preamble rides the existing query field. PASS.
- **Anti-fabrication**: the "no readable text" and "truncated" statements are explicit in the preamble so the answer cannot imply full coverage; extraction failures are honest refusals. PASS.
- **Suite green before commit**: vitest + the CDP script + `pnpm typecheck && pnpm lint` (never `pnpm build` while `pnpm dev` runs — house rule). PASS.

**Gate verdict: PASS** (re-checked post-design: unchanged).

## Project Structure

Single sub-project (`ai-chat-landing/`). New/changed (implementation orientation):

- `lib/attach/formats.ts` — the 8-format allowlist (extensions + MIME families), human-readable refusal messages, size gate (20 MB), magic-sniff for PDF (`%PDF-`) and zip-family (`PK`).
- `lib/attach/extract.ts` — `extractText(file: {name, bytes}): Promise<{text, note?}>` dispatching per format; honest notes for "no readable text", legacy `.ppt`, malformed JSON/XML, corrupt archives.
- `lib/attach/preamble.ts` — the injection builder: `[Attached file: name (type, N chars extracted)]\n<text>\n[End of attached file]\n---\nUser question: …`, 24,000-char cap with the truncation named.
- `app/api/attach/route.ts` — POST multipart/FormData → validate → extract → `{ok, filename, chars, text, truncated, note?}` or an honest `422 {error}`.
- `app/api/chat/route.ts` — accept optional `attachments: AttachmentPart[]` (`{name, type, chars, text, truncated?, note?}` — `lib/attach/preamble.ts`), build the preamble into the Dify `query`; **no attachment → body byte-identical to today** (FR-007).
- `app/page.tsx` — wire the paperclip: a hidden `<input type="file" accept=…>` + click handler; selected-file chip (name + remove) in the composer; client-side pre-validation (type/size) with inline honest errors; on send, POST the file to `/api/attach`, then include the extraction in the chat request; errors render inline (the house's existing inline-error pattern).
- `tests/fixtures/attach/` — one tiny real file per family (pdf, docx, xlsx, pptx, txt, csv, json, xml) plus corruption/oversize/empty/image-only-pdf fixtures for the error battery.
- `scripts/attachment-check.mjs` — the CDP E2E (set the file input via `DOM.setFileInputFiles`, chip assertion, send, answer-grounding assertion on a fixture-unique token, chip-clear, error cases).

Not changed: the Dify chatflow (text-only by construction), the streaming/stop machinery, the model selector, the history proxy.

## Complexity Tracking

Moderate: 3 linchpin decisions — server-side extraction (vs. Dify native files, rejected: DSL surgery + file-variable + re-publish), query-preamble injection (vs. new sidecar tool, rejected: the analysis is genuinely LLM work over text), in-memory only (privacy posture confirmed). Each format is a library call, not custom parsing, except the small `.pptx` slide-text walk.