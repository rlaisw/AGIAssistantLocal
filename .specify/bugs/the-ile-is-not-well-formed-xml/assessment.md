# Bug Assessment: UTF-16 XML attachment refused as "not well-formed"

- **Slug**: the-ile-is-not-well-formed-xml
- **Created**: 2026-11-17
- **Source**: pasted text (a Windows Reliability Monitor XML export, `RelMonReport`, ~470 GraphDataPoint + Rac/Wer event entries, declared `<?xml version="1.0" encoding="utf-16" ?>`)
- **Verdict**: valid (reproduced live)
- **Severity**: medium

## Report (verbatim or summarized)

The owner attached a Windows Reliability Monitor export (`RelMonReport` XML: hourly stability `GraphDataPoint`s from 2026-10-17 to 2026-11-16 plus `RacEvents`/`WerEvents` — OUTLOOK.EXE hangs, OneDrive crashes, unexpected shutdowns) and got back:

> "The file is not well-formed XML."

The file is well-formed XML. Its declaration is `encoding="utf-16"` and Windows exports of this family (Reliability Monitor "Save all events as XML", Task Scheduler XML exports, PowerShell `Export-Clixml`/`Out-File`, legacy Notepad "Unicode") are UTF-16 encoded, typically with a BOM.

## Symptom

A valid, well-formed XML file encoded as UTF-16 (the declared and Windows-native encoding for this export family) is refused with "The file is not well-formed XML." The same content saved as UTF-8 attaches and analyzes fine. Expected: the UTF-16 file extracts and the answer is grounded in its data.

## Reproduction

1. Write a RelMon-shaped XML file (declaration `encoding="utf-16"` + any well-formed body) as UTF-16 with BOM (`python: open(...).write(xml.encode("utf-16"))`).
2. `curl -s -X POST -F "file=@relmon-utf16.xml" http://localhost:3000/api/attach` → `{"error":"The file is not well-formed XML."}` (reproduced 2026-11-17, dev server :3000).
3. Control: byte-identical content saved as UTF-8 → `{"ok":true,...,"chars":618,...}` with the parsed GraphDataPoint data (reproduced).

## Suspected Code Paths

- `ai-chat-landing/lib/attach/extract.ts:148-152` — `extractXml` does `buf.toString("utf-8")` unconditionally, then `XMLValidator.validate` on the decoded string. UTF-16 bytes decoded as UTF-8 produce interleaved NULs/mojibake, so validation fails on a well-formed document → the honest-looking but wrong error.
- `ai-chat-landing/lib/attach/extract.ts:139` (`extractJson`, `buf.toString("utf-8")`), `:45` (`.csv`), `:55` (`.txt`) — the same unconditional UTF-8 decode; a UTF-16 `.txt`/`.csv` would attach "successfully" as mojibake (worse: silently wrong text), a UTF-16 `.json` would fail "not valid JSON".
- `ai-chat-landing/lib/attach/formats.ts` gate — not implicated: the UTF-16 file passes the extension/magic gate and reaches the extractor (the error is the extractor's, a 422-shaped honest refusal).

## Root Cause Hypothesis

**High confidence.** All text-family extractors assume UTF-8 (`Buffer.toString("utf-8")`) with no BOM awareness. Windows-generated XML (and txt/csv/json) files are commonly UTF-16 with a BOM; decoding those bytes as UTF-8 corrupts them before parsing, so the XML validator fails and the file is falsely refused as malformed. The refusal itself is honest per FR-006 — the file never reaches the assistant — but the *reason* is wrong and a valid supported attachment is rejected (a false negative against FR-003/FR-001's promise for the XML family).

## Proposed Remediation

**Preferred**: one BOM-aware decode helper in `extract.ts` (≈8 lines, no new dependency): if the bytes start with `FF FE` decode as UTF-16LE, `FE FF` as UTF-16BE, `EF BB BF` as UTF-8 (strip the BOM); otherwise UTF-8 as today. Use it in `extractXml`, `extractJson`, `.txt`, `.csv` — one root fix for the whole text family, matching how the bytes actually arrive. Deletion beats branching: replace the four `buf.toString("utf-8")` call sites with the helper.

**Alternatives**:
- Fix only `extractXml` — smallest diff, but leaves UTF-16 `.txt`/`.csv` silently garbling (the worse failure mode).
- Declaration-sniff `encoding="..."` from the raw bytes — over-engineering; every Windows tool in scope writes a BOM, and BOM-less UTF-16 is the rare case.

**Files likely to change**:
- `ai-chat-landing/lib/attach/extract.ts`
- `ai-chat-landing/lib/attach/extract.test.ts`

**Tests to add or update**:
- Unit: UTF-16LE-with-BOM XML fixture → `ok: true`, extracted text contains a known `<Value>`/event token (red first; it currently returns the not-well-formed error).
- Unit: UTF-16LE `.txt` and `.json` decode correctly; UTF-8-with-BOM XML still parses (BOM stripped).
- Existing suite must stay green (UTF-8 paths unchanged).

## Risks & Considerations

- BOM-less UTF-16 (rare on Windows) stays unsupported — document as a known limit, error remains honest.
- UTF-16BE (`FE FF`) support is one branch of the same helper; big-endian files are near-nonexistent but cost ~1 line.
- No contract change: `/api/attach` response shape and the FR-007 no-attachment byte-identical guarantee are untouched.
- The chatflow side needs nothing — the preamble pipeline is encoding-agnostic once extraction yields real text.

## Open Questions

- None blocking. [Optional, for the fix pass: add a UTF-16 fixture generator line to `tests/fixtures/attach/generate.mjs` so the CDP battery exercises it — unit pins are sufficient for the gate.]
