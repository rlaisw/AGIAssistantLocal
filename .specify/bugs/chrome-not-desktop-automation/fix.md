# Bug Fix: Browser lanes unusable — service, registry, dynamic tool, and the container-reachability class

- **Slug**: chrome-not-desktop-automation
- **Fixed**: 2026-11-11T09:11:15Z
- **Assessment**: ./assessment.md
- **Status**: applied (with one scope expansion: the container-reachability class — see Deviations)

## Summary

All three assessed gaps closed — the dead `:3002` service restarted, the scripted registry mounted into the container, and the missing `browser_dynamic_task` sidecar tool built and wired — plus a **fourth, deeper gap** the live testing exposed: the sidecar container cannot reach ANY Windows-loopback service (the same flaw latent in spec-038's task-gateway client), fixed with a WSL docker0 port bridge. **End-to-end live proof: the verbatim weather scenario now returns real observed weather (Bing, Hong Kong 23°C sunny) with `BROWSE: COMPLETED`.**

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | `BROWSER_DYNAMIC_INSTRUCTIONS` — the Hermes-side dynamic-browsing prompt: step-by-step mcp__PlaywrightMCP__* use, observations only, UNTRUSTED-CONTENT LAW verbatim, BROWSE: COMPLETED/FAILED attestation |
| `src/agentic_rag_mcp/server.py` | modified | new `browser_dynamic_task` tool (probe-first → honest unavailable envelope → hermes directive → verdict from the BROWSE marker, never prose) + both browser tools probe via cfg (bridge host/port) |
| `src/agentic_rag_mcp/deploy/docker_ops.py` | modified | `_BROWSER_SCRIPTS_MOUNT` ("scripts/browser" → /usr/local/scripts/browser) — the registry ships like ppt-master |
| `src/agentic_rag_mcp/config.py` | modified | `browser_mcp_host/port` (172.17.0.1:13002 via the bridge), `task_gateway_url` → :18080 |
| `services/wsl-bridge/bridge.py` | added | the docker0 port bridge (asyncio TCP forwarder, shifted ports — mirrored networking forbids re-binding Windows-held ports) |
| `~/.config/systemd/user/wsl-port-bridge.service` | added (host) | user service, no sudo, Restart=always — bridges 172.17.0.1:{13002→3002, 18080→8080} |
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | `browser_dynamic_task` on the Hermes lane + the dynamic-lane instruction now names the tool |
| `tests/unit/test_browser_scripted_run.py` | added 3 tests | probe-down honest envelope (zero executed rows), completed relay + audit, missing-marker-is-failure |
| `tests/unit/test_deploy_docker_ops.py` | modified | mount pin 5→6 with the scripts mount asserted |
| `tests/integration/test_browser_a2.py` | modified | the dynamic tool joins the A2 allowed scope |

## Tests Added or Updated

- `TestDynamicTaskTool::test_probe_down_honest_envelope_no_hermes_call` — down lane → error envelope, audit row, nothing executed
- `TestDynamicTaskTool::test_completed_relay_and_audit` — BROWSE: COMPLETED → ok + observed content + executed audit row
- `TestDynamicTaskTool::test_missing_marker_is_failure_never_ok` — prose without the attestation never passes (the 029 FR-007 lesson)
- Mount pin: 6 mounts incl. `scripts/browser:/usr/local/scripts/browser`

## Local Verification

- `pytest tests/unit/` → **562 passed** (full regression)
- Service: `schtasks /run /tn playwright-mcp-server` → `:3002` SSE live (Status: Ready after its earlier death — see Follow-ups)
- Bridge: `systemctl --user is-active wsl-port-bridge` → active; container reachability matrix: `172.17.0.1:{13002,18080}` REACHABLE (3002/8080/8642-at-127.0.0.1 all refused — the class proof)
- Container: registry shows all 3 starter scripts; 40 tools synced
- **THE LIVE PROOF**: `browser_dynamic_task("…what is hong kong weather today…")` → `status: ok, verdict: completed` with the real Bing weather report (23°C sunny, fire warning, forecast) — the verbatim morning-bug scenario, working end-to-end

## Deviations from Assessment

**Scope expansion — the container-reachability class (gap #4)**: live testing after parts 1–3 showed the probe still failing from an UP server: the sidecar container cannot reach Windows-loopback services at any address (only WSL-host services like the Hermes gateway at 172.17.0.1:8642 answer). This also silently afflicted spec-038's task-gateway client (`task_gateway_url` pointed at an unreachable address). Fixed with the `wsl-bridge` user service: docker0 listeners on **shifted ports** (13002/18080 — mirrored networking makes Windows-held ports unbindable in WSL on any interface, the EADDRINUSE discovery) forwarding to WSL loopback → Windows mirrored loopback. Zero new Windows-side exposure (all Windows services stay on 127.0.0.1); the only new listeners are on the container network. The 038 config default moved to :18080 in the same change.

## Follow-ups

- **watch the playwright-mcp-server death**: the task died once today (RestartOnFailure does not fire on clean exits); the bridge adds no keep-alive for it — if it recurs, consider a Windows-side watchdog or making the task a loop-wrapper.
- The bridge service is host state — document it in DEPLOY.md's host-prereqs on the next doc pass.
- Full battery (`deploy verify`) at a future window for the formal record — expected: 15/15 incl. X1 green for the first time.
- The owner's chat-path re-test (send the weather prompt in the Chat UI) is the final user-visible confirmation; the tool-level path is proven above.