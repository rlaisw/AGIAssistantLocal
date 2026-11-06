# Bug Verification: launch+GUI split — the false MULTI refusal is gone; followup respects desktop-control consent

- **Slug**: `blocked-more-than-one-application-named`
- **Tested**: 2026-11-06T10:05+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original symptom — "open chrome/edge/default browser and type www.google.com" refused as "more than one application named" — no longer reproduces: the gate splits these into one launch verdict plus a carried desktop followup, and both live variants completed the launch successfully with the followup delegated to the agent's WindowsMCP tools. The Chrome case ran fully end-to-end (launch → profile picker → address bar → google.com loaded, screenshot-verified); the Edge case launched correctly and then honestly declined to type because the desktop-control consent timed out while the user was active — the control policy working as designed, reported without fabrication.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction #1 (the bug's exact request) | live `hermes_launch_app("open chrome and type www.google.com")` (fix phase, 09:47) | **pass** | `status ok` — Chrome launched fresh, profile picker handled (Raymond), address bar focused (Ctrl+L), www.google.com typed, **screenshot-verified Google homepage loaded**; full audit trail; 152 s |
| Reproduction #2 (second variant from the report) | live `hermes_launch_app("open edge and type www.google.com")` (this phase, 10:00) | **pass on the bug; honest partial on followup** | `LAUNCH: SUCCESS` — Edge window opened (was already running, activated); the typing followup was **blocked by a desktop-control consent timeout** (user active) and reported honestly, not fabricated. The false MULTI block did not occur |
| Gate unit matrix | `pytest tests/unit/test_hermes_launch_gate.py tests/unit/test_hermes_launch_tool.py` | **pass** | 35 passed — split-not-two-apps, default-browser compound, two-real-apps ask-back, followup-bypass refusals |
| Regression suite | `pytest tests/unit` | **pass** | 337 passed |
| Lint | `ruff check` on the three changed files | **pass** | 0 new findings (5 pre-existing I001s unchanged) |

## Output Excerpts

```
Chrome (fix phase): "…selected the user's 'Raymond' profile… focused the
  address bar (ctrl+l), typed www.google.com, pressed Enter. Verified by
  screenshot: the tab title is 'Google'…" → status ok
Edge (this phase): "Edge was already running; launching it produced a
  Microsoft Edge window… I did not type www.google.com because the
  follow-up activation/typing command was blocked by a consent timeout
  and did not run." → LAUNCH: SUCCESS (honest)
pytest tests/unit → 337 passed
```

## Residual Risks

- The followup typing is subject to WindowsMCP's desktop-control consent: when the user is actively using the machine, typing waits and can time out — correct by design, but users should expect "open X and type Y" to need ~10 s of hands-off time, and may need to re-ask after a consent timeout
- The Edge turn ran long (593 s — the agent wrapped the consent wait); the turn-duration floor remains the known nested-LLM + control-policy cost, not a regression here
- "default browser" resolution is agent-side (asks once if ambiguous, never guesses) — not exercised live this run
- Gate parsing edge cases ("open word and type a letter" may route to the office lane instead — the Dify router decides) — watch natural turns

## Recommendation

**Close the bug — verified.** All three original blocked requests now pass the gate (two proven live), the launch scope rules are provably intact (unit matrix), and the followup's consent-timeout behavior is honest reporting of the desktop-control policy, not a defect. Note the hands-off expectation in everyday use.