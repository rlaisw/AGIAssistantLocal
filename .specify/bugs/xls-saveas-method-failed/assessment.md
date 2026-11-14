# Bug Assessment: xls_write_v2 SaveAs fails on same-path repeats — the same-path pre-close does not achieve its goal

- **Slug**: xls-saveas-method-failed
- **Created**: 2026-11-14T06:15:00+00:00
- **Source**: live user tests (the four-case benchmark: Word ✓ / Excel ✗ ×2 / PPT ✓ / Chrome ✓) + the audit trail
- **Verdict**: valid — the failure class reproduced live during assessment (error + control probe pair)
- **Severity**: medium — the Excel v2 lane fails on any save whose target file is already open in Excel (repeats, re-tests, benchmark loops — exactly how the owner works), each failure leaks an unsaved workbook into Excel, and the honest fallback costs ~57 s; fresh-name writes are unaffected

## Report (verbatim or summarized)

Two live user failures today with identical COM errors, plus the assessment's own reproduction:

```
xls_write_v2 → error:office-v2 malformed result —
{"success":false,"error":"(-2147352567, 'Exception occurred.',
 (0, 'Microsoft Excel', 'SaveAs method of Workbook class failed',
  'xlmain11.chm', 0, -2146827284), None)"}
```

- 2026-11-14 05:38:12 UTC (13:38 HK) — first Excel test (conv `9402426f`); fell back to the v1 office-task lane which completed the same work in **56.9 s** (saved `NameAgeTable.xlsx`, attached to the running Excel via GetActiveObject).
- 2026-11-14 06:00:48 UTC (14:00 HK) — the benchmark retry; same error (4.2 s), no fallback row.

## Symptom

`xls_write_v2` succeeds on fresh filenames but fails with Excel COM error `0x800A03EC` ("SaveAs method of Workbook class failed") when the target file is already open in the running Excel instance — and the template's "lock-free repeats" pre-close loop, which exists precisely to close a same-path workbook first, demonstrably does not close it (verified live: the file stays locked after a failed attempt).

## Reproduction

