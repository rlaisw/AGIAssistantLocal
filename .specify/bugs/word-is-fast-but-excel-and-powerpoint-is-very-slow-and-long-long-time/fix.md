# Bug Fix: office v2 extended to Excel and PowerPoint (156.4/143.9 s → 0.6/3.4 s)

- **Slug**: word-is-fast-but-excel-and-powerpoint-is-very-slow-and-long-long-time
- **Fixed**: 2026-11-13T02:40:32Z
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The doc_write_v2 discipline extended to the other two Office apps: `xls_write_v2` (literal cell map, no formulas, per-cell read-back verification) and `ppt_write_v2` (one-slide literal title/text), both single-hop, same-path pre-close (lock-free repeats), leave-open, full-screen + front. Live: Excel **0.6 s** (was 156.4 s), PowerPoint **3.4 s** (was 143.9 s).

## Changes

| File | Change | Notes |
|------|--------|-------|
| `office_lanes/proxy.py` | `_XLS_WRITE_TEMPLATE`, `_PPT_WRITE_TEMPLATE` + `write_xls`/`write_ppt` | live-probed first (assessment risk note); **PowerPoint COM quirk pinned**: `ActiveWindow.HWND` unusable via dynamic dispatch → `FindWindow('PPTFrameClass')`; Excel uses `ActiveWindow.Hwnd`; both verify in code, pre-close same-path, front via the ALT-tap |
| `server.py` | +2 tools (47 total) | `xls_write_v2(cells, name?, conversation_id)` — A1-style address validation `^[A-Za-z]{1,3}[1-9][0-9]{0,6}$` and **'='-formula rejection** (data, never code); `ppt_write_v2(title, text?, name?, conversation_id)`; honest created/REPLACED, fronted reported, audit rows with cid |
| DSL | routing extended + both tools on the lane | WORD → doc_write_v2; EXCEL "open Excel and write X in cell Y" → xls_write_v2; POWERPOINT "make a slide titled X" → ppt_write_v2; published |
| `tests/unit/test_office_v2.py` | +3 pins | both templates' discipline (pre-close, verify, front, no-Formula) |

## Local Verification

- Probes live before wiring: Excel write+verify+front ✓ (`text_ok True, fronted True`); PowerPoint needed 3 attempts (HWND method/member quirks → PPTFrameClass) then ✓
- **Deployed live proof**: `xls_write_v2` = **0.6 s** (`created a new workbook, fronted True`); `ppt_write_v2` = **3.4 s** (`created a new presentation, fronted True`) — audit durations
- 620 unit green, ruff clean, 47 tools synced, chatflow published

## Deviations from Assessment

None — the preferred remediation landed as written; the assessment's PowerPoint-COM-quirk risk note proved out exactly (live-probing caught the HWND issue before shipping).

## Follow-ups

- Watch the next real "open Excel and write X in cell Y" / "make a slide titled X" in the Chat UI — expected seconds, fronted, honest created/replaced notes.
- Multi-slide decks, formulas, and existing-file edits remain on `hermes_office_task` (the complex class) by design.
