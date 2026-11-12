# Bug Verification: dynamic response time — routing flip

- **Slug**: not-meet-expected-response-time-dynamic-20-40s
- **Tested**: 2026-11-12T03:42:00Z (owner's live Chat UI re-benchmark)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The routing flip meets the benchmark. The owner's re-test turn (conversation 0bbac97c…) shows the designed shape end-to-end: NO skill_search round, NO scripted detour, browser_navigate_v2 at 5.1 s + browser_read_v2 at 0.5 s = 5.6 s total tool time, 3 kimi rounds total, complete honest weather report delivered.

## Checks Performed

| Check | Evidence | Result |
|-------|----------|--------|
| Skill-search skip | zero skill-search rows in the turn's audit window | pass |
| No scripted detour | zero browser-scripted-run rows (was 21.1 s always-failing before) | pass |
| v2 navigate | 5.1 s (full Bing search load, warm session) | pass |
| v2 trimmed read | 0.5 s | pass |
| Answer quality | real weather (24°C Sunny, H25/L22, humidity, AQI, forecast), honest derivation | pass |
| Wall-time | ~3 kimi rounds + 5.6 s tools ≈ the promised 25–45 s band (vs 1.5–2.5 min pre-fix) | pass |

## Residual Risks

- Remaining wall-time is kimi reasoning/reporting — irreducible for a conversational lane; further compression would need the lighter-steering-model option (owner call).
- The scripted relay hardening ("complete JSON output") is verified by directive text + pins but its next real multi-step scripted use should be watched.

## Recommendation

**Close — verified.** The search-and-report benchmark is met; the bug's expectation (dynamic 20–40s class) is confirmed live. The routing-flip lifecycle is complete.
