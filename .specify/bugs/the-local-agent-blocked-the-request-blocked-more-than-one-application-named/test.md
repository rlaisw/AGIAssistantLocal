# Bug Verification: check/read/tell-me verbs — the MULTI block on "open X , check Y" is gone

- **Slug**: `the-local-agent-blocked-the-request-blocked-more-than-one-application-named`
- **Tested**: 2026-11-09T02:40+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified (in scope) — with the documented ~300 s Dify-daemon ceiling prominently noted in every live sample

## Summary

The original symptom — "help to open chrome browser , check hong kong temperature today" refused as "more than one application named" — no longer reproduces: the exact phrasing now passes the gate (target `chrome`, the check-tail riding the desktop followup), proven both at the gate unit level and in two live chat turns where the agent passed the full task to `hermes_launch_app` and the tool executed. Both live turns ran to the **documented ~300 s Dify plugin-daemon ceiling** (`the-local-agent-hit-a-transport-error`, closed as a known limit this morning) and ended with honest transport-error relays — a separate, known issue, not this bug's symptom.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix), the exact request | live chat turn (fix phase, 02:12–02:17) | **pass (gate)** | 02:06:30 identical request was `blocked`; post-fix the agent passed the full task unchanged, the tool executed 307 s, then the known 300 s ceiling cut it with the honest relay — the MULTI block is gone |
| Reproduction (post-fix), light check-followup | live chat turn "open task manager , check cpu usage" (this phase) | **pass (gate)** | Same shape: no block, agent passed the full text, tool executed to the 300 s ceiling (306 s), honest relay, `status=normal` for the relay itself |
| Gate unit matrix | 9-case reproduction set | **pass** | Exact report phrasing → `ok, chrome + 'check hong kong temperature today'`; and/comma forms of check/read/tell-me; all fallbacks intact (unknown pair MULTI, bare `open search` ask-back) |
| New / updated tests | `pytest tests/unit/test_hermes_launch_gate.py tests/unit/test_hermes_launch_tool.py` | **pass** | 55 passed — incl. the 3 new verb tests |
| Regression suite | `pytest tests/unit` | **pass** | **357 passed** |
| Lint | `ruff check src/agentic_rag_mcp/hermes_launch_gate.py` | **pass** | clean |

## Output Excerpts

```
gate: "help to open chrome browser , check hong kong temperature today"
  -> ok | target: chrome | followup: 'check hong kong temperature today'
live (fix phase): blocked(02:06:30) → post-fix agent passed full task,
  tool executed 307s → known 300s ceiling, honest relay
live (this phase): "open task manager , check cpu usage" → same clean
  pass-through, executed 306s → ceiling, honest relay | pytest → 357 passed
```

## Residual Risks

- Both live followups executed until the **~300 s Dify-daemon known limit** cut them — the check-followup execution is currently too slow on this box to complete within the ceiling (WindowsMCP snapshot captures run 20–26 s each and the agent needs several). This is the known limit's operating cost, tracked in its own lifecycle: split requests ("open X", then a light check) or wait for the upstream Dify fix. The *parsing* fix this bug owns is fully proven.
- The desktop-control consent waits (user idle) add unbounded time when the user is active — hands-off is still required during followups
- A sub-300 s check-followup completion remains desirable as a natural sample — any light task (e.g., a short read) will provide it

## Recommendation

**Close the bug — verified in scope.** The exact blocked phrasing now passes the gate in every check (unit matrix ×2, live ×2), all honest fallbacks are regression-guarded, and the remaining failure mode in the live samples is the separately-tracked, documented Dify ceiling — whose relays are honest by design. The parsing class now covers input (type/click/press/enter/scroll), query (search/find/look up/google), and observe (show/display/view/check/read/tell me) verbs; future natural phrasings extend the same one-word + one-test pattern.
