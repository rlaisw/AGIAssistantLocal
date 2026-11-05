# Bug Fix: Gateway→OfficeMCP session degrades — args stripped, turns burn, user sees "no response"

- **Slug**: `officemcp-connection-error`
- **Fixed**: 2026-11-03
- **Assessment**: ./assessment.md
- **Status**: applied (mitigation — the root cause is upstream in hermes-agent, outside this repo)

## Summary

The agent's instructions now **stop the doomed retries** after 2+ consecutive empty RunPython deliveries and report `TASK: FAILED — OfficeMCP session stale` with the exact recovery, converting a 300–600 s silent failure into an immediate actionable error; the battery gained a **W0 watchdog pre-flight** that detects a degraded session in <10 s; and DEPLOY.md now documents this as a recurring known defect with the three-probe diagnosis. The durable fix remains upstream (hermes-agent's MCP-over-SSE client) — this repo's changes make the failure fast, honest, and recoverable.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | `OFFICE_INSTRUCTIONS` gained the SESSION-DEGRADATION RULE: "if 2+ consecutive RunPython calls return only the default echo, STOP retrying, end with TASK: FAILED — OfficeMCP session stale; recovery: hermes mcp remove/add + gateway restart. Do NOT fall back to PowerShell for the task steps" |
| `src/agentic_rag_mcp/deploy/battery.py` | modified | `scenario_hermes_office_task` gained the **W0 pre-flight**: a tiny office task ("check what Office apps are currently running") before every scenario run — a degraded session fails the scenario in <10 s with the recovery in the evidence string, instead of burning 300–600 s per turn |
| `DEPLOY.md` | modified | The troubleshooting row upgraded from "recovery procedure" to **"recurring known defect"**: the mechanism, the three-probe diagnosis (direct raw call → mcp test → lane task), the now-instruction-enforced honest failure, and the upstream-filed note |

## Diff Highlights (optional)

```python
# OFFICE_INSTRUCTIONS — the stop-retrying rule
"SESSION-DEGRADATION RULE (mandatory): if 2 or more consecutive RunPython "
"calls return only the default echo (your code argument was dropped — "
"the MCP session to OfficeMCP is stale), STOP retrying immediately and "
"end with 'TASK: FAILED — OfficeMCP session stale; recovery: hermes "
"mcp remove OfficeMCP then yes | hermes mcp add OfficeMCP --url "
"http://127.0.0.1:8888/sse then hermes gateway restart -y --detach'. "
"Do NOT fall back to PowerShell for the task steps..."

# battery.py — the W0 pre-flight
w0 = mcp_call("hermes_office_task",
              {"task": "check what Office apps are currently running", ...})
if w0.get("status") == "error":
    return False, "W0 SESSION-STALE pre-flight FAILED — recovery: ..."
```

## Tests Added or Updated

- The existing 48 office suites stay green (the instruction change is additive text; the rule fires at the agent layer, not in unit-testable gate code)
- The W0 pre-flight's healthy path is exercised by every future green scenario run; its degraded path returns the recovery string in the scenario evidence (manually verifiable during the next occurrence)

## Local Verification

- Commands: `pytest tests/unit/test_hermes_office_tool.py tests/unit/test_office_gate.py` → **48 passed**; hot-patched `hermes_client.py` + `battery.py` to the sidecar (restart + health wait)
- All three assessment probes were re-run in the assessment phase and were green — the mitigation is live for the next degradation event, which now fails fast and honestly instead of silently

## Deviations from Assessment

- **None.** The assessment's preferred remediation was applied exactly: the instruction rule, the watchdog pre-flight, and the DEPLOY.md upgrade. The upstream bug report was **not** filed (the assessment's open question — the owner can request it as a follow-up; the evidence chain from this session's three occurrences is ready).

## Follow-ups

- **File the upstream bug** against hermes-agent when ready — the reproduction is clean: direct MCP calls always deliver args; the gateway's don't after a period; cleared by remove/add + restart. The evidence chain from 2026-11-03's three occurrences is in this assessment.
- Fold this fix into the held T016 commit (same uncommitted working tree).
- The next time the defect recurs, the user experience changes from "no response" to an immediate "OfficeMCP session stale — recovery: …" message — the W0 pre-flight also catches it on every battery run.

---

# Addendum (2026-11-05, post-recurrence): root cause mechanism found — the cold window; lane now warms through it

Today the defect recurred worse (instant on fresh sessions, recovery no longer cleared it). An
**args-capture patch** on the Windows OfficeMCP package (a one-line log of every RunPython
invocation's received `code`/`data` to `C:\temp\officemcp_calls.log`, kept in place) produced the
mechanism:

- After an OfficeMCP process restart, roughly the **first 5 argument-carrying RunPython calls have
  their arguments stripped in transit** (the schema defaults execute and echo `OfficeMCP`);
  **call six onward delivers correctly**. Evidence: 5 default-echo entries followed by a delivered
  canary (`canary-args-probe-20261105`) and the real document-write code, in one live Word task that
  then completed.
- The old 2-echo SESSION-DEGRADATION RULE made every agent give up **inside** that cold window —
  which is why `remove/add` + gateway restart "recovery" never helped (it re-created the cold
  state), and why tasks that persisted past the window (2026-11-05 05:18–05:22 Word/Excel/PPT)
  worked while email turns died at their W0 canary.
- Intermittency within one session (broken 05:45 → working 05:54) is the window opening/closing
  around OfficeMCP restarts, not random.

**Lane fix applied**: `OFFICE_INSTRUCTIONS` now carries a cold-window-aware rule — retry with a
tiny canary (`'output = data'`) until one delivers, up to 8 attempts; only 8 consecutive echoes
declare staleness. Instruction-guard test extended; sidecar rebuilt + redeployed (26 tools).
Verified live (06:43): an email task ran with **0 stripped calls** and reached the Outlook
attach-failure protocol ask-back cleanly.

**Upstream narrowed**: calls **without** arguments always work; calls **with** arguments are
stripped during the cold window — the defect is in the hermes-agent MCP client's argument
serialization on a young session, not the transport. The args-capture log gives a byte-level
reproduction for hermes-agent issue #148459.

**OfficeMCP local patch inventory** (Windows, `uv` tool install): (1) existing local transport
patch notes, (2) the args-capture line in `RunPython` (OfficeMCP.py) writing to
`C:\temp\officemcp_calls.log` — keep for future evidence, remove when the upstream fix lands.
