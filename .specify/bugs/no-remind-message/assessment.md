# Bug Assessment: Reminder and finished message absent from the live app

- **Slug**: no-remind-message
- **Created**: 2026-11-23
- **Source**: pasted text
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

> "no remind message and finished message"

The expected behavior is the health-check draft showing the wait reminder above the exact offer, and the completed health answer ending with a report-finished message. Neither appears in the live app.

## Symptom

The repository contains both messages, but the live sidecar and both published Dify apps do not.

## Reproduction

1. Run the health-check draft and confirm flow in the live chat.
2. Observe the draft offer has no “Please wait about 2-5 minutes…” paragraph.
3. Observe the completed answer has no “System-Self-Check finished…” line.

## Suspected Code Paths

- `dify/AGIAssistant/AGI_Assistant.yml:2000-2003` — the checked-in finalizer contains `healthDraftNotice` and `System-Self-Check finished`, but the live app exports do not.
- `src/agentic_rag_mcp/mcp_action/service.py:19` — `_HEALTH_WAIT_NOTICE` exists in the repo; the running sidecar does not have it.
- Live Dify exports: both `194e1edf-2eba-442c-b10b-231bebb79c37` and `7863fbe2-47f8-48c9-b096-6f7da8536b08` contain neither `healthDraftNotice` nor `System-Self-Check finished`.
- Sidecar probe: `hasattr(service, "_HEALTH_WAIT_NOTICE")` is **False**.

## Root Cause Hypothesis

Confidence: **high**. The code changes were made and unit-tested but never deployed. The previous deploy/republish command did not execute successfully, so the container still runs the old service and both Dify apps still run the old `honesty_check` node. This is a deployment-state gap, not a missing-code or finalizer-logic bug.

## Proposed Remediation

**Preferred**:
1. Run `python -m agentic_rag_mcp.deploy redeploy` to rebuild/recreate the sidecar with `_HEALTH_WAIT_NOTICE`.
2. Publish the checked-in DSL to both explicit app IDs:
   - `194e1edf-2eba-442c-b10b-231bebb79c37`
   - `7863fbe2-47f8-48c9-b096-6f7da8536b08`
3. Re-export both apps and assert `healthDraftNotice` and `System-Self-Check finished` are present.
4. Run a live draft → confirm and assert:
   - the reminder appears above the exact offer;
   - the completed answer ends with the finished line;
   - the report path and full HTML remain.

**Files likely to change**:
- No source changes expected.
- Deployment target: sidecar container + both Dify apps.

**Tests to add or update**:
- Live post-deploy export assertion for both app IDs.
- Live chat assertion for the reminder placement and finished line.

## Risks & Considerations

- Both Dify apps share the same name; use only the explicit IDs above.
- Windows-MCP `CONTROL_UNAVAILABLE` previously blocked the health execution; ensure the host control session is available before the live check.
- If the messages are still absent after a confirmed deploy/republish, re-open this bug and inspect the live finalizer, not the checked-in copy.

## Open Questions

- None; the deployment-state evidence is conclusive.
