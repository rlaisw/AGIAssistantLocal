# Bug Fix (round 2): DisplayAlerts=False around Excel SaveAs — the overwrite prompt headless COM could not show

- **Slug**: xls-saveas-method-failed
- **Fixed**: 2026-11-14T07:10:00+00:00 (round 2; round 1 — GetActiveObject attach + honest pre-close + busy wrap — is below and stays shipped)
- **Assessment**: ./assessment.md
- **Status**: applied — the money pair and every historical failure scenario now pass live

## Summary

Round 2 adds the one line the verification isolated: `xl.DisplayAlerts = False` scoped around `wb.SaveAs(path)` (restored in `finally`). Excel — alone of the three office apps — raises the "file already exists, replace?" confirmation dialog on SaveAs-to-existing-path; in headless COM the dialog cannot be shown and the call dies with `0x800A03EC`. With alerts suppressed, the overwrite is silent and every previously-failing scenario completes; a try/except around SaveAs re-raises any residual failure as the honest recovered-twin envelope instead of the raw COM tuple.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/office_lanes/proxy.py` | modified | `_XLS_WRITE_TEMPLATE`: `xl.DisplayAlerts = False` → `wb.SaveAs(path)` → `finally: xl.DisplayAlerts = True`; SaveAs wrapped — failure raises `blocked: saving <name> failed (…); the file may be open in Excel under a recovered or temporary name (close the recovered copies in Excel or choose a different name), then ask again` |
| `tests/unit/test_office_v2.py` | added test | `test_xls_saveas_silences_the_overwrite_prompt` (below) |

## Diff Highlights (optional)

```python
xl.DisplayAlerts = False
try:
    wb.SaveAs(path)
except Exception as _e:
    raise RuntimeError(
        'blocked: saving %s failed (%s); the file may be open in Excel '
        'under a recovered or temporary name (close the recovered copies '
        'in Excel or choose a different name), then ask again'
        % (d['name'], str(_e)[:200]))
finally:
    xl.DisplayAlerts = True
```

## Tests Added or Updated

- `test_office_v2.py::test_xls_saveas_silences_the_overwrite_prompt` — pins `DisplayAlerts = False` **before** `wb.SaveAs(`, restored **after** it (the `finally:`), and the honest recovered-twin wrap text.
- Round-1 pins unchanged and green: running-app-first attach, verified+honest pre-close (refusal before SaveAs), busy-app wrap, COM-init-before-Dispatch.

## Local Verification

- Commands run: `pytest tests/unit/test_office_v2.py` → **19 passed**; full `pytest tests/unit` → **655 passed, 0 failed**; `ruff check` → clean; `deploy redeploy` → rebuilt, health ok, tools 53/53.
- **Live money pair** (conversation `xls-saveas-fix2-verify`, clean Excel instance):
  - WRITE onto the **existing** `discriminator-fresh-20261114b.xlsx` → **ok, "replaced the existing workbook", existed: true** (0.8 s) — the exact class that raw-failed five times today.
  - SAME-PATH REPEAT immediately after (the workbook left open by the write) → **ok, "replaced the existing workbook", existed: true** (0.5 s) — the assessment's original failing condition, end-to-end.
  - **`workbook.xlsx`** — the default name from the user's first failure, still held by the Document Recovery twins → **ok, "replaced the existing workbook"** (0.7 s).
- All three audit rows: `decision: executed`.

## Deviations from Assessment

- Round-2 change is a **refinement discovered by the round-1 verification** (recorded in `test.md`): the assessment's preferred remediation (attach + honest pre-close) was necessary but insufficient for Excel — the isolated root cause is the overwrite-confirmation dialog, closed by `DisplayAlerts = False`. Applied per the test report's recommendation; no assessment re-run needed (mechanism now fully identified and fixed).
- Word/PowerPoint templates deliberately untouched this round: both are live-proven replacing existing paths silently (Word's SaveAs2 and PowerPoint's SaveAs do not prompt).

## Follow-ups

- `/speckit.bug.test` round 2 should re-run the money pair plus the standard battery; the recovered-twin wrap's live demonstration is optional (a twin-held target now succeeds through the honest close — the wrap is the named fallback for any state that still refuses).
- Close the leftover recovered copies in Excel at will; the day's failed attempts left some unsaved Book debris only in the killed instance (gone with it).
- Long-run watch: any new `blocked: saving … failed` rows in the audit trail name their cause — none expected for the classes proven today.
