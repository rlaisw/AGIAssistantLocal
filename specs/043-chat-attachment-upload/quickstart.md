# Quickstart: the 043 test plan (unit + end-to-end + error handling)

The owner's explicit requirement: this feature ships with **unit tests, end-to-end test cases, and error handling**. This document is that plan — runnable at each layer.

## Prerequisites

- `ai-chat-landing/` with the new deps installed; `pnpm dev` running (never run `pnpm build` while dev runs — shared `.next/`).
- The Dify stack up (the chat route target) for the E2E only.
- Fixtures in `tests/fixtures/attach/` — tiny real files, one per format family, each carrying a unique token used for grounding assertions:
  `sample.pdf` (`RELIABILITY_CHECK_42`), `sample.docx` (`WORD_TOKEN_7`), `sample.xlsx` (`EXCEL_TOKEN_9`), `sample.pptx` (`SLIDE_TOKEN_3`), `sample.txt`, `sample.csv` (`CSV_TOKEN_5`), `sample.json` (`{"token": "JSON_TOKEN_1"}`), `sample.xml` (`<token>XML_TOKEN_8</token>`) — plus error fixtures: `scan-only.pdf` (no text layer), `corrupt.pdf` (10 bytes, bad magic), `broken.json`, `broken.xml`, `empty.txt`, `legacy.ppt` (stub bytes), `renamed-docx-as-pdf.pdf` (a zip payload with a .pdf name).

## A. Unit battery (vitest; run first — red before implementation)

```
cd ai-chat-landing && pnpm test
cd ai-chat-landing && pnpm typecheck && pnpm lint
```

Pinned classes:
1. **format gate** (`lib/attach/formats.test.ts`): the 8-family allowlist incl. `.doc`/`.xls`/`.ppt` extensions; unsupported ext refused with the list named; size gate at exactly 20 MB passes, 20 MB + 1 byte refused with the measured size in the message; magic-sniff mismatch (`.pdf` starting `PK`) refused with the content-mismatch reason.
2. **preamble** (`lib/attach/preamble.test.ts`): header/footer structure; the question embedded (and `(analyze this file)` when empty); truncation at 24,000 chars — 24,000 passes untruncated, 24,001 truncates with the named marker; the extraction note rides the header.
3. **extractors** (`lib/attach/extract.test.ts`): per-format fixture → the unique token present in the extracted text; scan-only PDF → empty text + the honest note; corrupt/legacy fixtures → the specific honest errors.
4. **attach route** (`app/api/attach/route.test.ts`): 413/415/422 shapes for oversize, unsupported, renamed, empty; 200 shape with chars/text/note.
5. **chat route** (`app/api/chat/route.test.ts` — extend): **no attachment → the Dify body is byte-identical** (request-shape pin); with attachment → the preamble in `query` (header, content, footer, question).

## B. End-to-end cases (CDP script `scripts/attachment-check.mjs`, real browser + real Dify)

Pattern: the existing `scripts/landing-check.mjs` (Chrome via CDP; `DOM.setFileInputFiles` on the hidden input).

| # | Case | Expected |
|---|---|---|
| E2E-1 | attach `sample.pdf`, type "what does this file say about reliability?", send | chip shows `sample.pdf`; streamed answer **contains `RELIABILITY_CHECK_42`**; chip clears after send; answer arrives < 30 s (SC-001) |
| E2E-2 | attach a workbook (`sample.xlsx`), send with no text | the answer describes the sheet content and contains `EXCEL_TOKEN_9` |
| E2E-3 | attach → remove (×) before sending → send plain text | the question goes with **no attachment payload** (no preamble; text-only path) |
| E2E-4 | text-only send (no attachment at all) | identical UX/streaming as today (FR-007 regression) |
| E2E-5 | eight-format matrix (one E2E per family, or one run each) | every family's unique token appears in its answer (SC-002) |

## C. Error-handling cases (first-class; unit or E2E as marked)

| # | Case | Layer | Expected |
|---|---|---|---|
| EH-1 | unsupported file (.exe/.zip/.png) set on the input | E2E + unit | inline refusal naming the supported list; nothing sent; typed text preserved (FR-004) |
| EH-2 | 21 MB file | E2E + unit | inline refusal naming 20 MB and the measured size (FR-005) |
| EH-3 | corrupt PDF / broken JSON / broken XML / empty file | unit + E2E (one) | the specific honest reason; nothing sent (FR-006) |
| EH-4 | scan-only PDF | unit + E2E | attaches with the "no readable text — OCR not enabled" note; the answer says it could not read text, never fabricates a summary |
| EH-5 | legacy `.ppt` | unit | honest refusal + the save-as-.pptx remedy |
| EH-6 | renamed `docx` as `.pdf` | unit | content/extension mismatch refusal |
| EH-7 | truncated (>24k chars) attachment | unit (preamble) | the injected content carries the truncation marker; the answer states it did not see everything (FR-008) |
| EH-8 | attach route unreachable / 5xx | E2E (stop the dev server mid-flight or mock) | inline honest error; nothing sent; chip removed |
| EH-9 | send while extraction in flight | E2E | the send waits for `ready` (or reports "still reading the file…") — never sends a broken attachment |

## D. Verification flow

1. `python -m pytest tests/unit`-free: this is a Node project — run `pnpm test` (vitest), `pnpm typecheck`, `pnpm lint` (house rule: not `pnpm build` while dev runs).
2. Fixtures generated once (committed, tiny).
3. E2E: `node scripts/attachment-check.mjs` with `pnpm dev` + Dify up.
4. Manual spot-check in the real UI (the owner's screenshot path): paperclip → native dialog → attach → grounded answer.

## Post-verification

- One attachment per message, 20 MB cap, eight formats, in-memory only (privacy posture) — all as clarified 2026-11-17. Legacy `.ppt` is the one documented limitation (honest refusal with the save-as remedy).