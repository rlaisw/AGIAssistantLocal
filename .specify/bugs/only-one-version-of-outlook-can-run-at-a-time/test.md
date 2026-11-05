# Bug Verification: "Only one version of Outlook" — attach-failure protocol

- **Slug**: `only-one-version-of-outlook-can-run-at-a-time`
- **Tested**: 2026-11-05T06:25+00:00 (overwrites nothing — first test.md of the recurrence cycle)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

The original symptom — a second-instance `Launch` on the COM-unreachable Outlook producing the Windows "only one version of Outlook" dialog — **did not reproduce**: the live email task against the still-broken Outlook state never called Launch and ended in an honest error. However, the fix's full ask-back path (probe → attach-fail → two-option consent) could not be exercised end-to-end because the unrelated upstream channel defect (#148459, argument-stripping) dominates every turn first; the guard's first leg (never re-Launch) is proven, the second leg (the consent ask-back) remains unverified in production.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Live reproduction post-fix | `hermes_office_task` "write an email …" against the broken Outlook state (direct sidecar MCP call, 06:21:37) | **pass on the core symptom** | No `Launch` call, no dialog, no second-instance attempt — the audit trail shows canary → direct-SSE fallback canary → verification probes only; the turn ended `error` with an honest multi-step report |
| Protocol ask-back path (two-option consent) | same live turn | **not-reached** | The #148459 argument-strip fired first (STEP 1 canary: 3+7 emissions stripped across main and a delegated fresh-channel subagent); the session-degradation rule ended the task before the attach-failure ask-back could surface |
| Outlook COM-unreachable state re-confirmed | GetActiveObject probe in the live turn | **pass (state present)** | "Operation unavailable (Outlook not in the ROT at that moment)" — the precondition the protocol targets is still live; the Dispatch follow-up probe was blocked by the terminal consent gate, as designed |
| New / updated tests | `pytest tests/unit/test_hermes_office_tool.py tests/unit/test_office_gate.py` | **pass** | 49 passed, including `test_office_instructions_contain_attach_failure_protocol` |
| Regression suite | `pytest tests/unit` | **pass** | 332 passed |
| Lint / type-check | `ruff check src/agentic_rag_mcp/hermes_client.py`; `mypy` same file | **pass** | All checks passed / no issues found |

## Output Excerpts

```
live turn (06:21:37 audit) — no Launch anywhere:
  STEP 1: Canary … FAILED — arguments stripped in transit (3 + 7 across a
          delegated fresh-channel subagent)
  STEP 2: Direct-SSE fallback canary OK — office_rpc.py over
          http://127.0.0.1:8888/sse echoed 'canary-ql9z7' (server healthy)
  STEP 4: GetActiveObject probe 'Operation unavailable' (Outlook not in the
          ROT); Dispatch probe BLOCKED by the terminal consent gate;
          no draft ID could be read back → status: error, honest report

pytest tests/unit → 332 passed
ruff/mypy on hermes_client.py → clean
```

## Residual Risks

- The two-option consent ask-back (and the consent-gated `taskkill` + relaunch) has never executed against the real broken state — every candidate turn so far is intercepted by the #148459 channel degradation. Its first leg (never re-Launch) is instruction-level and guarded by test; its second leg is unproven in production.
- The upstream channel defect is the enabler of the whole bug class; until #148459 is fixed, RunningApps can still lie and re-create the broken Outlook state after any recovery.
- The live turn's partial compose may have left an unverified draft named `protocol-verify-1105` in the Drafts folder (the turn reported "no draft ID could be read back"); it is harmless and the user can delete it from Outlook.
- The user's Outlook remains in the COM-unreachable state right now — closing and reopening the window once clears it.

## Recommendation

**Hold as partial** — the regression this fix targets (second-instance Launch → Windows dialog) is demonstrably gone, and the instructions are test-guarded. Re-run this verification once the #148459 channel delivers arguments on a fresh session: the expected next-live-turn behavior is the two-option ask-back, and after "restart Outlook" consent, one honest taskkill→relaunch sequence. Until then, the practical unblock remains: close and reopen Outlook once, then retry the email task.
