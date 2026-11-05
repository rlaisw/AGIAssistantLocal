# Bug Fix: "Failed to invoke tool" — wait-based strip-window guidance; stop re-arming it

- **Slug**: `the-tool-call-failed`
- **Fixed**: 2026-11-05T07:22+00:00
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The harmful reset recommendation is gone from every surface: the lane's SESSION-DEGRADATION RULE now teaches the evidence-backed model — the argument strip is a **~10–15-minute time window after any gateway restart or MCP re-registration**, self-healing, and every reset **re-arms** it — so the guidance is WAIT, never restart. `reboot.sh` no longer restarts a healthy gateway or re-registers an existing OfficeMCP connection (each re-armed the window on every run), DEPLOY.md's runbook row carries the corrected model, and a new OUTLOOK LAUNCH GUARD probes the outlook.exe process before any Launch. Live-verified post-fix: **0 stripped calls / 5 delivered**, no Launch on the broken Outlook, and the attach-failure protocol ended with the consent ask-back as designed.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | SESSION-DEGRADATION RULE rewritten: time-window model, 3-canary cap, wait-based recovery text, explicit "do NOT restart/re-register" guidance, no reset commands; new OUTLOOK LAUNCH GUARD (process-probe before any Outlook Launch) |
| `tests/unit/test_hermes_office_tool.py` | modified | Guard test pins: time-window wording, 3-canary cap, "WAIT about 15 minutes", "re-arms", **absence** of the `hermes mcp remove` reset hint, and the launch guard |
| `DEPLOY.md` | modified | Known-defect row rewritten: time-window model with args-capture evidence; recovery = WAIT ~15 min, never reset; diagnosis probes kept |
| `reboot.sh` | modified | Gateway step: skip restart when already healthy (with the why in output); MCP step: skip re-registration when OfficeMCP is registered; warn about the strip window whenever a fresh start/registration happens |
| `.specify/bugs/officemcp-connection-error/fix.md` | annotated | Supersession note: the earlier "~5-call cold window" model (same day) is replaced by the time-window model |
| Live sidecar | redeployed | `deploy redeploy` → ok: 4 steps, 26 tools synced |

## Diff Highlights (optional)

```python
# hermes_client.py — the rule that used to recommend the reset now forbids it
"...restarting the gateway, re-registering OfficeMCP, or restarting
OfficeMCP RE-ARMS it — so never recommend or perform a reset. If a
RunPython call returns only the default echo, try up to 3 tiny canaries
... If all 3 echo the default, STOP and end with 'TASK: FAILED — OfficeMCP
argument strip window ... recovery: WAIT about 15 minutes and ask again —
do NOT restart the gateway, re-register OfficeMCP, or restart OfficeMCP'"
```

## Tests Added or Updated

- `tests/unit/test_hermes_office_tool.py::test_office_instructions_contain_attach_failure_protocol` — extended to pin the time-window rule, the wait guidance, the absence of the reset hint, and the launch guard

## Local Verification

- `pytest tests/unit/test_hermes_office_tool.py tests/unit/test_office_gate.py` → **49 passed**
- `ruff check src/agentic_rag_mcp/hermes_client.py` → clean; `bash -n reboot.sh` → clean (ruff "errors" on reboot.sh are it parsing shell as Python — bogus)
- `deploy redeploy` → ok: 4 steps
- **Live (07:14–07:20 UTC)**: with the 07:01 gateway restart now ~15 min old, the user's exact email task ran: canary → process probe → attach attempts all **delivered arguments (0 stripped / 5 delivered)**; the launch guard held (no Launch despite the broken Outlook); the turn ended in the attach-failure protocol's consent ask-back. The owner declined the Outlook restart for now — the ask-back and the owner's choice are the designed flow.

## Deviations from Assessment

- None on substance. One scope addition, logged per the workflow: `reboot.sh` was changed (the assessment listed it only under Risks) because its unconditional gateway restart re-arms the window on **every** run — the skip-when-healthy change is the smallest way to stop the runbook itself from re-triggering the defect it warns about.
- The full email-compose e2e could not complete: Outlook's COM server remains unattachable and the owner chose to leave it alone. The channel, guard, and protocol layers of this fix are verified; the compose depends on the owner's Outlook decision (see `only-one-version-of-outlook` lifecycle).

## Follow-ups

- When the owner next consents (chat reply "2", or closing Outlook themselves), the compose should complete end-to-end; verify in `/speckit.bug.test`
- Update the hermes-agent #148459 upstream comment with the time-window model (drafts exist in two bug dirs; the token still needs write access)
- Consider deploy-time stream draining so a `redeploy` cannot sever in-flight chat requests (separate, lower-severity ops issue)
- The OfficeMCP args-capture patch stays in place until the upstream fix lands; remove it then
