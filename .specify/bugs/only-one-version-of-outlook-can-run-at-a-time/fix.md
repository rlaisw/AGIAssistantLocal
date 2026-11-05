# Bug Fix: "Only one version of Outlook" — attach-failure protocol closes the mitigation gap

- **Slug**: `only-one-version-of-outlook-can-run-at-a-time`
- **Fixed**: 2026-11-05T06:15+00:00 (overwrites the 2026-11-04 fix report — that mitigation held in form but not in function; git history preserves it)
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The office lane's instructions now include the missing third leg of the Outlook handling: the **OUTLOOK ATTACH-FAILURE PROTOCOL** — when the outlook.exe process is running but its COM server is unreachable (0x800401E3/0x80080005), the agent never calls Launch again (dialog risk), stops, and asks the user to choose between closing Outlook themselves or authorizing exactly one consent-gated `taskkill /IM outlook.exe /F` + relaunch. The sidecar was rebuilt and redeployed so the live lane runs the new instructions.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | `OFFICE_INSTRUCTIONS` gained the OUTLOOK ATTACH-FAILURE PROTOCOL between the RunningApps-corruption fallback and the report-honesty rule |
| `tests/unit/test_hermes_office_tool.py` | added test | `test_office_instructions_contain_attach_failure_protocol` pins the protocol text (both COM error codes, the never-re-Launch rule, the two consent options, the taskkill form, the never-killed-silently guard) and the pre-existing legs (Dispatch/GetComObject fallback, SESSION-DEGRADATION RULE) |
| `.specify/bugs/only-one-version-of-outlook-can-run-at-a-time/upstream-comment-draft.md` | added | Upstream #148459 recurrence+intermittency evidence, drafted for posting — the current fine-grained PAT lacks write access to NousResearch/hermes-agent |
| Live sidecar | redeployed | `deploy redeploy` → build image, recreate container, health-wait ok, sync-tools 26/26 — instructions are baked into the sidecar and delivered per gateway call, so no chatflow republish was needed |

## Diff Highlights (optional)

```python
"OUTLOOK ATTACH-FAILURE PROTOCOL (mandatory): before touching Outlook, "
"probe the outlook.exe process via RunPython; if the process is running "
"but every attach attempt fails with COM errors (0x800401E3 'Operation "
"unavailable' or 0x80080005 'Server execution failed'), Outlook is "
"running but its COM server is unreachable — NEVER call Launch again "
"(it can only produce the 'only one version of Outlook' dialog). Stop "
"and ASK BACK with exactly two options: the user closes Outlook "
"themselves and asks to retry, or the user says 'restart Outlook' to "
"authorize ONE consent-gated close-and-relaunch (taskkill /IM "
"outlook.exe /F via RunPython, wait for the process to exit, then "
"Launch Outlook and verify the COM attach works); execute the restart "
"only after that explicit confirmation — the user's Outlook may hold an "
"unsaved draft, so it must never be killed silently — and report every "
"step of the restart honestly."
```

## Tests Added or Updated

- `tests/unit/test_hermes_office_tool.py::test_office_instructions_contain_attach_failure_protocol` — the protocol text cannot silently disappear; the Nov-4 legs stay guarded too

## Local Verification

- `pytest tests/unit/test_hermes_office_tool.py tests/unit/test_office_gate.py` → **49 passed** (the full office suites; the new test included)
- `deploy redeploy` → `ok: 4 steps` (build, recreate, health-wait, sync-tools 26/26)
- Full unit regression: **331 passed** (see test run in the sibling-bug verification, same tree state)
- Live end-to-end exercise: **not run** — the Outlook COM-unreachable state on the user's desktop is a precondition; the protocol will fire on the user's next email task (see Follow-ups)

## Deviations from Assessment

- The assessment proposed checking `office_gate.py` for the restart-consent path: verified **no gate change is needed** — the gate has no kill/restart patterns and "restart Outlook" flows as a normal office task; the consent gate lives in the instruction protocol itself (the audit trail records every executed step either way).
- The upstream #148459 comment could not be posted: the repository's GitHub PAT is fine-grained without write access to NousResearch/hermes-agent. The drafted comment is saved in this bug directory for the owner to post (or re-post with a suitable token) — the file is `upstream-comment-draft.md`.

## Follow-ups

- On the user's **next email task**, the broken Outlook state will now produce the ask-back instead of a Launch/dialog loop; verify in `/speckit.bug.test` that the turn ends with the two-option ask and an audit entry naming the COM errors, and that a "restart Outlook" consent runs the taskkill→relaunch sequence honestly
- User-side immediate unblock remains available: close the Outlook window once and reopen it (clears the COM-unreachable state)
- Post `upstream-comment-draft.md` to hermes-agent #148459 with a write-capable token — the evidence (intermittent arg-drop, recovery no longer clears it, args-free tools unaffected) narrows the defect to client-side argument serialization
- Rotate the GitHub PAT if it was scoped down intentionally (it previously could comment on that repo)
