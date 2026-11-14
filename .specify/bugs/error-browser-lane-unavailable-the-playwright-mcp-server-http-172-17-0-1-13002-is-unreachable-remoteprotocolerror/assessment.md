# Bug Assessment: browser lane down with a broken recovery hint and a false-positive health probe

- **Slug**: error-browser-lane-unavailable-the-playwright-mcp-server-http-172-17-0-1-13002-is-unreachable-remoteprotocolerror
- **Created**: 2026-11-14T05:25:00+00:00
- **Source**: pasted text (the chat's honest-unavailable envelope, verbatim)
- **Verdict**: valid — reproduced live during assessment; three distinct defects confirmed
- **Severity**: high — both browser lanes (dynamic and scripted) are dead until manual Windows-side action, the documented recovery command fails, and the health tool falsely reports the lane reachable

## Report (verbatim or summarized)

> "error:browser-lane-unavailable — the Playwright MCP server (http://172.17.0.1:13002) is unreachable (RemoteProtocolError); recover with start the Scheduled Task: schtasks /run /tn playwright-mcp-server"

No URL was supplied with the report. (The URL embedded in the pasted error text is the lane's own bridge endpoint, not a fetched source.)

## Symptom

Any browser task through the container fails instantly (0.0 s) with the honest-unavailable envelope naming RemoteProtocolError on the WSL bridge endpoint (172.17.0.1:13002); the envelope's recovery command (`schtasks /run /tn playwright-mcp-server`) then also fails, because that Scheduled Task does not exist on the Windows host. Meanwhile `browser_status` — the designed honest health check — reports the lane as `reachable: true`, contradicting the real state.

## Reproduction

1. **Live reproduction (performed during assessment, 2026-11-14T05:15:55Z)**: `browser_navigate_v2("https://example.com")` through the sidecar → instant `error:browser-lane-unavailable … (RemoteProtocolError)` envelope; audit row written (`operation: browser-navigate-v2`, `duration_s: 0.0`).
2. **Windows side**: `netstat -ano` (via WSL interop) shows **no listener on :3002** — the Playwright MCP engine is down; 51 other LISTENING ports confirm the query itself works.
3. **The recovery hint is broken**: `schtasks /query /tn playwright-mcp-server` → `ERROR: The system cannot find the file specified.` — the task is not registered. The non-Microsoft task inventory on the host lists only `officemcp-server`, `windows-mcp-server`, `task-gateway-service` — our stack's other three services have Logon Tasks; the Playwright task is missing (the known register/import saga of 2026-11-13 never converged).
4. **The health check lies**: `browser_status` (same moment as step 1) returned `status: ok, dynamic.reachable: true` — because the probe is a bare TCP connect to the WSL bridge (:13002), which accepts connections unconditionally regardless of the far side's state.
5. History in the audit trail: 4 prior rows before this assessment (2× 2026-11-11 setup-era `browser-dynamic`, 1× 2026-11-12 `v2-maximize-test`, 1× 2026-11-14T05:12:28 `browser-navigate-v2` — the live user turn that prompted this report) plus the assessment's own reproduction row. The engine had been up as a long-lived leftover process since at least 2026-11-13's probes and died before 05:12:28Z today with nothing to restart it.

## Suspected Code Paths

- `src/agentic_rag_mcp/browser_lanes/dynamic_health.py:15-31` — `probe_dynamic()` does `socket.create_connection((host, port))` only; when invoked with the bridge address (172.17.0.1:13002) it measures the bridge, not the engine — a dead far side still yields `reachable: true` (violates the module's own "never a fabricated reachable" contract). The `RemoteProtocolError` class name in the envelope comes from the real MCP HTTP exchange (proxy path), not from this probe.
- `src/agentic_rag_mcp/browser_lanes/proxy.py:28` — the same envelope text and recovery hint on the proxy path (this side is honest and correct; its envelope is what the user saw).
- `src/agentic_rag_mcp/server.py` (`browser_status` tool) — passes the bridge URL into `probe_dynamic`, inheriting the false positive.
- `windows/playwright-mcp-task.xml`, `windows/playwright-mcp-launcher.pyw` — the intended Logon Task and launcher (`--isolated`); the task XML exists in the repo but was never successfully registered on the host (prior "task XML is malformed" import failure; `Register-ScheduledTask` run reported OK but `Export-ScheduledTask` showed a stale action; the task is now absent entirely).
- `services/wsl-bridge/bridge.py` — the TCP forwarder whose unconditional accept is what makes the bare-TCP probe meaningless for far-side health (the bridge itself is healthy and active; not at fault).

## Root Cause Hypothesis

**High confidence, three-part.** (1) *Operational*: the Playwright MCP engine has no durable host-side lifecycle — the `playwright-mcp-server` Scheduled Task was never successfully registered, so the engine runs only as a manually-started leftover process; when it dies (as it did before 05:12:28Z today) nothing restarts it, and both browser lanes go down. (2) *Code*: the recovery hint hard-codes `schtasks /run /tn playwright-mcp-server` — currently a nonexistent task — so the documented recovery fails exactly when it is needed. (3) *Code*: `probe_dynamic` health-checks the wrong layer (bare TCP to the bridge, which accepts unconditionally), so `browser_status` reports `reachable: true` while the engine is dead — a false positive that misleads diagnosis. All three were confirmed live during this assessment.

## Proposed Remediation

**Preferred** (three coordinated parts):
1. *Register the task for real (Windows-side, operational)*: register `windows/playwright-mcp-task.xml` via `Register-ScheduledTask -Xml` (elevated), then verify with `schtasks /query /tn playwright-mcp-server`, start it, and confirm `netstat :3002 LISTENING` plus a live `browser_navigate_v2` round-trip. This makes the envelope's recovery command true and gives the engine logon auto-start.
2. *Fix the health probe*: make `probe_dynamic()` do an HTTP-level exchange (short-timeout `httpx.get` against the base URL — any HTTP response, including 404, proves the engine is alive; a dead far side yields EOF/RemoteProtocolError through the bridge) instead of a bare TCP connect to the bridge. Keep the 2 s never-hang budget; keep the honest envelope text and FR-011 contract.
3. *Pin both*: unit tests that (a) a TCP-accept-but-HTTP-dead endpoint reports `reachable: false` with the envelope (the exact bridge-mask failure mode), (b) a responding endpoint reports ok, and (c) the recovery text names the task that the registration step creates.

**Alternatives**:
- Probe the engine directly from a Windows-side vantage (task-gateway health command) instead of through the bridge — more moving parts, no benefit over the HTTP-through-bridge probe.
- Teach the agent to offer running the recovery itself via the PowerShell lane (two-phase confirm) — a nice self-service enhancement, but pointless until the task actually exists; treat as a follow-up, not this fix.

**Files likely to change**:
- `src/agentic_rag_mcp/browser_lanes/dynamic_health.py` (probe semantics)
- `tests/unit/` (health-probe pins; likely `test_browser_control_v2.py` or a new `test_dynamic_health.py`)
- Windows-side registration actions (no repo file change expected; `windows/playwright-mcp-task.xml` stays as the source of truth)

**Tests to add or update**:
- `probe_dynamic` against a socket that accepts but never speaks (the bridge-mask mode) → must return the unavailable envelope, not ok.
- `probe_dynamic` against a minimal HTTP responder → ok.
- Envelope text pin: recovery hint names `playwright-mcp-server`.

## Risks & Considerations

- The HTTP-level probe must never hang: a live SSE server can hold connections open — probe the base URL (not `/sse`) with a hard 2 s timeout and treat any HTTP status as proof of life.
- Task registration needs an elevated PowerShell (UAC); the prior import path (`schtasks /create /xml`) hit a malformed-XML rejection — use the cmdlet and verify by live export/query, not by the cmdlet's own success message.
- The engine must keep `--isolated` in its action (the upstream session-latch workaround); a re-registration with a stale action would trade this bug for the old one.
- The bridge and the other three lanes are healthy — do not touch them; blast radius of the code change is only the health probe and its tests.
- Sidecar rebuild + re-publish not required for the task registration, but the probe change ships in the sidecar image (redeploy needed).

## Open Questions

- [NEEDS CLARIFICATION: none blocking — all three defects are confirmed live. The exact moment/cause of the engine process death (crash vs. reboot vs. manual close) is unknowable from WSL and does not change the fix.]
