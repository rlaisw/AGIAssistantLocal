# Bug Assessment: Health check success is replaced by a false honesty-check failure

- **Slug**: no-html-report-and-no-reliability-monitor-applet
- **Created**: 2026-11-22
- **Source**: pasted text
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

> "no html report and no Reliability Monitor slug=no-html-report-and-no-Reliability-Monitor-applet
> only return :
> Honesty check: the health status claim did not match the real system health result returned this turn."

The user reports that a completed health check produced no HTML report link and no Reliability Monitor, and the chat contained only the honesty-check failure text.

## Symptom

A successful `system_health_check` whose real overall status is `warn` (or `fail`) is replaced with:

> Honesty check: the health status claim did not match the real system health result returned this turn.

The answer, report link, summary, and display/screenshot evidence are lost. Expected: keep the real health summary, append the published report link, and report display/capture separately.

## Reproduction

1. Complete a health check whose real result is `health.status=warn`, `health.score=72`.
2. Produce the normal summary containing the overall status followed by the required counts, e.g. `Overall health: WARN. Score: 72. Pass: 8, Warn: 3, Fail: 1, Info: 2, Skip: 2.`
3. Run the checked-in `honesty_check` code with that answer and result.

Observed using the actual DSL and the existing test harness: the guard returns exactly the reported string. The report URL is never appended because the status check returns before the missing-link append runs.

[NEEDS CLARIFICATION: whether Reliability Monitor actually appeared on the desktop before the answer was replaced. The code path proves the answer/link suppression; a separate display failure would need its own evidence.]

## Suspected Code Paths

- `dify/AGIAssistant/AGI_Assistant.yml:2000` — the `honesty_check` code node, specifically `claimedHealthStatus()`: it scans 100 characters after the first `overall` and returns the first key found in the fixed order `pass`, `warn`, `fail`, `unknown`. A following count line such as `Pass: 8` therefore wins over the earlier `WARN`.
- `dify/AGIAssistant/AGI_Assistant.yml:2002` — the `healthExecution` block compares that false `pass` value with the real `warn` status and returns the replacement before the report-link append.
- `tests/unit/test_mcp_action_dsl.py:1190` — static guard coverage exists, but the functional honesty tests only use an answer without count labels.
- `tests/unit/test_mcp_action_dsl.py:1208` — `test_offline_honesty_appends_a_missing_published_health_report_link` uses `Overall: WARN (score 72)` with no `Pass:` count, so it misses this false positive.

## Root Cause Hypothesis

Confidence: **high**. `claimedHealthStatus()` treats any occurrence of `pass`, `warn`, `fail`, or `unknown` within 100 characters after `overall` as the claimed overall status, and checks `pass` first. Health summaries must include pass/warn/fail counts, so a `WARN` or `FAIL` result followed by `Pass: N` is misread as an overall `PASS` claim. The honesty guard then replaces the complete answer—including any published report URL and Reliability Monitor/screenshot evidence—with the mismatch message.

## Proposed Remediation

**Preferred**: Replace the first-key-wins scan with an explicit parse of the status token adjacent to the overall label, for example:

```js
function claimedHealthStatus(text) {
  var match = text.match(
    /\boverall(?:\s+(?:health|status|result))?\s*(?::|=|-|is|was)?\s*(pass|warn(?:ing)?|fail(?:ed)?|unknown)\b/i
  );
  if (!match) { return ''; }
  var value = match[1].toLowerCase();
  if (value.indexOf('warn') === 0) { return 'warn'; }
  if (value.indexOf('fail') === 0) { return 'fail'; }
  return value;
}
```

This accepts `Overall health: WARN` while ignoring later count fields such as `Pass: 8`. When no explicit overall status is present, return `''` rather than guessing, so the guard does not over-block. Keep the score check and the report/display/screenshot checks unchanged.

**Alternatives**:
- Choose the earliest status-word position in the overall window instead of fixed key order. Smaller diff, but still guesses when the answer has no explicit overall status.
- Require the prompt to emit a machine marker such as `Overall: <STATUS>` and reject only deviations. Stronger parsing, but makes the formatter brittle.

**Files likely to change**:
- `dify/AGIAssistant/AGI_Assistant.yml`
- `tests/unit/test_mcp_action_dsl.py`

**Tests to add or update**:
- A `WARN` result with `Overall health: WARN. Score: 72. Pass: 8, Warn: 3...` must keep the answer and append the published report link.
- A `FAIL` result with `Overall health: FAIL. Score: 55. Pass: 5, Fail: 2...` must keep the answer and link.
- A false `Overall health: PASS` claim with a real `warn` result must still be blocked.
- Preserve the existing forged-link, failed-publication, forged-score, and forged-display tests.

## Risks & Considerations

- A too-permissive parser could let a false overall-status claim through; the regression pair must verify both acceptance and rejection.
- The fix is in the checked-in DSL only; both Dify apps must be republished by explicit ID (`194e1edf-2eba-442c-b10b-231bebb79c37` and `7863fbe2-47f8-48c9-b096-6f7da8536b08`), never by name.
- The honesty guard may still suppress a valid answer for other formatting variants; the parser should return `''` when the status is ambiguous rather than guess.
- No report-route, screenshot, audit, or health-action code should need changes.

## Open Questions

- [NEEDS CLARIFICATION: did the Reliability Monitor window actually appear before the answer was replaced, or did display also fail?]
- [NEEDS CLARIFICATION: what exact visible answer text triggered the live failure? The count-line format above reproduces the guard path deterministically.]
