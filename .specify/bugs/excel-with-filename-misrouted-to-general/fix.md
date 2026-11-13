# Bug Fix: hermes_file classifier strengthened — the verbatim prompt now routes to xls_write_v2

- **Slug**: excel-with-filename-misrouted-to-general
- **Fixed**: 2026-11-13T03:16:04Z
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The `hermes_file` class topic now explicitly covers the misrouted shape — "open <app> with file name X, type Y at cell Z", cell-write vocabulary, and a never-knowledge-base clause — and the live replay of the verbatim prompt routes to the Hermes lane and completes via `xls_write_v2` (0.6 s, fronted, verified). The flash router handles it correctly with the strengthened examples; no model re-pinning needed.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `dify/AGIAssistant/AGI_Assistant.yml` `intent_router.classes[hermes_file].topic` | strengthened + published | adds: ANY 'type/write/put a VALUE into a cell' phrasing; ANY 'open <app> with file name X' / 'open <app> and type X' phrasing; the verbatim misrouted prompt as the canonical example; "NEVER knowledge-base questions, even though they mention a file name or a spreadsheet cell" |

## Local Verification

- **Live replay of the exact failing prompt** through the real chatflow (`POST /v1/chat-messages`, streaming): status 200; the answer starts *"This is an Office task — specifically Excel… 'open Excel and write/type X in cell Y' is a SIMPLE literal write -> xls_write_v2"* — the Hermes lane took it.
- **The audit row**: `xls-write-v2 | executed | 0.6 s | test1.xlsx: status ok, path C:\OfficeMCP\test1.xlsx, size 8454, existed False, text_ok True, fronted True` — the write completed, verified, and Excel fronted.

## Deviations from Assessment

None — option (a) of the preferred remediation (strengthened examples with the flash model) worked on the live replay; the model re-pinning fallback (option b) was not needed.

## Follow-ups

- Watch for over-eager routing: if genuine knowledge-base questions mentioning Excel/cells start landing on the Hermes lane, tighten the example wording (the never-knowledge-base clause is the guard).
- The General branch's fabricated-then-retracted turn (a flash model behavior) is now a less-traveled path; no separate fix planned.
