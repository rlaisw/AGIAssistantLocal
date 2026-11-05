# Bug Verification: direct browser MCP channel — the codified path carried a live stripped-channel turn in 89 s

- **Slug**: `the-local-agent-hit-a-transient-channel-error`
- **Tested**: 2026-11-05T09:52+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The fix's exact target scenario occurred naturally during verification: a live email compose hit a stripped gateway channel, and the agent followed the codified rule — detected the strip, switched to the direct OfficeMCP channel, ran **all** task steps there, and composed the draft in **89 seconds** (`status ok, draft_pending True`) — versus the multi-minute, multi-attempt turns this bug reported. The direct-channel protocol itself was additionally verified with a conformant raw MCP-SSE client from WSL (handshake → initialize → tools/call → token echoed with full arguments).

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Direct-channel protocol (raw) | conformant MCP-SSE client: SSE GET → endpoint → initialize → initialized → `tools/call RunPython` with args | **pass** | `{"success":true,"output":"direct-channel-protocol-verified-1105"}` — arguments delivered over the exact codified path |
| Reproduction (post-fix) — stripped-phase email compose | live `hermes_office_task` email task, 09:50–09:52 | **pass** | Gateway channel stripped during the turn → the agent switched per the rule: "all task steps ran via the direct OfficeMCP channel at 127.0.0.1:8888… STEP 1: channel check OK (via direct channel)" → draft composed, verified, `status ok, draft_pending True`, **89 s** |
| Reproduction (post-fix) — healthy-phase compose | live email task, 09:42 (fix phase) | **pass** | canary delivered immediately, no direct-channel needed — the rule doesn't disturb healthy turns |
| Second-instance / window check | tasklist Outlook count after both composes | **pass** | exactly ONE OUTLOOK.EXE throughout; attach without Launch; window-dedup rule in place (the "two instances" effect can only be extra windows, now suppressed by instruction) |
| New / updated tests | `pytest tests/unit/test_hermes_office_tool.py tests/unit/test_office_gate.py` | **pass** | 49 passed — direct-channel contract, window-dedup, falsified models absent |
| Regression suite | `pytest tests/unit` | **pass** | 332 passed |
| Lint | `ruff check src/agentic_rag_mcp/hermes_client.py` | **pass** | clean |

## Output Excerpts

```
raw protocol probe: endpoint /messages/?session_id=2a44288e… → initialize ok
  → RunPython → {"success":true,"output":"direct-channel-protocol-verified-1105"}
  DIRECT CHANNEL PROTOCOL: VERIFIED
live compose (stripped phase): "The gateway's RunPython channel was stripped
  (arguments arrived empty, default echoed), so all task steps ran via the
  direct OfficeMCP channel at 127.0.0.1:8888. STEP 1: channel check OK
  (via direct channel)…" → status ok, draft_pending True — 89 s
pytest tests/unit → 332 passed
```

## Residual Risks

- The direct channel depends on WSL mirrored loopback keeping `127.0.0.1:8888` reachable from the gateway host; a networking-mode change would need the WSL-side relay alternative (documented in `say-the-local-agent-failed…` fix.md)
- The browser/fetch tool's exact capabilities vary with hermes-agent updates; the instruction pins the protocol (endpoint, handshake, message POST) so the path stays reconstructible
- The upstream strip itself (#148459) is unresolved — the lane now routes around it deterministically, but the gateway's own MCP client remains defective (conclusive isolation evidence is in the upstream drafts, awaiting a write-capable token)
- Another verification draft ("final-verify-1105") joined the user's Drafts folder — delete unwanted copies
- One naturally-stripped occurrence is a single production data point; the battery/next user turns will accumulate more — the codified path is protocol-verified and rule-verified independently of sample size

## Recommendation

**Close the bug — verified end-to-end.** Both halves of the report are resolved with live evidence: the latency (89 s through a stripped phase via the codified direct channel, versus the multi-minute retry turns that prompted the report) and the "two instances" effect (one process, window-dedup rule, no Launch on attach). The upstream defect stays tracked on #148459; the lane no longer depends on its whims.
