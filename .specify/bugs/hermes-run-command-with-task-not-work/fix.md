# Bug Fix: dispatch-leak detector — leaked `<invoke>` tool-call text is replaced with an honest dispatch-failure notice

- **Slug**: `hermes-run-command-with-task-not-work`
- **Fixed**: 2026-11-09
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The `honesty_check` code node gained a second, zero-false-positive detector: when the visible answer contains a leaked invocation tag naming a hermes tool (`<invoke|<function_call|<tool_call … hermes_…`) and no tool call actually happened that turn, the call provably failed to dispatch — the answer is replaced with an honest dispatch-failure notice (a model formatting glitch; nothing was done; re-send, fresh conversations are reliable) instead of the user seeing dangling text plus raw XML. The completion-claims logic is untouched.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `dify/AGIAssistant/AGI_Assistant.yml` — `honesty_check` code node | modified | new `leaked` test before the claims test: `/<(invoke\|function_call\|tool_call)[^>]*hermes_/i` on the visible answer, `!called`-guarded (a turn that really ran keeps its real result even if stray markup appears); new "Dispatch check: …" notice |

No python changed — the gate and tool were never implicated (nothing reached the sidecar in these turns; no audit rows).

## Diff Highlights (optional)

```js
// a leaked invocation tag naming a hermes tool proves the call was emitted
// as plain text and never dispatched
var leaked = /<(invoke|function_call|tool_call)[^>]*hermes_/i.test(visible);
if (!called && leaked) {
  return {result: 'Dispatch check: the local agent was NOT called — the tool call was emitted as plain text instead of being dispatched (a model formatting glitch), so nothing was done on your computer. Please send the request again; if it keeps happening, a fresh conversation is the most reliable path.'};
}
```

## Tests Added or Updated

- Node-harness cases (9 total): the two recorded drafts from this incident — `leaked-invoke-locale` (the exact `<invoke name="hermes_run_command">` text) → **REPLACED (dispatch notice)**; `silent-noemit-systeminfo` (dangling "I'll check…" only, no leak) → **PASSED** (documented residual — indistinguishable from ordinary text at the answer layer). All seven prior cases unchanged: fabricated-newtab-1/2/3 and fabricated-0853 → BLOCKED; honest-noemit-locale/disk and real-ip-turn → PASSED.

## Local Verification

- Commands: nine-case node harness (extracted live code vs recorded drafts) → **9/9 correct**.
- Live: published via the established console cycle; Postgres graph `09:31:32` carries the detector (`Dispatch check` text present, `t`).
- No python changes — the gate/tool suites are unaffected (green at last run this session).

## Deviations from Assessment

- None. The detector, notice, and harness cases match the proposed remediation exactly. (One harness-builder stumble during verification — a naive multi-row psql split fed the wrong fragment into the leak case and briefly showed a false PASS; refetched per-turn and re-run — the recorded leak is caught. Test-harness bug, not a fix defect.)

## Follow-ups

- The **silent no-emit shape** ("I'll check…" with no leak) remains undetectable at the answer layer — it degrades to the honest-but-empty turn; only the model/provider layer can fix the root. Watch for recurrences; the flake clusters on failure-laden conversation history (fresh conversations emitted reliably all day).
- Consider suggesting (in a future lifecycle) that users with a flaky conversation start a fresh one — the dispatch notice already says so.
- Fold this fix into the next lifecycle commit together with the `the-local-agent-was-not-called-for-this-request` docs.
