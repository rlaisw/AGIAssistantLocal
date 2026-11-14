# Bug Fix: COM apartment guard in every office v2 template (CoInitialize before Dispatch)

- **Slug**: slow-respone-come-back-again-first-attempt-fast-v2-document-path-failed
- **Fixed**: 2026-11-14T05:16:00+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — unit-pinned, sidecar rebuilt, live probe ok

## Summary

All four office v2 RunPython templates (Word write/read, Excel write, PowerPoint write) now call a guarded `pythoncom.CoInitialize()` before `win32com.client.Dispatch(...)`, so a script handed to a COM-uninitialized OfficeMCP worker thread (error `-2147221008`, the cause of the instant "First attempt (fast v2 document path): failed") initializes its own apartment instead of dying in 0.1 s and falling back to the 70 s v1 lane.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/office_lanes/proxy.py` | modified | guarded `pythoncom.CoInitialize()` inserted between `import win32com.client` and each `Dispatch(...)` in `_WRITE_TEMPLATE`, `_READ_TEMPLATE`, `_XLS_WRITE_TEMPLATE`, `_PPT_WRITE_TEMPLATE`; failures of the init call are swallowed (a healthy apartment is unaffected, a genuinely broken COM environment still surfaces its real error) |
| `tests/unit/test_office_v2.py` | added test | `test_templates_init_com_apartment_before_dispatch` — pins `CoInitialize()` presence AND ordering before `Dispatch(` for all four templates |

## Diff Highlights (optional)

```python
import win32com.client
# COM apartment guard (2026-11-14): some RunPython workers execute scripts
# on a COM-uninitialized thread (-2147221008); failures here must not block
# a healthy apartment, a broken one still surfaces its real error
import pythoncom
try:
    pythoncom.CoInitialize()
except Exception:
    pass
word = win32com.client.Dispatch('Word.Application')
```

## Tests Added or Updated

- `tests/unit/test_office_v2.py::TestXlsPptV2::test_templates_init_com_apartment_before_dispatch` — every v2 template calls `pythoncom.CoInitialize()` and the call is ordered before `win32com.client.Dispatch(` (the same string-level pin discipline as the `.Text`-verify pin).

## Local Verification

- Commands run: `pytest tests/unit/test_office_v2.py` → **16 passed**; full `pytest tests/unit` → **638 passed, 2 failed** — both failures (`test_browser_control_v2.py::TestType::test_type_not_found_asks_back`, `TestSensitiveExclusion::test_secret_absent_from_all_surfaces`) verified **pre-existing on the unmodified tree** (git-stash check reproduced them on the clean checkout); unrelated to this fix. `ruff check` → clean (after `--fix` sorted the new import block).
- Sidecar: `python -m agentic_rag_mcp.deploy redeploy` → image built, container recreated, health ok, tools synced 53/53.
- Live probe (healthy window): `doc_write_v2("com init probe post-fix…")` on the rebuilt sidecar → **ok, created, text_ok true**.
- Honest limit: the failing window (a COM-uninitialized worker thread) is service-side and intermittent — it cannot be forced on demand. The structural guarantee is the pinned ordering: with `CoInitialize()` first, the `-2147221008` failure is no longer reachable from these templates; the audit trail will confirm over time (no new `-2147221008` rows on `doc-write-v2`/`xls-write-v2`).

## Deviations from Assessment

None — the preferred remediation applied exactly (4 templates + unit pin + rebuild + probe). No DSL or model changes; tool count unchanged (53).

## Follow-ups

- Watch the next few days of `audit.jsonl` for any recurrence of `-2147221008` on v2 office rows (structurally it should be gone; any recurrence would mean a COM failure mode past apartment init).
- The two pre-existing browser-control v2 unit failures (`test_type_not_found_asks_back`, `test_secret_absent_from_all_surfaces`) predate this fix and fail on the clean tree — worth their own lifecycle.
- Upstream note (optional): the OfficeMCP service owner may want to CoInitialize all RunPython worker threads so lane scripts need not self-initialize.
