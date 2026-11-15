# Bug Verification: "list top 5 processes" in chat now takes the windows-mcp fast path — 7.7 s end-to-end, genuine output, audited

- **Slug**: does-not-have-a-powershell-windows-mcp-tool
- **Tested**: 2026-11-14T12:55:00+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md (with the verification addendum)
- **Result**: **verified** — the chat has the PowerShell/windows-mcp tool, the routing nudge works, and the verification itself surfaced and closed two real gaps (the USER_CONTROL consent-wait protocol; the agent-node tool bindings)

## Summary

The original failing journey ("list top 5 processes on Windows" → read-only lane ask-back, no windows-mcp tool anywhere) is closed: the same class of request now completes in **7.7 s end-to-end** through the chat with a **1.5 s** `windows-mcp-process` audit row — the agent takes `windows_mcp_process_list` on the fast path, the consent protocol is handled transparently, and the genuine process table is relayed verbatim.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Service restoration | your `schtasks /run /tn windows-mcp-server` after reconnecting RDP | **pass** | :8800 LISTENING; probe ok |
| Live tool probe (pre consent-fix) | container `windows_mcp_process_list` | **finding** | returned the service's `{"code": "USER_CONTROL", "wait_seconds": 7.3}` — the lane misread the consent-WAIT as a refusal → fixed (bounded wait+retry, gateway pattern), pinned, rebuilt |
| Live tool probe (post consent-fix) | container `windows_mcp_process_list` | **pass** | ok — genuine top-5 table (vmmemWSL ~19.9 GB top) |
| Status tool live | container `windows_mcp_status` | **pass** | ok, reachable: true — honest probe |
| Chat replay 1 (bare phrasing) | "list top 5 processes by memory" | **known quirk** | routed to General, no tool call (the parked pre-router issue; same as this morning) — not this bug's scope |
| Chat replay 2 (local phrasing, pre binding-fix) | "on my computer, list…" | **finding** | the agent's own answer: "Fast path: windows_mcp_process_list… but that tool isn't in my available function list" — the DSL instruction was there, the agent-node tool binding was not → fixed (both tools added to the Hermes agent node's tools array, republished) |
| **Chat replay 3 (decisive)** | "on my computer, list the top 5 processes by memory" | **pass** | **turn 7.7 s · audit: `windows-mcp-process` executed 1.5 s · genuine table relayed** — the exact original request class, on the fast path, no confirm friction, no ask-back |
| Consent refusal path (bonus, live) | the pre-fix blocked probes | **pass** | the refusal classification produced the honest "blocked: the host did not approve execution" envelope before the wait-protocol fix — the machinery is correct for true refusals |
| Unit suite | `pytest tests/unit` | **pass** | 678 passed, 0 failed (incl. the USER_CONTROL-wait pins) |
| Lint | `ruff check` (changed files) | **pass** | All checks passed |

## Output Excerpts

```
container probe: {"status":"ok","tool":"Process","text":"Processes (5 shown): PID  Name … 8928 vmmemWSL …"}
chat replay 3:   conversation 80e7c2d5… | message_end 7.7s | answer 1060 chars
audit:           12:48:16 | windows-mcp-process | executed | 1.5s | Processes (5 shown)…
pytest tests/unit → 678 passed
```

## Residual Risks

- Bare phrasings ("list top 5 processes…") still route to General — the known classifier quirk; the parked **pre-router** decision is the structural fix. Local phrasings ("on my computer…", "what's running") reach the Hermes lane, where the fast path now works.
- The windows-mcp host service still requires an active interactive desktop to run at all (its own design) — a disconnected RDP session takes the lane down with an honest envelope + the recovery hint; re-logging on auto-starts it (LogonTrigger).
- The consent-wait retry is bounded (4 attempts, ≤15 s each) — a user who never approves gets the honest refusal envelope, never a hang.
- Privileged windows-mcp tools (registry/clipboard/notification) remain out of the chat slice pending the gate review (the T019 unprompted-registry-write finding).

## Recommendation

**Close the bug — verified end-to-end on the real journey.** The chat now exposes the windows-mcp fast path, the consent protocol is handled, the routing works for local phrasings, and every attempt is audited. The two verification-era findings (consent-wait, tool bindings) are closed within this lifecycle and pinned. The remaining residuals are known, documented, and belong to the parked pre-router decision and the host service's own design.