1. **Live reproduction (performed during assessment, 06:07–06:08 UTC, conversation `xls-saveas-bug-probe`)**: `xls_write_v2(name="workbook.xlsx")` — a file left open in Excel by an earlier probe — → **the exact user error** (`0x800A03EC`, SaveAs failed, audit row written).
2. **Control probe, same instance, same moment**: `xls_write_v2(name="fresh-probe-20261114.xlsx")` → **ok**, created, verified, fronted — isolating the failure to the same-path condition, not the Excel instance, the service, or the template's happy path.
3. **Post-failure state (verified)**: `workbook.xlsx` still **LOCKED** in Excel after the failed attempt — the pre-close loop did not close it. Note the failed probe took **59.2 s** (vs 4.2–4.4 s for the user's failures and 0.7 s for the control) — COM-call timing under a busy/foreground Excel varies widely; the terminal error is identical.
4. **Current folder state**: every `.xlsx` in `C:\OfficeMCP` (workbook, test1, test2, test9, NameAgeTable, com-init-probe.xls, fresh-probe) is **open+locked in the one running EXCEL.EXE** — the successful v2 writes leave their workbooks open by design, so the folder's own outputs become the next write's lock hazards.
5. **Side effect observed**: each failed attempt leaves an additional **unsaved workbook** (Workbooks.Add debris) open in Excel — the failed run creates it, the error aborts the script, nothing closes it.

## Suspected Code Paths

- `src/agentic_rag_mcp/office_lanes/proxy.py` `_XLS_WRITE_TEMPLATE` (the same-path pre-close block, ~lines 109–115 + the guard added 2026-11-14): `for wb in list(xl.Workbooks): try: if normcase(wb.FullName) == normcase(path): wb.Close(False) except Exception: pass` — the bare `except: pass` swallows any Close failure, and nothing verifies the workbook is actually gone before `wb.SaveAs(path)` runs; Excel refuses SaveAs onto a path whose file is open in the instance → `0x800A03EC`.
- Same template, `win32com.client.Dispatch('Excel.Application')` — **Dispatch may start a new Excel instance instead of attaching to the running one** (ROT miss from the service context); in that case the pre-close loop iterates the wrong instance's (empty) Workbooks collection and SaveAs hits a file locked by the other instance. The v1 lane's proven pattern (`hermes_office_task`, the 05:39 fallback) explicitly uses **GetActiveObject to attach to the running instance** — and succeeded where v2 failed. Disambiguating missed-attach vs swallowed-Close is the fix phase's first instrumentation task.
- `src/agentic_rag_mcp/server.py` `xls_write_v2` wrapper (`_xls_name` sanitizer verified clean: basename-only, `.xlsx` enforced — the name is NOT the problem).
- Word's `_WRITE_TEMPLATE` shares the same pre-close pattern — same latent hazard for doc repeats (not reproduced today; fix both together).

## Root Cause Hypothesis

**High confidence on the failure class, two candidate mechanisms to disambiguate by instrumentation.** The failure is proven: SaveAs onto an already-open workbook fails with `0x800A03EC`, and the pre-close loop does not get the workbook closed (live-verified still-locked afterward). Whether that is (a) a swallowed `Close(False)` failure (e.g. Excel busy in cell-edit mode — the owner works in the fronted Excel during tests) or (b) a Dispatch-vs-GetActiveObject attach miss making the loop iterate a fresh instance that holds nothing, the observed behavior is identical; the v1 lane's GetActiveObject success at 05:39 leans toward (b) as at least one real contributor. The user's two failures are the same error class; the exact target name of the 05:38 attempt is not logged (sidecar logs no tool args), so which trigger fired per-turn is [NEEDS CLARIFICATION] — but both candidate triggers are closed by the same remediation.

## Proposed Remediation

**Preferred** (template hardening, mirrors the v1 lane's proven attach + makes the pre-close honest):
1. Attach like the v1 lane: `win32com.GetActiveObject('Excel.Application')` first (attach to the running instance), fall back to `Dispatch` only if none is running.
2. Make the pre-close loop honest: no bare `except: pass` — attempt `Close(False)`, collect failures, then **re-check whether any workbook still sits at the target path**; if it does, retry the close once, and if it still holds, return a structured honest error BEFORE attempting SaveAs — naming the situation and the recovery ("the target file is open in Excel and could not be closed automatically; close it in Excel or choose a different name") instead of surfacing the raw COM tuple.
3. Same hardening for the Word template's identical pre-close block (same pattern, same hazard class).

**Alternatives**:
- Save to a temp name then `os.replace` — rejected: it would silently diverge from the open workbook (the user's screen would show the OLD content) — the honest error + fallback is correct.
- Keep swallowing and rely on the v1 fallback — rejected: 57 s per repeat and unsaved-workbook debris accumulation in Excel.

**Files likely to change**:
- `src/agentic_rag_mcp/office_lanes/proxy.py` (`_XLS_WRITE_TEMPLATE`, `_WRITE_TEMPLATE`)
- `tests/unit/test_office_v2.py` (string-level pins per house style)

**Tests to add or update**:
- Pin: both templates contain `GetActiveObject` before `Dispatch` fallback.
- Pin: no bare `except Exception: pass` around the pre-close (the loop must record outcomes).
- Pin: both templates contain the still-open re-check + the honest refusal text before `SaveAs`.
- Live (fix phase): repeat-write to a workbook left open by a prior successful write → either succeeds (close worked) or refuses honestly — never the raw `0x800A03EC` envelope; fresh-name write still ok.

## Risks & Considerations

- `GetActiveObject` throws when Excel is not running — the fallback to Dispatch must be preserved (the "attach if present, else start" shape).
- The honest-refusal path changes the error envelope the agent sees: the DSL's office-task fallback rule already covers it (the 05:38 turn proved the fallback works), so the failure degrades to the slow lane with a clear reason instead of an opaque COM tuple.
- Closing the user's open workbook discards their unsaved changes (`Close(False)` is the existing, intended semantics — documented in the template as lock-free repeats; unchanged by this fix, but the re-check makes the discard explicit when it happens rather than silent).
- Excel left with leaked unsaved workbooks from today's failures (up to 4): close at will; the fix prevents future leaks.
- Sidecar rebuild required; no tool-count or DSL change.

## Open Questions

- [NEEDS CLARIFICATION: the exact target name of the 05:38 user failure (args are not audited) — same-path lock and busy-Excel are both consistent with the observed error; the fix-phase instrumentation (instance PID + open workbook names + close outcomes in the template's error path) will disambiguate. Not blocking: both candidate triggers are closed by the same remediation.]
