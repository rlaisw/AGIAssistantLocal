# Bug Fix: Office X1 overwrite-honesty — deterministic REPLACED: attestation

- **Slug**: office-x1-important-recurring-bug
- **Fixed**: 2026-11-11T07:24:59Z
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The spec-031 "replaced" report for overwrites of pre-existing user-named files is now a deterministic attestation stamped by the `hermes_office_task` tool (the 034 echo-and-attest pattern) instead of a free-form LLM phrase that reliably never matched the battery's spec-031 pin.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/server.py` | modified | module-level `_office_path_exists()` probe helper; `_RE_OFFICE_TARGET` Windows-path regex; pre-existence check in `hermes_office_task` (write-kind tasks naming a `C:\…` target); `REPLACED: the existing file at <path> was overwritten.` appended to the returned result ONLY when the target pre-existed AND the task COMPLETED |
| `tests/unit/test_hermes_office_tool.py` | added 4 tests | the X1 pins (below) |

## Diff Highlights

```python
# pre-existence (before dispatch), office-x1 (spec 031):
_win_path = _RE_OFFICE_TARGET.search(task)
_target_pre_existing = False
if _win_path and verdict.kind == OP_DOCUMENT_WRITE:
    _norm = _normalize(_win_path.group(0), home=..., allowed_root="/mnt")
    _target_pre_existing = bool(_norm) and _office_path_exists(_norm)
# ...in the COMPLETED branch:
if _target_pre_existing:
    result += f"\nREPLACED: the existing file at {_win_path.group(0)} was overwritten."
```

## Tests Added or Updated

- `test_x1_overwrite_of_existing_file_gets_replaced_stamp` — COMPLETED write onto a pre-existing named file → the result carries `REPLACED: the existing file at <path>` (the battery pin's report leg, now deterministic)
- `test_x1_fresh_create_gets_no_replaced_stamp` — create path → no stamp (honest both ways)
- `test_x1_failed_write_on_existing_file_gets_no_stamp` — FAILED write onto pre-existing file → error envelope, no fabricated replaced-claim
- `test_x1_read_task_never_stamps` — reads naming existing files → no stamp (writes only)

## Local Verification

- Commands run: `pytest tests/unit/test_hermes_office_tool.py` → **22 passed** (18 existing + 4 new)
- Commands run: `pytest tests/unit/` → **550 passed** (full unit suite green)
- Manual checks: diff is surgical (+40/-1 in server.py, X1 change only — an auto-fix excursion that touched unrelated import blocks was reverted and reapplied by hand); the live overwrite file from the batteries still verifies `v2` (the write leg was never broken).

## Deviations from Assessment

None — the preferred remediation (deterministic stamp, stamped only on pre-existing + success) is exactly what landed. One implementation detail: the pre-existence probe is behind the module-level `_office_path_exists()` indirection so the pins are hermetic (the real check hits `/mnt/<drive>`, host-only) — within the spirit of the assessment's "no schema change, additive" risk notes.

## Follow-ups

- The X1 verdict flips green at the next `deploy all` battery (needs the sidecar rebuild — the running container predates this fix).
- Spec 031's honesty contract now has a code-enforced attestation, not a prompt hope — consider the same echo-and-attest pattern for any future report-wording requirements.
- The X1 flake's "3-for-3" record in the residual list can be closed once the next battery confirms.
