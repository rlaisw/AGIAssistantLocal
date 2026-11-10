# Bug Verification: honesty-check precision — false accusation gone, fabrications still blocked, and the original locale ask now completes end-to-end

- **Slug**: `the-local-agent-was-not-called-for-this-request`
- **Tested**: 2026-11-09
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The reported symptom — the honesty check firing on legitimate asks (tool names mentioned in reasoning) and dead-ending the user in a "send again" loop — no longer reproduces: re-asking both original questions in the same failure-history conversation produced no false accusation (the honest drafts passed through untouched), the seven-case harness shows all four recorded fabrications still **blocked** (including the 08:53 "the tool returned" class) while both honest no-emit drafts now **pass**, and the exact reported ask — *"show my system locale setting"* — completed end-to-end in a fresh conversation with the **real** `systeminfo` output relayed (System Locale `zh-tw`, Input Locale `en-us`). No regressions: 91/91 suites; the published graph (09:14:36) carries all three fix elements.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix, LIVE — same poisoned conversation `e4a98f05`) | re-ask "show my system locale setting" and "check my hard disk disk spaces" | **pass** | Neither ask produced the false "Honesty check" notice anymore. Both hit kimi's upstream no-emit flake (3 items, no call — the documented residual), and the honest drafts ("I'll check that for you.") passed through un-branded, exactly per the replace-only-on-claimed-action design. The false-accusation loop is gone. |
| Reproduction (post-fix, LIVE — fresh conversation, the reported ask) | "show my system locale setting" (×2 fresh conversations) | **pass** | First attempt: the call **was emitted** with both args (proving the flake is history-correlated, not instruction-caused) and the turn died in the documented transport class (no audit row; session terminated mid-call; relay honestly reported the transport error with no retry per the rule). Second attempt: **full success** — gate mapped locale → `systeminfo`, the command ran, and the answer relayed the genuine locale lines + the truncation note. |
| New / updated tests (harness) | node harness vs 7 recorded drafts | **pass** | fabricated-newtab-1/2/3 → BLOCKED; fabricated-0853 → BLOCKED (via the new `the tool (returned|responded)` pattern); honest-noemit-locale/disk → PASSED; real-ip-turn → PASSED. |
| Regression suite | `pytest tests/unit/test_hermes_run_gate.py tests/unit/test_hermes_run_tool.py tests/unit/test_hermes_launch_gate.py tests/unit/test_hermes_launch_tool.py -q` | **pass** | 91 passed, including the new `test_locale_asks_map_to_systeminfo`. |
| Live graph state | Postgres `workflows` latest | **pass** | 09:14:36 carries the narrowed regex + `the tool (returned|responded)` + the emit-the-call bullet + the locale mapping (`t`/`t`/`t`). |
| Lint / type-check | — | **skipped** | DSL + one gate-module phrase changed; the gate source is finding-free (checked in the 033 lifecycle); the yml is YAML-parse-validated. |

## Output Excerpts

```
Harness: fabricated-newtab-1..3 BLOCKED | fabricated-0853 BLOCKED
         honest-noemit-locale PASSED  | honest-noemit-disk PASSED
         real-ip-turn PASSED                                   pytest: 91 passed

Live, fresh conversation, the exact reported ask:
  "Here are your locale settings from systeminfo:
   - System Locale: zh-tw;Chinese (Taiwan)
   - Input Locale: en-us;English (United States)
   Related: Time Zone: (UTC+08:00) Beijing, Chongqing, Hong Kong, Urumqi"
```

## Residual Risks

- **kimi-k3's no-emit flake** (upstream, documented): intends a call, narrates "I'll check…", emits nothing — it clusters on failure-laden conversation history (the same conversation emitted fine twice in the morning, flaked in the afternoon, and fresh conversations emit reliably). Post-fix it produces an honest-but-empty turn instead of a false accusation; a fresh conversation is the working path.
- **The intermittent transport drop** (the known environmental class from the `the-local-agent-hit-a-transport-error` lifecycle) hit one probe mid-call before any verdict; the relay handled it per the no-retry rule with honest advice. Re-asking worked immediately.
- Disk-space asks remain honestly uncovered (gate ask-back with the list) until an allowlist amendment adds a read-only volume command.
- The visible-answer extraction keys on kimi's ```-fence output shape; fence-less text falls back to testing the whole answer (over-block, never under-block), and a no-call answer that itself contains code fences is only tested after its last fence — rare, and always in the honest direction.

## Recommendation

Close the bug — verified live end-to-end: the guard no longer false-accuses (the recorded honest drafts pass; the same poisoned conversation no longer loops), it still blocks every recorded fabrication including the fabricated-tool-interaction class, its block message now names working asks, and the originally dead-ended question returns the machine's real locale. Keep the two documented residuals (upstream no-emit flake, intermittent transport drops) as known behaviors with honest UX; a future allowlist amendment can add a volume command for disk-space asks.
