# Bug Fix: the transport-cut relay now explains the ~300 s window and hands the user the split-request remedy

- **Slug**: `the-launch-request-failed-while-communicating-with-the-local-agent-on-your-pc`
- **Fixed**: 2026-11-09T04:05+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — live-graph verified

## Summary

The chatflow's transport-error rule (the `hermes_agent` node prompt) now instructs the agent: when relaying a transport cut on a **desktop** task, also tell the user *why* it recurs (the chat's tool window is roughly 300 seconds; multi-step desktop tasks that exceed it always cut) and *how to avoid it* (split — first "open \<app\>", then the typing/search followup as a separate message, each step still fitting the window). Applied export→patch→publish via the console API; live-graph check true (04:03:14).

## Changes

| File / surface | Change | Notes |
|------|--------|-------|
| Live Dify workflow (`hermes_agent` node prompt) | modified | The transport-error bullet gains the desktop-cut guidance (why + split remedy) — appended after "One tool attempt per turn; re-asking is the user's choice, not yours", so the honest-relay contract is unchanged and the new sentence only adds the actionable hint for the desktop-cut case |
| `dify/AGIAssistant/AGI_Assistant.yml` | synced | re-exported post-publish so the repo artifact matches live |

## Diff Highlights (optional)

```text
… When the failure is a transport cut on a DESKTOP task, also tell the
user WHY it recurs and HOW to avoid it: the chat's tool window is roughly
300 seconds, and multi-step desktop tasks that exceed it will always cut;
suggest splitting — first 'open <app>', then the typing/search followup as
a separate message — each split step must still fit within the window.
```

## Tests Added or Updated

- No code surface touched (prompt-only); live-graph assertion is the check (`LIKE '%will always cut; suggest splitting%'` → **true**); full suite stays green

## Local Verification

- Publish executed via the console API; live-graph check **true** on the version created 04:03:14
- `pytest tests/unit` → **359 passed** (no code changed; confirmation)

## Deviations from Assessment

- None — the preferred remediation applied exactly (one prompt-bullet amendment, console publish, no code).

## Follow-ups

- Behavioral sample: the next >300 s desktop turn's relay should now include the split suggestion; a natural occurrence completes the verification (the mechanism is prompt-level, same as every prior honest-relay rule the agent demonstrably follows — e.g., the no-retry rule in the very transcript that prompted this bug)
- The ceiling itself remains upstream (Dify plugin-daemon); its evidence file is ready to post from an account with write access to that repo
- Chrome may be open from the failed 03:53 turn (the gateway agent kept working past the cut) — close at will
