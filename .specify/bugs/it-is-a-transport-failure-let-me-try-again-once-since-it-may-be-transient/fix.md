# Bug Fix: No-retry-on-transport-error in the chat agent — one tool attempt per turn, honest relays instead of silent cumulative kills

- **Slug**: `it-is-a-transport-failure-let-me-try-again-once-since-it-may-be-transient`
- **Fixed**: 2026-11-08T09:20+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — live graph verified

## Summary

The chatflow's `hermes_agent` node prompt now forbids retrying a `hermes_*` tool call after a transport error within the same turn: a retry stacks a second long call onto the turn's tool-time window and the platform kills the whole run silently (the 09:00:31 turn died at 603.3 s mid-retry with no verdict and no audit). The agent must relay the failure honestly — the tools' error text already carries the recovery hint — and leave re-asking to the user.

## Changes

| File / surface | Change | Notes |
|------|--------|-------|
| Live Dify workflow (`hermes_agent` node prompt) | modified | New bullet after the never-reattempt-blocked rule: transport errors (peer closed / incomplete chunked read / connection dropped / timeout) → **do NOT retry the same tool within this turn**; relay the error (its text carries the recovery hint); "One tool attempt per turn; re-asking is the user's choice, not yours." Applied export→patch→publish via the console API; repo artifact re-synced from the published graph |
| `dify/AGIAssistant/AGI_Assistant.yml` | synced | matches the live workflow (the local file is regenerated from the export, avoiding the clobber trap) |
| No sidecar code changes | — | The 540 s envelope is correct as-is; this fix closes the *cumulative* window escape, not the per-call budget |

## Diff Highlights (optional)

```text
- Transport errors: if a hermes_* tool call fails with a transport error
(peer closed connection / incomplete chunked read / connection dropped /
timeout), do NOT retry the same tool within this turn — a retry stacks a
second long call onto the turn's tool-time window and the platform kills
the whole run silently with no verdict at all. Relay the failure to the
user honestly (the tool's error text already carries the recovery hint)
and let the user re-ask. One tool attempt per turn; re-asking is the
user's choice, not yours.
```

## Tests Added or Updated

- No repo-code test surface (prompt-only change); the live-graph assertion below is the verification, per the assessment's plan
- Full suite **354 passed** (no sidecar code touched)

## Local Verification

- Publish executed via the console API; **live workflow graph check**: `graph::text LIKE '%do NOT retry the same tool%'` → **true** on the version created 09:17:18
- `pytest tests/unit` → 354 passed (nothing broken)
- Behavioral verification is inherently user-side: the next chat turn that hits a transport error must return an honest relayed verdict instead of a killed run — observable in future natural turns (see Follow-ups)

## Deviations from Assessment

- None — the preferred remediation was applied exactly as specified.

## Follow-ups

- Watch natural turns: any transport-error turn should now surface the tool's honest error text in the chat — the first such relay makes the previously-invisible first-attempt error observable (the 09:00 turn's blip was lost entirely); if the same blip recurs, its text becomes diagnosable
- If the underlying transport blip proves persistent (not transient), it graduates to its own lifecycle with the now-visible error text as evidence
- The no-retry rule deliberately covers all `hermes_*` tools (launch/office/file) — one bullet, whole lane
