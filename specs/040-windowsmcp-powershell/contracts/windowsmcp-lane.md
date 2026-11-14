# Contract: the Windows-MCP lane (040)

Internal lane contract — how the sidecar stack talks to the Windows-MCP service. All details verified live 2026-11-14 (research.md R1/R2).

## Transport

- **Endpoint**: SSE MCP over the existing port bridge: `http://172.17.0.1:18800/sse` (bridge forwards raw TCP to `127.0.0.1:8800` on the Windows host).
- **Host header (the fix)**: every request MUST carry `Host: 127.0.0.1:8800`. Without it the service rejects with `400 Invalid host header` (it enforces a Host allowlist; the bridge forwards the header verbatim). This header is part of the lane's contract and unit-pinned.
- **MCP protocol**: standard SSE transport — `initialize`, `tools/list`, `tools/call`. Session lifecycle handled by the MCP client (endpoint event carries the `/messages/?session_id=…` callback).

## Tool surface (captured from the live service)

| Tool | Required args | Full args |
|---|---|---|
| `Process` | mode | mode, name, pid, sort_by, limit, force |
| `Clipboard` | mode | mode, text |
| `Notification` | title, message, app_id | (same) |
| `Registry` | mode, path | mode, path, name, value, type |

The lane validates args against these schemas before dispatch (invalid shape → blocked envelope, no service call).

## Health probe (FR-002)

- HTTP-level through the bridge with the canonical Host header: any HTTP response = reachable; reset/EOF/timeout (2 s budget) = down with the honest envelope.
- The envelope names the real recovery: start the `windows-mcp-server` Scheduled Task (`schtasks /run /tn windows-mcp-server`) — the task exists on the host (verified).

## Honest envelopes (FR-006, error handling contract)

| Condition | Envelope |
|---|---|
| service unreachable / reset | `error:windows-mcp-lane-unavailable — the Windows-MCP service (http://172.17.0.1:18800) is unreachable (…); recover with schtasks /run /tn windows-mcp-server` |
| consent declined / timed out | `blocked: the host did not approve execution — nothing ran; no retry without the owner` |
| invalid args | `blocked: <named violation>` (no service call) |
| service-reported tool error | genuine error text relayed verbatim under `error:windows-mcp-tool-error — <service text>` |
| large output | bounded, truncation named (house rule) |

## Audit contract (FR-004)

Every attempt goes through the shared `HermesAudit` funnel: operation `windows-mcp-<tool>` (`windows-mcp-status` for health checks), decision executed/blocked/error, conversation_id always present, duration_s, reason/outcome bounded. Append-only; never rewritten. The funnel also classifies the conversation for the loop gate (operational, non-exempt class) — no extra wiring needed.

## Out of contract (clarified Option A)

No new chat-facing tool surface, no DSL/routing changes, no host-side service changes, no bridge changes.
