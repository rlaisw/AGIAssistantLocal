# Bug Verification: Excel same-path repeat verified end-to-end — overwrite prompt silenced, every historical failure scenario now passes

- **Slug**: xls-saveas-method-failed
- **Tested**: 2026-11-14T07:15:00+00:00 (round 2; overwrites the round-1 report — see History)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md (round 2)
- **Result**: **verified** — the original symptom no longer reproduces in any form; the exact failing condition (same-path repeat onto an open workbook) completes live, as does the existing-file overwrite that produced the raw error all day

## History

Round 1's verification verdict was **failed**: the shipped hardening (GetActiveObject attach, honest verified pre-close, busy-app wrap) was live-proven on Word and PowerPoint but the Excel repeat still raw-failed — which isolated the true root cause: Excel alone raises the "replace existing file?" dialog on SaveAs-to-existing-path, and headless COM cannot show it → `0x800A03EC`. Round 2 added `xl.DisplayAlerts = False` scoped around `wb.SaveAs` plus the honest recovered-twin wrap. The full evidence chain is in `fix.md` (Deviations).

## Summary

All three round-2 probes passed live against the running Excel (fresh write control, existing-file overwrite, and the same-path repeat onto the workbook left open by the previous write), each ~0.6 s, all audited `executed` — including `workbook.xlsx`, the default name from the user's original 05:38 failure. The raw `0x800A03EC` no longer appears anywhere; the test battery and lint are green with zero regressions.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction, existing-file overwrite | `xls_write_v2(name="discriminator-fresh-20261114b.xlsx")` onto the existing file (conversation `xls-saveas-test2-verify`) | **pass** | ok — "replaced the existing workbook", existed: true, 0.6 s — the exact class that raw-failed 5+ times before round 2 |
| Reproduction, same-path repeat (the money probe) | immediate second write, same name — the workbook still open from the row above | **pass** | ok — "replaced the existing workbook", existed: true, 0.6 s — the assessment's original failing condition, end-to-end |
| Fresh-name control | `xls_write_v2(name="round2-fresh-control-20261114.xlsx")` | **pass** | ok — created, 0.6 s — happy path intact |
| Historical failure names (round-2 fix phase) | `workbook.xlsx` (default name of the user's first failure; twin-held), `pending-repeat.xlsx` | **pass** | both "replaced the existing workbook" live in the fix phase on the same build |
| Word / PowerPoint repeats (round 1, still shipped) | live probes on open same-path files | **pass** | Word 3.5 s / PPT 2.0 s — "replaced" — unchanged by round 2 |
| New / updated tests | `pytest tests/unit/test_office_v2.py` | **pass** | 19 passed, incl. `test_xls_saveas_silences_the_overwrite_prompt` (DisplayAlerts off before `wb.SaveAs(`, restored after via `finally:`, recovered-twin wrap text) and all round-1 pins |
| Regression suite | `pytest tests/unit` (full) | **pass** | 655 passed, 0 failed |
| Lint / type-check | `ruff check` (changed files) | **pass** | All checks passed |

## Output Excerpts

```
WRITE  (existing file)      → {"status":"ok","note":"replaced the existing workbook at this path","existed":true}  (0.6 s)
REPEAT (same path, open wb) → {"status":"ok","note":"replaced the existing workbook at this path","existed":true}  (0.6 s)
FRESH  (new name)            → {"status":"ok","note":"created a new workbook"}                                     (0.6 s)
audit (07:12:05/09/15)       → three rows, decision: executed, 0.6 s each
pytest tests/unit → 655 passed, 0 failed
```

## Residual Risks

- The recovered-twin wrap (`blocked: saving … failed; the file may be open in Excel under a recovered or temporary name…`) was not exercised live in its failure form — no twin-held target refused after round 2 (workbook.xlsx, the twin-held case, now succeeds through the honest close). The wrap is the named fallback if an unseeable state ever refuses; its text and ordering are pinned.
- `DisplayAlerts = False` is scoped to the SaveAs call and restored (`finally:`) — the user's interactive Excel keeps its normal prompts; verified by inspection (pinned), not by live prompt interaction.
- Excel's ~180 s busy-pump wait when the user holds the app in a modal/edit state remains (server-side; the honest envelope names it and arrives after Excel's own timeout).
- The day's test files in `C:\OfficeMCP` are disposable; delete at will.

## Recommendation

**Close the bug — verified end-to-end, both rounds' mechanisms proven.** The original symptom is eliminated in every form tried (existing-file overwrite, same-path repeat onto an open workbook, twin-held names, fresh controls), the honest-envelope discipline holds across busy-app, pre-close, and save paths, and the full suite is green (655/655). Excel now behaves like Word and PowerPoint: same-path repeats just replace.
