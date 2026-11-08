# Bug Verification: comma-list "open chrome, …, type …" executes end-to-end — refusal gone, followup completes

- **Slug**: `typing-search-is-gui-automation-that-the-local-agent-cant-perform`
- **Tested**: 2026-11-08T02:02+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original symptom — the chat refusing "open chrome, open a new tab, type www.google.com, type hong kong hang seng index at search" as "GUI automation the local agent can't perform" — no longer reproduces: the full comma-list request now executes end-to-end with every step verified by screenshot (new tab → google.com → the search phrase typed into Google's search box). The fix's blocker (disconnected Windows session) cleared after reconnect, and the one stale-connection retry it needed is documented below.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Environment precondition | `qwinsta` + WindowsMCP task start + ControlStatus probe | **pass** | Session now **Active** (RDP); scheduled task started; `ControlStatus: {"state":"ready","generation":1}` — healthy |
| Reproduction (post-fix) — the exact comma-list | live `hermes_launch_app("open chrome, open a new tab, type www.google.com, type hong kong hang seng index at search")` | **pass** | `status ok` — *"Desktop followup, all verified by screenshot: 1. Opened a new tab with Ctrl+T. 2. Typed www.google.com in the address bar and navigated — google.com homepage loaded. 3. Typed 'hong kong hang seng index' into the Google search box — text confirmed in the field"* (left unsubmitted, correctly — only typing was requested); 207 s |
| Intermediate run (environmental retry) | same request, first attempt post-reconnect | pass with note | Gate+prompt worked (no refusal, followup attempted); the agent's WindowsMCP session was stale from the 2-day downtime → `hermes mcp test WindowsMCP` refreshed it (21 tools) → retry passed. The agent's honest fallback report during the stale window (PowerShell route held for consent, never run) proved the honesty rules too |
| New / updated tests | `pytest tests/unit` | **pass** | **341 passed** (incl. the 4 comma-list gate tests) |
| Lint | `ruff check src/agentic_rag_mcp/hermes_launch_gate.py` | **pass** | clean |

## Output Excerpts

```
ControlStatus: {"state":"ready","generation":1,"wait_seconds":0.0}
live comma-list: "…Desktop followup, all verified by screenshot: 1. Opened
  a new tab with Ctrl+T. 2. Typed www.google.com… navigated — google.com
  homepage loaded in the new tab. 3. Typed 'hong kong hang seng index'
  into the Google search box…" → status ok — 207 s
pytest tests/unit → 341 passed
```

## Residual Risks

- WindowsMCP 0.8.8 still cannot survive a **disconnected** session (control machinery hard-requires an Active session; no 0.8.8 config escape) — after any disconnect/reconnect cycle the server may need `./reboot.sh` or `Start-ScheduledTask` to come back, and the gateway's tool session may need one `hermes mcp test WindowsMCP` refresh (observed this run); worth adding to the runbook's disconnect-recovery notes
- The agent noted intermittent **UIA staleness** mid-task (empty window list while screenshots were fine) — it recovered; if it recurs, the `WINDOWS_MCP_EXCLUDE_PROCESSES` mitigation from the README is the knob
- The agent typed into Google's **search box** rather than the address bar for step 3 (both match the request's intent; noting the interpretation)
- Multi-step desktop turns take 3–6 minutes (desktop-control idle waits + LLM iterations) — the known latency floor; the search-phrase was correctly left unsubmitted since only typing was requested

## Recommendation

**Close the bug — verified end-to-end.** The exact four-clause request from the report now runs to completion with per-step screenshot verification; the gate unit matrix and the full suite hold; and the environmental blocker's recovery path (reconnect → start task → refresh gateway session) is documented for the runbook. No further cycle needed for this bug.