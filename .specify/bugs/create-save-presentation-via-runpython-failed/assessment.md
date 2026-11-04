# Bug Assessment: RunPython create/save — upstream MCP args-dropping (16th manifestation)

- **Slug**: `create-save-presentation-via-runpython-failed`
- **Created**: 2026-04
- **Source**: pasted text (error message)
- **Verdict**: valid — but the **same upstream MCP degradation** (issue [#148459](https://github.com/NousResearch/hermes-agent/issues/148459)); the SESSION-DEGRADATION RULE fired correctly (4 consecutive empty deliveries detected, stopped, reported TASK: FAILED with recovery)
- **Severity**: low — known root cause, mitigation working, recovery + retry resolves

## Assessment

16th manifestation. The audit shows STEP 1 (RunningApps check) succeeded, then STEP 2 (RunPython) hit the args-dropping on 4 consecutive calls. The canary/rule detected it and the agent stopped immediately. Run the recovery and retry — the standard procedure.

## Recommendation

Recovery + retry. Close as a manifestation record of hermes-agent issue #148459.
