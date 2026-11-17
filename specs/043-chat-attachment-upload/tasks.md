---
description: "Task list for Chat attachment upload + analysis"
---

# Tasks: Chat attachment upload + analysis (043-chat-attachment-upload)

**Input**: Design documents from `specs/043-chat-attachment-upload/` (plan.md, spec.md, research.md, data-model.md, contracts/attach-api.md, quickstart.md)

**Tests**: INCLUDED — the owner explicitly required unit tests + end-to-end cases + error handling (quickstart.md is the test plan). Tests are written FIRST in each story (red), then implemented (green).

**Organization**: Two user stories — US1 (P1) attach→send→grounded answer; US2 (P2) honest errors. US2's gates are foundational for safe US1 delivery; error pins are written alongside US1's as the batteries interleave.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependencies on incomplete tasks)
- Exact file paths in every description (all paths under `ai-chat-landing/` unless stated)

---

## Phase 1: Setup

- [X] T001 Install the server-side extraction dependencies in `package.json`: `pdf-parse`, `mammoth`, `word-extractor`, `xlsx`, `jszip`, `fast-xml-parser` (pnpm; no client-side parser bundles)
- [X] T002 [P] Generate the tiny committed fixtures in `tests/fixtures/attach/` (quickstart.md list): `sample.pdf` with `RELIABILITY_CHECK_42`, `sample.docx` with `WORD_TOKEN_7`, `sample.xlsx` with `EXCEL_TOKEN_9`, `sample.pptx` with `SLIDE_TOKEN_3`, `sample.txt`, `sample.csv` with `CSV_TOKEN_5`, `sample.json` with `JSON_TOKEN_1`, `sample.xml` with `XML_TOKEN_8`, plus the error fixtures (`scan-only.pdf`, `corrupt.pdf`, `renamed-docx-as-pdf.pdf`, `broken.json`, `broken.xml`, `empty.txt`, `legacy.ppt` stub)

---

## Phase 2: Foundational (blocking prerequisites)

- [X] T003 Implement the format gate in `lib/attach/formats.ts` per contracts/attach-api.md: the 8-family allowlist (extensions pdf/doc/docx/xls/xlsx/ppt/pptx/txt/csv/json/xml), the **20 MB** size gate (exactly 20 MB passes, +1 byte refuses with the measured size named), magic sniff (PDF must start `%PDF-`; docx/xlsx/pptx must start `PK` — mismatch → the content/extension-mismatch reason), and the human-readable refusal messages
- [X] T004 [P] Implement the preamble builder in `lib/attach/preamble.ts` per research R3: header `[Attached file: <name> (<type>, <N> characters extracted)]` with the note and (when applicable) the `[content truncated at 24,000 characters — the file is longer]` marker; content bounded to **24,000** chars; footer + `---` + `User question: <text>` (or `(analyze this file)` when empty)
- [X] T005 [P] Implement `extractText` in `lib/attach/extract.ts` per research R2: dispatch per format (`pdf-parse` via `pdf-parse/lib/pdf-parse.js`; `mammoth.extractRawText` for docx; `word-extractor` for .doc; `xlsx` sheets → CSV text for xlsx/xls/csv; `jszip` slide walk (`ppt/slides/slide*.xml`, `a:t` runs) for pptx; UTF-8 text for txt/csv/json (JSON parse for the malformed error); `fast-xml-parser` well-formedness for xml) with the honest notes: scan-only PDF → `no readable text (scanned/image-only PDF — OCR is not enabled)`, legacy `.ppt` → the save-as-.pptx refusal, corrupt archives/malformed JSON-XML/encrypted PDF → the specific honest reason

**Checkpoint**: the gate + preamble + extractors are pure logic — their units can be written and green before any route exists.

---

## Phase 3: User Story 1 - Attach, send, grounded answer (Priority: P1) 🎯 MVP

**Goal**: paperclip → native file dialog → attached chip → send → answer grounded in the file's genuine content.

**Independent Test**: quickstart E2E-1..5 — attach `sample.pdf`, send, the streamed answer contains `RELIABILITY_CHECK_42`; the eight-format matrix's tokens all appear; < 30 s for E2E-1; text-only sends identical (E2E-4).

### Tests for User Story 1 (write first, expect red)

- [X] T006 [P] [US1] Unit pins in `lib/attach/formats.test.ts` and `lib/attach/preamble.test.ts`: allowlist membership + refusal list text; size gate at 20 MB ±1 byte; sniff mismatch; preamble header/footer/question/`(analyze this file)`; truncation at 24,000 ±1 char (the marker named)
- [X] T007 [P] [US1] Fixture extraction pins in `lib/attach/extract.test.ts`: each format's unique token present; the error fixtures' honest notes (the EH matrix at unit level)

### Implementation for User Story 1

