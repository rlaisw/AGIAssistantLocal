# Bug Fix: Health status honesty parser no longer mistakes count labels for the overall status

- **Slug**: no-html-report-and-no-reliability-monitor-applet
- **Fixed**: 2026-11-22
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`claimedHealthStatus()` now reads an explicit status token adjacent to `overall` instead of returning the first of `pass|warn|fail|unknown` found anywhere in the following 100 characters. A normal `Overall health: WARN ... Pass: 8` summary is accepted and keeps the report link; a real false `PASS` claim is still blocked.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | Replaced the first-key-wins health status scan with an adjacent-token parser; ambiguous or count-only text returns no claim. |
| `tests/unit/test_mcp_action_dsl.py` | added tests | Added WARN/FAIL count-label acceptance, false-PASS rejection, and ambiguous-status non-guessing coverage. |

## Diff Highlights

```js
var rest = lower.slice(idx + 7);
if (!/^[^a-z0-9]*(health|status|result|pass|warn|fail|unknown)/.test(rest)) { return ''; }
rest = rest.replace(/^[^a-z]+/, '');
for (var q = 0; q < 3; q++) {
  rest = rest.replace(/^(health|status|result)([^a-z]+)/, '');
}
var match = rest.match(/^(pass|warn|fail|unknown)/);
if (!match) { return ''; }
```

The parser accepts `Overall health: WARN`, `Overall status: FAIL`, and `Overall: PASS`, but returns `''` for `Overall: 8 pass, 3 warn` rather than guessing.

## Tests Added or Updated

- `tests/unit/test_mcp_action_dsl.py::test_offline_honesty_accepts_warn_overall_with_count_labels` — WARN plus `Pass: 8` keeps the answer and appends the published report link.
- `tests/unit/test_mcp_action_dsl.py::test_offline_honesty_accepts_fail_overall_with_count_labels` — FAIL plus counts keeps the answer and link.
- `tests/unit/test_mcp_action_dsl.py::test_offline_honesty_blocks_a_false_pass_claim_with_count_labels` — a real WARN result with `Overall health: PASS` is still blocked.
- `tests/unit/test_mcp_action_dsl.py::test_offline_honesty_does_not_guess_an_ambiguous_overall_status` — count-only overall text is not treated as a status claim.

## Local Verification

- Commands run: `.venv/bin/python -m pytest tests/unit/test_mcp_action_dsl.py -q` → **113 passed**.
- Commands run: `.venv/bin/python -m pytest tests/unit/test_mcp_action_*.py -q` → **571 passed**.
- Commands run: `.venv/bin/ruff check tests/unit/test_mcp_action_dsl.py` → **all checks passed**.
- Commands run: `git diff --check` → **clean**.
- Manual reproduction: the exact reported failure scenario (`health.status=warn`, score 72, `Overall health: WARN ... Pass: 8`) now returns the original answer plus `[Open the system health report](...)` instead of the honesty replacement.

## Deviations from Assessment

None. The fix stays within the two files named by the assessment. The assessment's open question about whether Reliability Monitor actually appeared remains a live-verification item, not a code change.

## Follow-ups

- Republish both Dify apps by explicit ID (`194e1edf-2eba-442c-b10b-231bebb79c37`, `7863fbe2-47f8-48c9-b096-6f7da8536b08`); do not use name-based deploy.
- Run one live health check with warnings and confirm the report link and Reliability Monitor evidence survive the honesty guard.
- Add an opt-in live Dify health-confirm case with a count-bearing WARN/FAIL summary if one is not already covered.
