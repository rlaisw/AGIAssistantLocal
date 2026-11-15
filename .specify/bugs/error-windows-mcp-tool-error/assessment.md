# Bug Assessment: USER_CONTROL deferral surfaces as a raw tool-error with a misleading recovery hint

- **Slug**: error-windows-mcp-tool-error
- **Created**: 2026-11-14T13:42:00+00:00
- **Source**: pasted text (the chat's error envelope plus the agent's reasoning trace: fast path taken correctly, tool called, USER_CONTROL error relayed with the "start the Scheduled Task" hint)
- **Verdict**: valid — the envelope and the relay hint misrepresent what actually happened (the service is up; it deferred while the desktop user was active)
- **Severity**: medium — hits the fast path exactly when the owner is actively using the machine (i.e., while chatting), which is often; the turn stays honest but ends useless with confusing guidance

## Report (verbatim or summarized)

> error:windows-mcp-tool-error — {"code": "USER_CONTROL", "status": {"state": "user", "generation": 92, "wait_seconds": 8.514…}}

The pasted agent trace shows correct behavior up to the envelope: it recognized the fast path (windows_mcp_process_list, not hermes_run_command), called the tool, and honestly relayed the error — but then appended the lane-down recovery hint ("start the Scheduled Task: schtasks /run /tn windows-mcp-server") because the envelope's status was `error`, and the DSL rule says errors carry the schtasks hint.

No URL was supplied with the report.

## Symptom

A process-listing request made while the desktop user is active returns, after the lane's bounded consent retries exhaust (~26–31 s), a raw JSON error (`USER_CONTROL`, `state: user`) classified as a generic tool-error — and the agent then relays a recovery hint for a service that is actually running fine. Expected: a named, actionable envelope — "the Windows-MCP service deferred the call while you are active on the machine; ask again in a few seconds" — with no schtasks hint, audited as a deferral, not an error.

## Reproduction

From the audit trail (both rows `operation: windows-mcp-process`, `decision: error`):

1. 2026-11-14 12:57:47 UTC — duration **25.6 s**, reason = `error:windows-mcp-tool-error — {"code": "USER_CONTROL", …}` (first observed in the prior bug's test phase, recorded there as a residual).
2. 2026-11-14 13:34:56 UTC — duration **30.9 s** — the user's reported turn: 4 retry-waits (~8.5 s each) exhausted while the desktop was active, same raw envelope.
3. Contrast rows the same day: identical calls succeeded in 0.5–11.3 s whenever the desktop was quiet — the deferral is state-dependent (the service's USER_CONTROL: "state": "user" = the desktop user is in control; wait_seconds is its suggested backoff), not a lane outage.

## Suspected Code Paths

- `src/agentic_rag_mcp/windows_mcp/client.py` — the USER_CONTROL retry loop (added 2026-11-14): 4 attempts × min(wait_seconds, 15 s), then the final response falls through to the generic `error:windows-mcp-tool-error` branch. The exhaustion path needs its own classification: still-pending USER_CONTROL after the retries = a **deferral**, not a refusal (classify_refusal is for explicit declines) and not a lane-down error.
- `dify/AGIAssistant/AGI_Assistant.yml` — the fast-path rule and tool description instruct "on status error include the recovery hint (start the Scheduled Task…)" — correct for unreachable-lane errors, wrong for deferrals. With the lane returning `blocked` for deferrals, the existing DSL rule ("on 'blocked' give the reason verbatim") already relays correctly without a hint.

## Root Cause Hypothesis

**High confidence.** The windows-mcp service's USER_CONTROL "state": "user" is a desktop-activity deferral: while the user is actively using the machine, the service tells callers to wait (~wait_seconds) — it is neither a consent dialog nor an outage. The lane's retry loop handles the waits correctly, but when the retries exhaust (the user stays active for ~30 s), the final USER_CONTROL response is classified as a generic tool-error, so (a) the chat relays raw JSON and (b) the agent attaches the schtasks recovery hint for a service that is up. The exhaustion path simply lacks its own envelope class.

## Proposed Remediation

**Preferred** (one classification + one envelope, lane-side):
1. In `client.py`: after the consent-retry loop exhausts, if the final error is still a USER_CONTROL response, return a named deferral envelope — `{"status": "blocked", "reason": "blocked: the Windows-MCP service deferred the call while the desktop user is active (USER_CONTROL) — nothing ran; wait a few seconds and ask again"}` — audited as `decision: blocked`. Explicit declines keep the existing "host did not approve" refusal; only the exhausted-still-pending case gets the deferral wording.
2. DSL needs no change: the blocked class already relays verbatim without the schtasks hint (the rule attaches hints to `error`, not `blocked`).

**Alternatives**:
- Longer retry windows (e.g., total 60 s) — rejected: the user is left waiting either way; the honest named deferral plus a quick retry is better UX than a longer silent wait inside one turn.
- Agent-side interpretation of the raw JSON — rejected: deterministic classification belongs in the lane, not in LLM reasoning over JSON payloads.

**Files likely to change**:
- `src/agentic_rag_mcp/windows_mcp/client.py`
- `tests/unit/test_windows_mcp_lane.py`

**Tests to add or update**:
- Fake-session behavioral test: a call whose every attempt returns USER_CONTROL → after the bounded retries, the envelope is the blocked deferral (named text, no raw JSON, no schtasks hint) and the audit row is `decision: blocked`.
- Pin that an explicit-decline refusal still produces the "host did not approve" wording (unchanged classes).

## Risks & Considerations

- The deferral wording must not promise a consent prompt exists; "deferred while the desktop user is active" describes the observed signal without inventing UI facts.
- The blocked classification interacts with the loop gate the same way as other blocked rows (operational class) — no loop-side change needed.
- Deferral frequency is inherently tied to the user's own activity — the envelope wording ("wait a few seconds and ask again") sets the right expectation; the service's wait_seconds keeps the retry honest.

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the mechanism (activity-deferral, retries, exhaustion) is fully evidenced by the audit trail and the day's contrasting successes.]
