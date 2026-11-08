# Bug Verification: compound app names + observe verbs — Control Panel request executes; the gate class is closed

- **Slug**: `the-launcher-only-handles-one-program-at-a-time`
- **Tested**: 2026-11-08T08:20+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original symptom — "open windows control panel , show me network adapter configuration, e.g. ip address setting" blocked as "more than one application named" — no longer reproduces: the exact request executed end-to-end in the fix phase (Control Panel launched, navigated to Network Connections, adapter Properties dialog opened, read-only attested), and this test phase's fresh compound (`open task manager`) launched in **15 s** with PID-level verification — proving the deployed stack handles compounds beyond the single already-proven case. The full gate matrix holds and no regressions appeared.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) — the exact request | live `hermes_launch_app("open windows control panel , show me network adapter configuration, e.g. ip address setting")` (fix phase, 08:06–08:13) | **pass** | `status ok` — *"Control Panel started fresh. I opened Network Connections and the Intel i219-LM adapter's Properties dialog. No settings were changed. LAUNCH: SUCCESS"* — full audit trail |
| Repeatability — a second canonical compound | live `hermes_launch_app("open task manager")` (this phase) | **pass** | `status ok` in **15 s** — *"Task Manager launched fresh… Taskmgr.exe, PID 18352, confirmed via tasklist"* — the compound map works through the deployed stack, not just for the reported case |
| Gate unit matrix | `pytest tests/unit/test_hermes_launch_gate.py tests/unit/test_hermes_launch_tool.py` | **pass** | 49 passed — compounds (5), the exact report phrasing, unknown-pair MULTI fallback, show-me split, all prior class tests (and/comma splits, search verbs, default browser, shell/chaining refusals) |
| Regression suite | `pytest tests/unit` | **pass** | **351 passed** |
| Lint | `ruff check src/agentic_rag_mcp/hermes_launch_gate.py` | **pass** | clean |

## Output Excerpts

```
Control Panel (fix phase): "…I opened Network Connections and the Intel
  i219-LM adapter's Properties dialog. No settings were changed." → ok
Task Manager (this phase): "Task Manager launched fresh… Taskmgr.exe,
  PID 18352, confirmed via tasklist" → ok — 15 s
pytest tests/unit → 351 passed
```

## Residual Risks

- The compound map is intentionally small and canonical; unmapped multiword names (e.g., "windows media player") still ask back honestly — extend `_COMPOUND_APPS` opportunistically as real usage surfaces them (a one-dict change)
- The observe-followup's execution quality (navigating and reading within the launched app) has one clean live sample; more phrasings may reveal WindowsMCP navigation edge cases — the honest-failure envelope covers them
- The 470 s Control Panel turn was cold-start + click-navigation cost — the standing latency floor; the deterministic-executor follow-up remains the structural fix

## Recommendation

**Close the bug — verified end-to-end.** The exact blocked request executes to the adapter Properties dialog with a read-only attestation, a second compound launches in seconds, the complete gate matrix holds (including every honest fallback — unknown pairs, shell/chaining, two real apps), and the full suite is green. This closes the third and final known manifestation of the launch-gate parsing class.
