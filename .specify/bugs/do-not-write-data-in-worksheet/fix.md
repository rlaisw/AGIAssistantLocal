# Bug Fix: VISIBLE-STATE REQUIREMENT — tasks end with the document open and active; audit slice 200 → 1000

- **Slug**: `do-not-write-data-in-worksheet`
- **Fixed**: 2026-11-06T05:25+00:00
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The STEP BATCHING rule gained a mandatory VISIBLE-STATE REQUIREMENT: the combined script must end with the task's document **open and active** in the application window (re-open from disk is the preferred final form — it also proves what persisted), display claims must match the verified window state, closed documents must be reported as such, and documents the task didn't open must never be closed. The audit trail's STEP outcome slice was raised from 200 to 1000 characters so batched step texts survive whole.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | STEP BATCHING rule extended with the VISIBLE-STATE REQUIREMENT (end state: document OPEN and ACTIVE; verify the window state before claiming "shows the result"; empty-window endings forbidden with the why: "an empty app window makes the user believe the write never happened"; never close others' documents; close+re-open-from-disk offered as the preferred final sub-step) |
| `src/agentic_rag_mcp/server.py` | modified | Audit STEP outcome/reason slice `[:200]` → `[:1000]` (batched texts were cut mid-sentence; why-comment included) |
| `tests/unit/test_hermes_office_tool.py` | modified | Guard: the visible-state rule's key phrases pinned |
| Live sidecar | redeployed | ok: 4 steps, 26 tools |

## Diff Highlights (optional)

```python
"VISIBLE-STATE REQUIREMENT (mandatory): the script must END with the
task's document OPEN and ACTIVE in the application window — after SaveAs
keep the workbook open (or close it and re-open the saved file from
disk, which also shows exactly what persisted); never finish with the
app visible but no document loaded. Before claiming the app 'shows the
result', VERIFY the window state …"
```

## Tests Added or Updated

- `tests/unit/test_hermes_office_tool.py::test_office_instructions_contain_attach_failure_protocol` — visible-state phrases pinned (332 unit tests pass)

## Local Verification

- `pytest tests/unit` → **332 passed**; `ruff` on changed files — no new findings (the 5 fixables on `server.py` are pre-existing, verified against the stashed baseline); `deploy redeploy` → ok
- **Live end-to-end (05:21:27)**: Excel task "create visible-state-verify.xlsx with 555777 in A1" through a **stripped gateway channel** (3 canaries → direct channel again): the agent batched the steps AND followed the new rule — "STEP 5: Verify OK — **closed and re-opened the saved file from disk**; A1 read back as 555777". Post-task COM probe of the live Excel: **`ACTIVE_WB=visible-state-verify.xlsx … A1=555777`** — the window now shows the task's document with its data (the exact failure from the bug report cannot recur silently). Audit entries for the turn are complete (274-char steps, no truncation).

## Deviations from Assessment

- None. The preferred remediation was applied exactly, including the assessment's re-open-from-disk alternative folded in as the preferred final sub-step.

## Follow-ups

- The user's earlier file `excel-2026-11-06.xlsx` was always correct on disk (A1=98765) — opening it in Excel now shows the data; the empty Excel shell from that turn can be closed
- Watch natural turns for visible-state adherence (instruction-level rule, model-adherence probabilistic — same class as the batching rule; the strong form is the re-open-from-disk ending the agent already chose voluntarily)
- The 5 pre-existing ruff fixables on `server.py` are worth a separate lint-hygiene pass (out of scope here)
