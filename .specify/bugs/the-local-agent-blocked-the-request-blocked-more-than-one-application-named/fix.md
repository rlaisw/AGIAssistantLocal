# Bug Fix: `check`/`read`/`tell me` join the observe-verb set — the "open X , check Y" phrasing executes

- **Slug**: `the-local-agent-blocked-the-request-blocked-more-than-one-application-named`
- **Fixed**: 2026-11-09T02:25+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — gate fix verified (unit matrix + live); the verification turn then hit the *documented, separate* ~300 s Dify-daemon ceiling (see Verification)

## Summary

The gate's observe-verb alternation gained `check`, `read`, and `tell me` (comma/and/then form only — no bare-space, protecting any app literally named "check"), so "help to open chrome browser , check hong kong temperature today" splits into the launch (`chrome`) plus a carried desktop followup instead of MULTI-blocking.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_launch_gate.py` | modified | `_RE_GUI_CLAUSE` verb set: + `check`, `read`, `tell me` |
| `tests/unit/test_hermes_launch_gate.py` | +3 tests | the exact report phrasing (target `chrome`, followup `check hong kong temperature today`), read/tell-me splits, and the honest fallbacks (unknown pair still MULTI, bare `open search` still ask-back) |
| Live sidecar | redeployed | ok: 4 steps |

## Diff Highlights (optional)

```python
# ...|search|find|look up|google|show|display|view|check|read|tell me)\b.*$"
```

## Tests Added or Updated

- 3 new gate tests; gate suite 55 passed; full suite **357 passed**; `ruff` clean

## Local Verification

- Gate matrix (9 cases): the exact report phrasing → `ok, target=chrome, followup='check hong kong temperature today'`; and/comma forms of check/read/tell-me all split; every prior class case and fallback intact
- **Live (02:12–02:17)**: the exact request through the chat — **no MULTI block**: the agent passed the full task to `hermes_launch_app` (its reasoning quotes the pass-unchanged rule), the tool **executed for the full turn**, and at **307 s wall** the turn ended with the honest transport-error relay — the *documented ~300 s Dify plugin-daemon ceiling* (`the-local-agent-hit-a-transport-error`, closed as a known limit), not a parsing failure. The gate fix's live proof is the transition: 02:06:30 the identical request was `blocked`; 02:12 it executed.

## Deviations from Assessment

- None — the preferred remediation applied exactly (check + read + tell me, comma/and/then form only).

## Follow-ups

- The verification turn's ceiling hit reconfirms the known-limit operating posture: heavy Chrome navigation should be split ("open chrome", then "check hong kong temperature") or kept under ~300 s; the honest relay makes the failure self-explanatory
- The verb family is now: type/click/press/enter/scroll (input), search/find/look up/google (query), show/display/view/check/read/tell me (observe) — natural additions to the same alternation remain one word + one test each
- `/speckit.bug.test` can close this on the gate evidence; a sub-300 s live completion of a check-followup will arrive naturally (a light check task, e.g. "open task manager , check the cpu usage")
