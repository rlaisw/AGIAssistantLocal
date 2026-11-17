# Bug Fix: UTF-16 XML attachment refused as "not well-formed"

- **Slug**: the-ile-is-not-well-formed-xml
- **Fixed**: 2026-11-17
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Added a BOM-aware text decoder to the attachment extractors so UTF-16/UTF-8-BOM text files (the Windows RelMon/schtasks/Export-Clixml export family) decode correctly instead of being garbled into a false "The file is not well-formed XML." refusal. One helper now feeds all four text-family extractors (`.xml`, `.json`, `.txt`, `.csv`).

## Changes

| File | Change | Notes |
|------|--------|-------|
| `ai-chat-landing/lib/attach/extract.ts` | modified | new `decodeText()` helper (FF FE → UTF-16LE, FE FF → UTF-16BE via `swap16()`, EF BB BF → UTF-8 stripped, plus stray `\uFEFF` strip); the four `buf.toString("utf-8")` call sites (`.csv`, `.txt`, `extractJson`, `extractXml`) now call it |
| `ai-chat-landing/lib/attach/extract.test.ts` | added tests | four red-first pins for the decode matrix |

## Diff Highlights (optional)

```ts
function decodeText(buf: Buffer): string {
  if (buf[0] === 0xff && buf[1] === 0xfe) return stripBom(buf.subarray(2).toString("utf16le"))
  if (buf[0] === 0xfe && buf[1] === 0xff) {
    const body = buf.subarray(2, buf.length - (buf.length % 2))
    return stripBom(Buffer.from(body).swap16().toString("utf16le"))
  }
  if (buf[0] === 0xef && buf[1] === 0xbb && buf[2] === 0xbf)
    return buf.subarray(3).toString("utf-8")
  return buf.toString("utf-8")
}
```

## Tests Added or Updated

- `lib/attach/extract.test.ts` — UTF-16LE XML with BOM extracts its token (was red: "not well-formed" refusal)
- `lib/attach/extract.test.ts` — UTF-16LE `.txt` and `.json` with BOM decode their tokens (was red: mojibake / "not valid JSON")
- `lib/attach/extract.test.ts` — UTF-16BE XML with BOM extracts (constructed via `swap16()`; Node has no `utf16be`)
- `lib/attach/extract.test.ts` — UTF-8 BOM is stripped before parsing

## Local Verification

- Commands run: `npx vitest run lib/attach/extract.test.ts` → red first (3 failed), green after fix (18/18); `pnpm test` → **175/175** (24 files); `pnpm typecheck` → clean; `pnpm lint` → 1 pre-existing warning (`stop-button-check.mjs`), 0 errors.
- Manual/live: re-ran the assessment repro against the dev server — `curl -F "file=@relmon-utf16.xml" :3000/api/attach` now returns `{"ok":true,...,"chars":618,...}` with the parsed GraphDataPoint body, byte-for-byte the same `chars` count as the UTF-8 control; the control still passes.
- `graphify update .` refused to write (pre-existing `specs_036` saved-node mismatch, unrelated to this change).

## Deviations from Assessment

None. Scope stayed inside the two files the assessment named; no new dependency.

## Follow-ups

- Not committed yet — say the word and this lands with the other pending spec-043 deltas.
- Known limit (unchanged): BOM-less UTF-16 stays unsupported and still fails honestly ("not well-formed XML") — rare in practice; every Windows export tool in scope writes a BOM.
- Optional: add a UTF-16 fixture to `tests/fixtures/attach/generate.mjs` if the CDP battery should exercise it end-to-end.