- [X] T008 [US1] Implement `app/api/attach/route.ts` per contracts/attach-api.md: multipart `file` → validate (size 413, extension 415, sniff 415, empty 422, extraction failure 422) → `{ok, filename, type, chars, text, truncated:false, note?}`; in-memory only, no writes
- [X] T009 [US1] Extend `app/api/chat/route.ts`: accept optional `attachments: [{name, type, chars, text, truncated, note?}]`; when present, build the preamble into the Dify `query`; when absent, the upstream body stays **byte-identical** (request-shape pin in `app/api/chat/route.test.ts`)
- [X] T010 [US1] Wire the composer in `app/page.tsx`: hidden `<input type="file" accept=…>` triggered by the paperclip; post the file to `/api/attach`; chip (filename + spinner + remove ×; new selection replaces); client pre-checks (extension allowlist + 20 MB); send blocks until the chip is `ready` (or reports "still reading the file…"); include the extraction in the `/api/chat` body; clear the chip on send (one-shot)
- [X] T011 [US1] E2E CDP script `scripts/attachment-check.mjs` (the `scripts/landing-check.mjs` pattern; `DOM.setFileInputFiles`): E2E-1 (pdf token in the answer, chip clears, < 30 s), E2E-2 (xlsx with no question), E2E-3 (remove before send → no preamble), E2E-4 (text-only regression), E2E-5 (eight-family matrix)

**Checkpoint**: US1 fully functional — attach → grounded answer works end-to-end.

---

## Phase 4: User Story 2 - Honest errors (Priority: P2)

**Goal**: every refusal is honest, inline, and recoverable; nothing silently drops.

**Independent Test**: quickstart EH-1..9 — the refusals render inline with the typed text preserved; scan-only and truncation notes ride the preamble; no broken attachment ever sends.

### Tests for User Story 2 (write first, expect red)

- [X] T012 [P] [US2] Route-level error pins in `app/api/attach/route.test.ts`: the 413/415/422 matrix with exact message shapes (oversize names 20 MB + measured size; unsupported names the list; sniff mismatch names the content mismatch; empty/legacy/corrupt names their specifics)
- [X] T013 [P] [US2] E2E error cases in `scripts/attachment-check.mjs`: EH-1 (unsupported file inline refusal), EH-2 (oversized temp file), EH-3 (one corrupt fixture), EH-4 (scan-only note), EH-8 (route unreachable → inline honest error), EH-9 (send while extracting waits/reports)

### Implementation for User Story 2

- [X] T014 [US2] Implement the inline error surface in `app/page.tsx`: the house's inline-error pattern above the composer (reason verbatim, dismiss on next action), typed text preserved, the chip removed on failure, retry allowed after fixing the file
- [X] T015 [US2] Harden the extraction notes through the pipeline: `attach` response `note` → composer chip note (visible before send) → preamble header (the LLM sees it) — the scan-only/OCR and truncation statements travel intact (EH-4/EH-7)

**Checkpoint**: both stories independently functional; every error path honest.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T016 Full battery: `pnpm test` (vitest — all unit classes), `pnpm typecheck`, `pnpm lint` inside `ai-chat-landing/` (house rule: never `pnpm build` while `pnpm dev` runs); run `node scripts/attachment-check.mjs` against the live stack
- [X] T017 Update `ai-chat-landing/README.md` (the attachment feature surface + the 20 MB cap + the eight formats + the legacy-.ppt limitation) and `AGENTS.md`'s ai-chat-landing rule line
- [X] T018 Commit and push the feature (working tree clean; the fixtures included)

---

## Dependencies & Execution Order

- **T001 → T002** (deps before fixtures generation if the generators need them) — T002 can run first for the text fixtures (txt/csv/json/xml are hand-written), the binary ones (pdf/docx/xlsx/pptx) need tiny builders or pre-made files.
- **T003/T004/T005** after T001; parallel (three disjoint lib files).
- **US1 (T006..T011)**: tests (T006/T007) after T003-T005; T008 after T003/T005; T009 after T004; T010 after T008/T009; T011 after T010.
- **US2 (T012..T015)**: T012 after T008; T014 after T010; T013/T015 after T014.
- **Polish (T016..T018)** after both stories.

### Parallel Opportunities

T003/T004/T005 (three lib files); T006/T007 (two test files); T012 alongside T013 (different files).

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 + Phase 2 (deps, fixtures, gate, preamble, extractors)
2. Phase 3 (US1) — STOP and VALIDATE: quickstart E2E-1 passes (attach → grounded answer, chip lifecycle, latency) and the unit batteries are green.

### Incremental Delivery

1. MVP (US1) → 2. honest errors (US2) → 3. Polish (full battery, README, commit)

---

## Notes

- The Dify chatflow is untouched by design (text-only; the preamble rides the query). No DSL publish step.
- Privacy posture (clarified): extraction in-memory; content goes to the configured LLM provider like chat text; no server persistence.
- 24,000-char preamble cap and the 20 MB file cap are pinned with ±1 boundary tests — do not soften them.
- The E2E needs the Dify stack up and `pnpm dev` running; the CDP pattern is the existing `scripts/landing-check.mjs`.
- Legacy `.ppt` is a documented honest-refusal limitation (EH-5); OCR is out of scope (EH-4).
- Commit per logical group; `pnpm test && pnpm typecheck && pnpm lint` before each commit.
---

## Phase 6: Convergence

- [X] T019 Add the attachments section to `ai-chat-landing/README.md` per T017 (partial): the paperclip flow, the 20 MB cap, the eight formats, the 24,000-char preamble cap, the honest edges (scanned PDFs, legacy .ppt, malformed files), and the `scripts/attachment-check.mjs` acceptance script — the T017 script's anchor never matched, so only AGENTS.md carries the documentation
