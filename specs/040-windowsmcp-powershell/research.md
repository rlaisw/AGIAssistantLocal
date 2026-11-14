# Research: Windows-MCP lane enablement (040)

Created: 2026-11-14. All findings below were verified LIVE against the running stack during planning — no assumptions.

## R1: The 400 Bad Request root cause — RESOLVED

**Decision**: lane requests through the bridge must carry the canonical `Host: 127.0.0.1:8800` header.

**Rationale / live evidence**:
- Every path on `http://172.17.0.1:18800/...` returned `400 | Invalid host header` (probed `/`, `/sse`, `/mcp`, `/messages`, `/health` — all identical).
- The WSL bridge (`services/wsl-bridge/bridge.py:31`) is a raw TCP forwarder `172.17.0.1:18800 → 127.0.0.1:8800`; it forwards bytes verbatim, so the client's `Host: 172.17.0.1:18800` reaches the service, which enforces a Host allowlist.
- With `Host: 127.0.0.1:8800` set: `GET /sse` → **200** with a proper MCP SSE handshake (`event: endpoint data: /messages/?session_id=…`); `/` and `/mcp` → 404 (the service serves SSE on `/sse` only).
- Full MCP handshake over the fixed transport succeeded: `initialize` OK, `tools/list` returned 4 tools.
- **E2E proof**: `Process {mode: "list", sort_by: "memory", limit: 5}` returned genuine host process data (vmmemWSL 19,023.8 MB top) in seconds, no consent prompt for the read-only listing.

**Alternatives considered**:
- Bridge-side Host rewrite — rejected: raw TCP forwarding must not parse/modify HTTP; a header-aware proxy is a new component for no gain.
- Host-side config to disable Host validation — rejected: Windows-side change, out of repo, weaker security posture.
- New port mapping without the bridge — rejected: the mirrored-network constraint makes Windows-loopback ports unbindable from WSL (established infrastructure fact); the bridge is the designed path.

## R2: The actual tool surface — captured live

**Decision**: document and wrap the four tools the service really exposes; the diagnostics acceptance case maps to the native `Process` tool, not a raw PowerShell tool.

**Rationale / live evidence** (`tools/list` on the fixed transport, 2026-11-14):
| Tool | Args (required) | Purpose |
|---|---|---|
| `Process` | mode (mode, name, pid, sort_by, limit, force) | list/kill running processes — the top-5 acceptance case |
| `Clipboard` | mode (mode, text) | copy/paste clipboard text |
| `Notification` | title, message, app_id | Windows toast notification |
| `Registry` | mode, path (mode, path, name, value, type) | registry read/write |

- No `PowerShell` tool exists on this service build. The spec name ("Windows-MCP PowerShell lane") keeps the historical intent; the implementation targets the real surface. The agent's gateway-side `mcp__WindowsMCP__PowerShell` path (spec 034 history) is a different connection and outside this feature's clarified scope (Option A).
- Read-only listings ran with no consent prompt; privileged operations (e.g. `Process mode=kill`, Registry writes) are expected to trigger the service's user-control consent — treated as host-owned behavior, verified as part of E2E error/consent cases rather than assumed.

## R3: Health-probe semantics — the bridge-mask lesson (2026-11-14, browser lane)

**Decision**: the lane's health probe must do an HTTP-level exchange through the bridge (any response = alive; connection reset/EOF/hang = down), exactly the pattern fixed in `browser_lanes/dynamic_health.py` this morning.

**Rationale**: a bare TCP connect to the bridge succeeds unconditionally while the far side may be dead — the false-positive this repo already fought once. The probe carries the same canonical Host header and the honest-unavailable envelope names the recovery (start the `windows-mcp-server` Scheduled Task — which exists, unlike the playwright saga).

## R4: Error handling expectations (owner's explicit requirement)

**Decision**: the lane wraps every failure class in a named honest envelope, unit-pinned + E2E-verified:
- service down → `error:windows-mcp-lane-unavailable` + recovery hint (start task), < 5 s;
- busy/consent-declined/timeout → named refusal, never fabricated output;
- tool error (service returns error text) → relayed verbatim;
- large output → bounded, truncation named (house rule).
All attempts audited through the shared `HermesAudit` funnel (operation class `windows-mcp-*`), which also feeds the loop-gate classification (operational class, non-exempt).

## R5: Test strategy (owner's explicit requirement)

**Decision**:
- **Unit**: string/contract pins (Host header present and canonical; envelope texts; probe-before-wrap ordering) + behavioral tests against a fake SSE server (accept-then-close → unavailable; responder → ok; header-dropped → 400 reproduced) + audit-row integration tests (mirror `test_loop_gate.py` / `test_dynamic_health.py` patterns).
- **E2E** (`quickstart.md`): top-5-process probe (the acceptance case, already proven live once), down-state honesty (stop task → envelope < 5 s → start task → works), genuine-error relay (an invalid tool call), large-output bounding, and a post-reboot durability check.
- **Error handling** is a first-class slice across both layers, per the owner's input.
