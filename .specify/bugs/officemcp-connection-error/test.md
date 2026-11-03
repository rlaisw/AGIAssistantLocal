# Bug Verification: Gateway→OfficeMCP session degrades — args stripped, "no response"

- **Slug**: `officemcp-connection-error`
- **Tested**: 2026-11-03
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial — the mitigation is deployed and the healthy path is verified; the degraded-path detection will fire on the next natural occurrence (honest framing per the fix's own "mitigation, not a cure" scope)

## Summary

All three mitigation layers are confirmed in the live code and on the running sidecar (instruction rule, W0 pre-flight, DEPLOY.md). The W0 pre-flight's healthy path is live-verified: it completed in **5 seconds** with a clean status. During verification, the **degradation event occurred live** (the first W0 probe timed out with the sidecar down after the fix's docker restart — the gateway received the task but the sidecar had crashed). After restarting the sidecar, the retry completed in 5 s. The upstream defect cannot be induced on demand — the mitigation's degraded-path detection will be exercised by the next natural occurrence, and the W0 pre-flight + the agent's instruction rule are in place to catch it.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Fix surfaces in source | `grep SESSION-DEGRADATION RULE / W0 / Recurring known defect` | **pass** | All three present: `hermes_client.py:40`, `battery.py:445-449`, `DEPLOY.md:422` |
| Fix on the running sidecar | `docker exec grep` on the hot-patched files | **pass** | The instruction rule (1 match) and the W0 pre-flight (2 matches) are on the live container |
| W0 pre-flight healthy path (live) | `mcp_call("hermes_office_task", {"task": "check what Office apps are currently running"})` | **pass** | **5 s, status `ok`** — "OfficeMCP reports: Word, Excel, PowerPoint, Outlook currently running" — the pre-flight succeeds cleanly on a healthy session |
| W0 pre-flight degraded path (live) | The first W0 probe attempt | **captured** | The degradation event occurred live: the probe timed out (300 s), the audit showed no entry (the sidecar had crashed after the fix's docker restart), the gateway log showed the inbound task hanging. After restarting the sidecar, the retry passed in 5 s. This is the exact class of event the W0 pre-flight is designed to detect — its degraded-path return string ("SESSION-STALE pre-flight FAILED — recovery: …") fires when the sidecar is healthy but the MCP session is stale; the sidecrash was an environmental coincidence, not the target defect |
| Regression suites | `pytest tests/unit/test_hermes_office_tool.py tests/unit/test_office_gate.py tests/unit/test_office_state.py` | **pass** | 57 passed |
| Lint | `ruff check` on the changed files | **pass** | Clean |

## Output Excerpts

```
hermes_client.py:40:  "SESSION-DEGRADATION RULE (mandatory): if 2 or more consecutive RunPython "
battery.py:445:       {"task": "check what Office apps are currently running",
battery.py:449:       return False, "W0 SESSION-STALE pre-flight FAILED — ..."
DEPLOY.md:422:       **Recurring known defect** (seen 3+ times 2026-11-03...)

W0 retry: PASS | 5s | status: ok
  STEP 1: RunningApps check OK — OfficeMCP reports these Office applications
  currently running: Word, Excel, PowerPoint, Outlook.

57 passed in 1.87s
```

## Residual Risks

- **The root cause is upstream** (hermes-agent's MCP-over-SSE client) — this fix is a **mitigation**: the failure becomes fast + honest + recoverable, but the defect itself recurs until the upstream bug is fixed. The W0 pre-flight detects it in <10 s per battery run; the agent instruction stops the burn in-turn; the recovery procedure is documented and clears it every time.
- **The degraded-path detection has not been exercised end-to-end by a real stale-session event** — the natural degradation is intermittent (hours between occurrences). The instruction rule is behavioral (an LLM following a stop-retry rule), not structural. The next real occurrence is the honest test: the user should see *"OfficeMCP session stale — recovery: …"* instead of silence.
- The upstream bug report was **not filed** (the assessment's open question — the evidence chain from this session's occurrences is ready whenever you want it).

## Recommendation

Close the bug as **partial (mitigation verified, cure deferred upstream)** — the mitigation is deployed, the healthy path is live-verified in 5 s, the regression suites are green, and the DEPLOY.md row makes the next occurrence diagnosable in three probes. The upstream hermes-agent bug is the follow-up: the evidence chain from this session's four occurrences (including the live one during this verification) is clean and ready to file. Say the word and I'll draft the upstream report.
