# Bug Fix: Long-turn Dify timeout — no-terminal-verification rule + Hermes iteration budget reduced

- **Slug**: `cannot-open-two-instances-of-outlook`
- **Fixed**: 2026-11-04
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The agent's instructions now explicitly forbid using terminal/shell/PowerShell commands for verification (the consent gate holds them for approval that API-server turns can never give, burning the turn budget and causing the Dify "peer closed connection" timeout), and the Hermes agent node's iteration budget is reduced from 30 to 15 (matching the PPT agent) so multi-step turns complete faster within Dify's MCP response window.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | `OFFICE_INSTRUCTIONS` gained: "NEVER use terminal, shell, or PowerShell commands for VERIFICATION — the gateway's consent gate holds them for interactive approval that API-server turns can never give, burning the turn budget. Always verify by reading through the Office application itself (open the file, read the cell, check the folder in the running app)." |
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | `hermes_agent` node's `maximum_iterations` reduced 30 → 15 (matching the PPT agent); the `agentic_strategy` node's value was accidentally touched and **reverted** to 30 (no functional change to the general lane) |

## Diff Highlights (optional)

```python
# OFFICE_INSTRUCTIONS — the consent-gate amplifier removed
"NEVER use terminal, shell, or PowerShell commands for VERIFICATION — "
"the gateway's consent gate holds them for interactive approval that "
"API-server turns can never give, burning the turn budget. Always "
"verify by reading through the Office application itself (open the "
"file, read the cell, check the folder in the running app)."
```

## Tests Added or Updated

- The existing 48 office suites stay green (the instruction is additive text at the agent layer)
- No new unit test — the rule fires at the agent-instruction layer, not in gate-testable code (same scope as the existing SESSION-DEGRADATION RULE)

## Local Verification

- Commands: `pytest tests/unit/test_hermes_office_tool.py tests/unit/test_office_gate.py` → **48 passed**; hot-patched to the sidecar; `deploy chatflow` → published
- The YAML was validated before publish (both nodes confirmed at their intended values: strategy=30, hermes=15)

## Deviations from Assessment

- The assessment's second remediation item ("raise the Dify-side MCP tool-call timeout") could not be applied — **there is no timeout field in the DSL**; the MCP response timeout lives in the Dify `langgenius/agent` plugin or console-level environment settings, outside this repo's artifacts. The instruction + iteration-budget changes are the in-repo mitigation; the DEPLOY.md note below documents the plugin-level setting for the owner to adjust in the Dify console.
- An editing accident briefly changed `agentic_strategy`'s iterations (30→15) instead of `hermes_agent`'s — caught and reverted in the same fix run; the general lane is untouched.

## Follow-ups

- Document the Dify MCP tool-call timeout in DEPLOY.md as a console-level setting (the owner can find it in the Dify console under the agent plugin's configuration, or via environment variables in the plugin daemon)
- The upstream MCP fix (hermes-agent issue #148459) remains the root cure for the long-turn problem
- Fold this fix into the next commit
- The user's email draft from the failed turn — check the Drafts folder manually; the connection broke after Outlook Dispatch, so a draft may exist
