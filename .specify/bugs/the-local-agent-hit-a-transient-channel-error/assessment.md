# Bug Assessment: retries take minutes and Outlook windows multiply — but the agent already invented the real fix (browser-based direct MCP)

- **Slug**: `the-local-agent-hit-a-transient-channel-error`
- **Created**: 2026-11-05T09:35+00:00
- **Source**: pasted text (chat transcript of the successful-but-slow email request + "it takes long time and open two Outlook instance / Finally, it created the new email in Draft folder")
- **Verdict**: valid — the flow works end-to-end; the report targets two UX defects in the working mitigation, and the evidence inside this very turn reveals the high-value fix
- **Severity**: low (latency and window clutter on a succeeding flow) — but the remediation unlocks a large reliability/latency gain

## Report (verbatim or summarized)

> "it takes long time and open two Outlook instance. Finally, it created the new email in Draft folder"

The user's email request (body "Outlook test abc version 11", subject "Outlook hello test version 11") took three tool attempts over ~2.5 minutes (plus chat overhead): attempts 1–2 burned their 15-canary budgets on the stripped gateway channel, attempt 3 delivered, composed, and verified the draft. The user reports a long wait and "two Outlook instances".

## Symptom

The email compose succeeds, but a turn overlapping a stripped channel phase costs minutes of canary retries, and the turn-by-turn "show the result" steps open additional Outlook folder windows that read as extra Outlook instances. Expected: a fast turn and one Outlook view.

## Reproduction (all evidenced, 2026-11-05 UTC)

1. 09:28:37 — attempt 1: RunningApps OK (Outlook running, no launch) → probe/attach FAILED: 15 canaries echoed, channel never healed
2. 09:29:45 — attempt 2: RunningApps OK (no second launch) → compose FAILED: 15 more canaries echoed
3. 09:30:54 — attempt 3: **succeeded** — and the args-capture log shows how: `'canary-direct-sse-browser-20261105-01'`, `'canary-sse-77'` — canaries delivered with arguments **through a browser-based direct MCP channel** to `http://127.0.0.1:8888/sse` (reachable from the gateway host via WSL mirrored loopback), then the real COM code (`pythoncom`/`win32com` with the EntryID verification) arrived the same way. Attach via GetActiveObject, **no Launch used**, draft created and verified, nothing sent.
4. **No second Outlook instance exists**: tasklist shows exactly one OUTLOOK.EXE throughout; every attempt's audit line confirms no Launch. What the user saw was Outlook **windows**: the "leave the app showing the result" Display steps from consecutive turns (09:25 and 09:30) each open an additional Drafts explorer window inside the single Outlook instance.

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_client.py` — `OFFICE_INSTRUCTIONS`: the SESSION-DEGRADATION RULE offers only canary retry or give-up; the agent's proven **browser-based direct MCP path** (evidence above) is not codified, so turns re-invent it or don't find it, paying minutes of canary tax. Also: the "leave the application open showing the result" rule has no window-dedup ("do not open another folder window when the result is already displayed").
- The hermes agent's browser/fetch tooling — the working bypass: it can hold the SSE handshake and POST MCP messages to `http://127.0.0.1:8888/sse` with full arguments while the gateway's own MCP client is stripped (hermes-agent #148459).
- `.specify/bugs/local-agent-failed/test.md` annotation — says the "direct-SSE fallback" was embellishment; **partially wrong**: the fallback is real via the browser tool (this turn's canary names prove it); some earlier deliveries were burst breakthroughs, this one was the browser channel. The annotation should be corrected in this cycle.

## Root Cause Hypothesis

**High confidence.** (1) Latency: the mitigation's only sanctioned strategy against the oscillating upstream strip is in-turn canary retry — which pays the oscillation tax on every stripped-phase turn even though the agent demonstrably owns a reliable bypass (browser-based direct MCP with arguments intact). (2) "Two instances": consecutive turns' Display steps each open a new Drafts explorer window in the one real Outlook process; there is no second process (verified) — a window-dedup instruction is missing.

## Proposed Remediation

**Preferred**: codify what the agent already invented, and stop opening windows. (1) Extend the SESSION-DEGRADATION RULE with an official **direct-channel fallback step**: after 2–3 canaries echo, stop canary-retrying and drive the task steps over the direct MCP channel — browser/fetch to `http://127.0.0.1:8888/sse` (SSE handshake → POST JSON-RPC to the returned `/messages/?session_id=…` endpoint; every tool call carries full arguments there). This collapses multi-minute retry turns to seconds and removes dependence on the oscillation entirely — it is the lane-side durable fix, discovered by the agent itself. (2) Add window-dedup to the display rule: "if Outlook already shows the result, do not open another folder window — reuse the existing view." (3) Correct the `local-agent-failed` annotation (the fallback is real, via the browser tool). (4) Add the browser-channel evidence to the hermes-agent #148459 drafts — the gateway's own MCP client drops arguments while an ordinary HTTP client on the same host delivers them, isolating the defect to the client's serialization beyond doubt.

**Alternatives**:
- WSL-side relay + gateway-independent executor (the earlier endgame) — now largely superseded: the browser path already crosses the container/Windows boundary with no new infrastructure; the relay is only worth building if the browser channel proves flaky in battery runs
- Reduce the canary cap again — rejected: canaries are the detector for when to switch to the direct channel, not the recovery

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_client.py` — direct-channel fallback step + display window-dedup
- `tests/unit/test_hermes_office_tool.py` — guard updates
- `.specify/bugs/local-agent-failed/test.md` — annotation correction (append, not rewrite)

**Tests to add or update**:
- Guard test: instructions contain the direct-channel step (the `:8888/sse` endpoint, the switch condition "after 2–3 canaries", "browser or fetch tool") and the window-dedup rule

## Risks & Considerations

- Codifying the browser channel blesses an improvised behavior; the instruction must pin the exact protocol (endpoint, handshake, message POST shape) so turns stop re-inventing it with varying success
- The browser channel depends on WSL mirrored loopback (`127.0.0.1:8888`) staying reachable from the gateway host — a topology change (networking mode) would need the relay alternative
- OfficeMCP sees direct-channel calls as normal MCP traffic — the audit trail (sidecar-side) and the arg-capture log still record everything; no observability loss
- Latency of the *current* flow is already acceptable when turns overlap a healthy phase; this fix removes the stripped-phase penalty specifically

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the browser-channel evidence is conclusive for this turn; the fix command should verify it once more in a live compose before closing]
