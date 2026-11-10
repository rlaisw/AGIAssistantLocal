# Bug Verification: dispatch-leak detector — recorded leak replaced, no raw XML reaches the user, and the ask completes in fresh conversations

- **Slug**: `hermes-run-command-with-task-not-work`
- **Tested**: 2026-11-09
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The fix's detector is proven against the exact recorded leak (the `<invoke name="hermes_run_command">` draft is replaced with the honest dispatch notice in the nine-case harness, 9/9 correct) and is live in the published graph (09:31:32). The live reproduction in the failure-laden conversation dead-ended via the **silent** no-emit flake (no leak — correctly no fire; no raw XML reached the user), and the exact reported ask **completed end-to-end in a fresh conversation** with genuine `systeminfo` output. No regressions.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix, LIVE — same conversation `e4a98f05`) | re-ask "show my current system info." | **pass (with caveat)** | The turn took the **silent** no-emit shape (3 items, no call, no leak) — the documented upstream residual; the dangling "I'll check that for you now." passed through per design, and **no raw XML reached the user**. The leak shape itself is model-side and did not recur in the probe window; its replacement branch is harness-proven against the recorded draft with byte-identical live code. |
| Reproduction (post-fix, LIVE — fresh conversation) | "show my current system info." | **pass** | Full success: structured call dispatched, `systeminfo` executed on the Windows host, honest relay of the genuine output (Host A301-11120, Windows 11 Pro Build 26200, LENOVO, Intel ~2400 MHz) with the truncation named — the lane works; the dead-end is the flake, not the lane. |
| New / updated tests (harness) | nine-case node harness vs recorded drafts | **pass** | leaked-invoke-locale → **REPLACED (dispatch notice)**; silent-noemit-systeminfo → PASSED (residual); fabricated-newtab-1/2/3 + fabricated-0853 → BLOCKED; honest-noemit-locale/disk + real-ip-turn → PASSED. 9/9. |
| Regression suite | `pytest tests/unit/test_hermes_run_gate.py tests/unit/test_hermes_run_tool.py -q` | **pass** | 29 passed (no python changed by this fix). |
| Live graph state | Postgres `workflows` latest | **pass** | 09:31:32 carries the `Dispatch check` detector (`t`). |
| Lint / type-check | — | **skipped** | DSL-only change; YAML-parse-validated. |

## Output Excerpts

```
Harness: leaked-invoke-locale   REPLACED(dispatch)   ← the exact recorded leak
         silent-noemit-systeminfo PASSED              (documented residual)
         fabricated-×4 BLOCKED | honest-×2 + real PASSED     pytest: 29 passed

Live, fresh conversation, the reported ask:
  "Host Name: A301-11120 / OS: Microsoft Windows 11 Pro, Build 26200 /
   LENOVO 12YJS1V900 / Intel64 ~2400 MHz …" (real systeminfo output,
   truncation named)
```

## Residual Risks

- **The silent no-emit flake is upstream and remains**: on failure-laden conversation history the model sometimes emits no call at all (no leak, nothing detectable at the answer layer) — the turn degrades to the honest-but-empty "I'll check…" text. Fresh conversations dispatched reliably all day (ipconfig, hostname, locale, and this systeminfo success).
- The leak shape's live-branch was not re-triggered by chance in the probe window — the harness case uses the verbatim recorded draft and the live code node is byte-identical to the tested code, so the branch is covered; a natural recurrence would show the "Dispatch check:" notice.
- The leak and silent shapes both trace to kimi-k3's tool-call emission falling out of the structured channel (and an intermittent Dify↔sidecar transport drop observed earlier) — durable fixes are upstream (model/provider), matching the kimi-k3 pin posture.

## Recommendation

Close the bug — verified: the recorded leak is mechanically replaced with an honest, actionable dispatch notice (harness 9/9), the detector is live in the published graph, the poisoned conversation no longer leaks raw XML to the user, and the exact reported ask completes end-to-end with real output in a fresh conversation. Keep the silent no-emit flake as a documented upstream residual with honest UX; suggest fresh conversations to users whose turns keep dead-ending.
