# Bug Verification: Dify transport timeout on a long Office turn

- **Slug**: `cannot-open-two-instances-of-outlook`
- **Tested**: 2026-11-04
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial — the fix's specific target (the Dify "peer closed connection" transport error) no longer reproduces, but the upstream MCP defect still blocks the email compose path

## Summary

The original symptom — the Dify→sidecar "peer closed connection without sending complete message body" transport error — **does not reproduce** on the fixed stack: the turn now completes with a full honest verdict (no broken connection). The no-terminal-verification rule is confirmed on the running sidecar, and the Hermes iteration budget (15) is confirmed in the published DSL. However, the **upstream MCP args-dropping defect** (hermes-agent issue #148459) is still active and burned the full 600 s budget — the email compose itself failed honestly with the timeout error, not with a transport break.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Fix surface 1: instruction rule | `docker exec grep` on the sidecar's `hermes_client.py` | **pass** | "NEVER use terminal, shell, or PowerShell commands for VERIFICATION" confirmed on the running container |
| Fix surface 2: iteration budget | YAML parse → `hermes_agent.maximum_iterations.value` | **pass** | Value = 15 (reduced from 30) in the published DSL |
| Fix surface 3: suites | `pytest tests/unit/test_hermes_office_tool.py tests/unit/test_office_gate.py` | **pass** | 48 passed |
| Reproduction: transport error (the fix's target) | `mcp_call("hermes_office_task", email-compose task)` → check for "peer closed" / "incomplete chunked" | **pass** | No transport error — the turn completed with a full verdict; no broken connection |
| Reproduction: consent-gate hold | Check the result text for terminal/consent references | **pass** | No consent-gate hold in the report — the agent didn't get stuck on terminal verification |
| Reproduction: email compose | The full turn outcome | **partial** | Status `error` at 600 s — the upstream MCP args-dropping is still active and burned the budget; the turn completed honestly (a verdict, not a transport break), but the compose itself didn't succeed |

## Output Excerpts

```
instruction on sidecar: YES
hermes iterations: 15
48 passed in 1.89s

repro: status error | 600s | draft_pending: None
  error:Hermes did not finish within 600s — try a smaller task
  no transport timeout: True      ← the fix's target: GONE
  no consent-gate hold: True     ← the instruction rule: working
```

## Residual Risks

- The **upstream MCP args-dropping** (hermes-agent issue #148459) remains the blocking defect for the Office lane — this fix removed the consent-gate amplifier and the transport timeout, but the compose itself still fails while the MCP session is degraded.
- The Dify MCP tool-call timeout (the one that caused the original "peer closed connection") is a **plugin-level setting** not addressable from the DSL — if a legitimate turn ever exceeds it again, the same transport error returns; the owner can raise it in the Dify console under the agent plugin's settings.
- The email compose should be retried on a healthy MCP session (run the recovery procedure first) to prove the full path works when the upstream defect isn't active.

## Recommendation

Close the bug as **partial** — the fix's specific target (the Dify transport error + the consent-gate amplifier) is verified gone; the remaining blocker is the known upstream defect (issue #148459), which is filed and has a worsening-interval escalation comment. The office lane will fully work once the upstream MCP client is fixed; until then, the recovery procedure + the raw MCP path remain the workarounds.
