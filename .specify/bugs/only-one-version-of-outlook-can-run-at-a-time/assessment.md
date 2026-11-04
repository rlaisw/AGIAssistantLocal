# Bug Assessment: "Only one version of Outlook" dialog — RunningApps returned bad data under the degraded MCP session

- **Slug**: `only-one-version-of-outlook-can-run-at-a-time`
- **Created**: 2026-11-04
- **Source**: pasted text ("pop up error: Sorry, we are having trouble starting Outlook. Only one version of Outlook can run at a time")
- **Verdict**: valid — but a **derivative effect of the upstream MCP degradation** (`officemcp-connection-error`, hermes-agent issue [#148459](https://github.com/NousResearch/hermes-agent/issues/148459)); new evidence: the degradation corrupts RunningApps data, not just tool-call arguments
- **Severity**: medium — a Windows dialog blocks the turn; the agent's attach-first rule worked correctly but received bad input

## Report (verbatim or summarized)

User report: *"pop up error: Sorry, we are having trouble starting Outlook. Only one version of Outlook can run at a time"*. The Windows dialog appeared on the user's desktop during an email-compose attempt. **OUTLOOK.EXE IS RUNNING** (PID 5580, 680MB) — yet the audit trail shows the agent's RunningApps check reported *"Outlook was not running"* at both 04:54 and 04:56. The agent correctly followed its attach-first instruction (check RunningApps → only launch if not running), but RunningApps returned incomplete data (listed only Excel, missed Outlook), so the agent launched Outlook → Windows blocked the second instance → the dialog appeared.

## Symptom

The Windows "Only one version of Outlook" dialog popped up because the agent tried to Launch Outlook when Outlook was already running — but the agent's RunningApps check reported Outlook as NOT running (bad data from the degraded MCP session). Expected: RunningApps correctly lists Outlook → the agent attaches to the running instance → no second-launch attempt → no dialog.

## Reproduction

1. The user has Outlook running (OUTLOOK.EXE PID 5580 confirmed via tasklist)
2. An email-compose turn at 04:54 UTC: STEP 1 RunningApps check returned `["Excel"]` — **Outlook was missing from the list** despite running
3. The agent (correctly following its instruction) saw "Outlook not running" → called Launch("Outlook")
4. Windows detected the already-running Outlook → showed the "Only one version" dialog → the Launch call hung
5. The same pattern repeated at 04:56: RunningApps returned `["Word", "Excel"]` — still missing Outlook
6. The MCP session was degraded (the known upstream defect) — RunningApps data was corrupted/incomplete

## Suspected Code Paths

- **Upstream** (`~/.hermes/hermes-agent/` — issue #148459): the degraded MCP session not only drops tool-call arguments but also corrupts RunningApps enumeration results — the agent received `["Excel"]` or `["Word", "Excel"]` when Outlook was demonstrably running
- **`src/agentic_rag_mcp/hermes_client.py`** — the "check RunningApps FIRST and attach" instruction is present and the agent followed it correctly; the failure was bad input, not bad behavior
- **OfficeMCP `Officer.RunningApps()`** — may also have a COM enumeration gap under a degraded session, but the service itself was healthy (HTTP 200); the corruption is in the gateway→OfficeMCP data path

## Root Cause Hypothesis

**High confidence.** The upstream MCP args-dropping degradation (issue #148459) also corrupts the **data returned by tool calls** — RunningApps returned an incomplete list (missing Outlook) while Outlook was running. The agent's attach-first instruction depends on accurate RunningApps data; with bad input, the agent makes the wrong (but rational) decision to Launch, triggering the Windows single-instance dialog. This is a **new evidence point** for the upstream issue: the degradation doesn't just affect tool-call arguments (what goes TO the server) but also tool-call results (what comes BACK).

## Proposed Remediation

**Preferred**: this is the upstream defect's territory. The in-repo mitigation for this specific derivative:
1. **Instruction hardening** in `OFFICE_INSTRUCTIONS`: "if Launch returns success but the app window doesn't appear or a dialog pops up, try GetComObject/Dispatch to attach to the existing instance instead — RunningApps may return incomplete data on a degraded session."
2. The upstream fix (issue #148459) is the cure — the RunningApps data will be accurate when the MCP session is healthy.
3. Close this bug as a derivative manifestation with the RunningApps-corruption evidence added to the upstream issue.

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_client.py` (one instruction line)

## Risks & Considerations

- The instruction hardening can't prevent the dialog — it can only recover after it (try Dispatch to attach). The actual prevention is the upstream fix.
- The RunningApps corruption means the attach-first rule is unreliable under a degraded session — the agent should have a fallback path.

## Open Questions

- [NEEDS CLARIFICATION: whether the RunningApps corruption is also present on a healthy session, or only when the MCP session is degraded. Test on a fresh session to confirm.]
