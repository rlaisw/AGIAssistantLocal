# Bug Verification: UTF-16 XML attachment refused as "not well-formed"

- **Slug**: the-ile-is-not-well-formed-xml
- **Tested**: 2026-11-17
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original symptom no longer reproduces: the UTF-16 RelMon XML now attaches and extracts (618 chars, identical to the byte-equivalent UTF-8 control), while genuinely malformed XML still fails honestly with the same error. All new pins and the full suite pass; no regressions.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | `curl -F "file=@relmon-utf16.xml" :3000/api/attach` | pass | `{"ok":true,...,"chars":618,...}` with parsed GraphDataPoint body |
| Reproduction control (UTF-8) | `curl -F "file=@relmon-utf8.xml" :3000/api/attach` | pass | identical `chars: 618` — decode parity with the pre-fix control |
| Honest-failure control | `curl -F "file=@broken.xml"` (malformed XML) | pass | still `{"error":"The file is not well-formed XML."}` — the refusal fires only for real failures now |
| New / updated tests | `npx vitest run lib/attach/extract.test.ts` | pass | 18/18 — includes the four decode-matrix pins (red before the fix) |
| Regression suite | `pnpm test` | pass | 175/175 across 24 files |
| Type-check | `pnpm typecheck` (`tsc --noEmit`) | pass | clean |
| Lint | `pnpm lint` | pass | 0 errors, 1 pre-existing warning (`stop-button-check.mjs`) |

## Output Excerpts

```
relmon-utf16.xml → {"ok":true,"filename":"relmon-utf16.xml","type":".xml","chars":618,"text":"{\n  \"?xml\": …
broken.xml       → {"error":"The file is not well-formed XML."}
Test Files  24 passed (24)
     Tests  175 passed (175)
```

## Residual Risks

- BOM-less UTF-16 files still fail with the honest (but for them, misleading) error — documented known limit; every Windows export tool in scope writes a BOM.
- A UTF-32LE file (BOM `FF FE 00 00`) is misread as UTF-16LE and fails honestly — near-nonexistent in practice, noted for completeness.
- Verified against a structurally identical repro of the owner's file (the original stayed on the Windows host); the full-file behavior follows from the same decode path.

## Recommendation

Close the bug — verified end-to-end: repro passes post-fix, honest failure preserved, suite green, no regressions. Commit the fix (extract.ts + extract.test.ts) together with the pending spec-043 deltas when you're ready.
