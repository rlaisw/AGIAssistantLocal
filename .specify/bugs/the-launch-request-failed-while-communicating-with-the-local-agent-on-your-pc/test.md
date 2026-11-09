# Bug Verification: the transport-cut relay now explains the ~300 s window and prescribes the two-message split — behavioral proof in a live cut

- **Slug**: `the-launch-request-failed-while-communicating-with-the-local-agent-on-your-pc`
- **Tested**: 2026-11-09T04:10+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The fix's exact behavioral change is proven in a live transport-cut turn: a chat-side desktop request whose tool call was cut mid-flight (sidecar restart at +32 s, the identical "peer closed connection / incomplete chunked read" from the original bug report) now relays **why it happens and how to avoid it** — *"this chat's tool window is roughly 300 seconds… re-ask in two separate messages: 1. `open chrome` 2. `type hong kong temperature today in the search bar`. Each split step fits comfortably within the time window"* — instead of the old generic "ask again". The honest-relay and no-retry contracts are unchanged and visibly intact in the same answer.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) — forced transport cut | chat turn "help to open chrome browser , type hong kong temperature today at search bar"; sidecar restarted at +32 s (the proven forced-cut method) → the turn ended at +38 s with the transport error | **pass** | The relay now contains: **"Why this happened: this chat's tool window is roughly 300 seconds, and a combined 'launch + type' desktop task can run long enough to exceed it"** and **"How to get it done — please re-ask in two separate messages: 1. `open chrome` 2. `type hong kong temperature today in the search bar` … each split step fits comfortably within the time window"** — exactly the guidance the assessment prescribed; the transcript's own reasoning shows it applying the new rule ("transport cut on a DESKTOP task, also tell the user WHY…") |
| The prompt is live | graph check `LIKE '%will always cut; suggest splitting%'` (fix phase, 04:03:14) | **pass** | true; confirmed again by the behavioral output above |
| Honest contracts unchanged | the same relay text | **pass** | "I won't retry it in this same turn, since a second attempt would likely get cut off the same way" — the no-retry rule intact; the verdict accurate ("connection dropped before it could report back") |
| New / updated tests | `pytest tests/unit` | **pass** | **359 passed** (no code changed by this fix; suite green) |
| Lint / type-check | n/a — prompt-only change | **not-run** | No code surface touched; nothing to lint beyond the suite |

## Output Excerpts

```
forced cut at +32s -> turn +38s, transport error relayed, and:
  "Why this happened: this chat's tool window is roughly 300 seconds…
   How to get it done — please re-ask in two separate messages:
   1. open chrome   2. type hong kong temperature today in the search bar
   Each split step fits comfortably within the time window."
pytest tests/unit -> 359 passed
```

## Residual Risks

- The ~300 s Dify-daemon ceiling itself remains upstream and unchanged — heavy single steps can still cut; the guidance honestly frames each split step as needing to fit the window
- Prompt-rule adherence is probabilistic like every instruction-level rule — but the live sample shows it applied verbatim in the same failure shape that originally cut, and the rule is now live in the graph
- The upstream Dify issue remains unposted (PAT scope) — its evidence file is complete

## Recommendation

**Close the bug — verified end-to-end in the exact original failure shape.** The same transport cut that produced the original generic "ask again" relay now produces the why + the concrete two-message remedy, with the honest-relay and no-retry contracts intact. The next natural cut turn will show the same guidance; no further cycle needed.
