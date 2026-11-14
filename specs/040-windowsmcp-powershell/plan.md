# Implementation Plan: Windows-MCP lane enablement (040)

## Summary

Repair and harden the Windows-MCP lane so the agent stack can execute consented host-side operations through it. The transport root cause is already isolated and verified live: the Windows-MCP service enforces an HTTP `Host` header allowlist, and the raw TCP port bridge forwards the client's original `Host: 172.17.0.1:18800` verbatim → the service rejects every request with `400 Invalid host header`. Setting the canonical `Host: 127.0.0.1:8800` on lane requests restores the full chain (verified live 2026-11-14: SSE handshake 200, `tools/list` OK, and a real `Process` top-5-by-memory call returned genuine output). The implementation packages this as a durable, tested client surface in the sidecar with honest envelopes, a truthful health probe, and the audit integration the other lanes have — per the clarified scope (Option A: channel repair; no new chat tool).

## Technical Context

**Language/Version**: Python 3.12 (sidecar stack; WSL Ubuntu-24.04 container side, Windows host service untouched).

**Primary Dependencies**: existing `mcp` python client (SSE transport), `httpx` (already used by every lane), the WSL port bridge (`services/wsl-bridge/bridge.py`, mapping `172.17.0.1:18800 → 127.0.0.1:8800`), the shared `HermesAudit` funnel, and the existing lane-pattern modules (`browser_lanes/dynamic_health.py` as the honest-probe template).

**Storage**: N/A (stateless client; audit rows append to the existing `~/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl` via the shared funnel).

**Testing**: pytest unit pins (string-level contract pins per house style + behavioral unit tests with a fake SSE server), plus the live end-to-end scenarios in `quickstart.md`. The owner's explicit expectation for this feature: **unit tests + end-to-end test cases + error handling** — all three are first-class deliverables.

**Target Platform**: sidecar container (`agentic-rag`, :28080) reaching the Windows host service (Windows-MCP on `127.0.0.1:8800`) through the bridge at `172.17.0.1:18800`.

**Project Type**: internal lane module + client (no new host service, no DSL change, no new chat tool — clarified Option A).

**Performance Goals**: read-only command round-trip (e.g. top-5 processes) < 30 s per SC-001 (measured live: seconds); honest failure < 5 s per SC-002 when the host service is down.

**Constraints**: never fabricate output (anti-fabrication law); consent-gated host writes (the service's own user-control); audit every attempt; the health probe must measure the far side, not the bridge (the browser-lane lesson, 2026-11-14); 300 s turn budget respected.

**Scale/Scope**: single service, four tools (`Process`, `Clipboard`, `Notification`, `Registry` — schemas captured live 2026-11-14); one client module; ~4 unit test classes; ~5 E2E scenarios.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Tests before/at implementation**: satisfied by design — every non-trivial behavior (host-header contract, probe honesty, envelope shapes, audit funnel integration) gets one deterministic unit pin; E2E cases run in `quickstart.md`. (Principle: one runnable check per non-trivial behavior.)
- **Measured, not assumed, performance**: SC-001/SC-002 are measured against the live service (the 2026-11-14 probes already supply the baseline: handshake <1 s, Process call seconds).
- **Lazy engineering / shortest working diff**: the fix is a client-side header plus a small durable client module reusing existing patterns (audit funnel, honest-probe template) — no bridge rewrite, no host-side change, no new chat surface.
- **Anti-fabrication**: relayed output is the service's genuine text; failures surface verbatim; the honesty contract is pinned by tests.
- **No raw HTTP tool outside gates**: the lane is an internal execution channel with the service's own consent flow for privileged operations; read-only listings are the acceptance slice. (Spec 035 laws respected.)

**Gate verdict: PASS** — no violations; re-checked after Phase 1 below (unchanged).

## Project Structure

Single-project layout (sidecar repo). New/changed files (implementation phase, for orientation only — exact tasks come from `tasks.md`):

- `src/agentic_rag_mcp/windows_mcp/` — the lane client module (connection with the canonical Host header, tool-call wrappers, honest envelopes, health probe).
- `tests/unit/test_windows_mcp_lane.py` — unit pins + behavioral tests (fake SSE server: accept-then-close/masked states, envelope shapes, host-header contract, audit rows).
- `tests/integration/` — live E2E harness per `quickstart.md` (top-5 probe, down-state honesty, error handling), following the existing browser-lane harness pattern.
- No changes: `services/wsl-bridge/`, the Windows host service, the DSL, the tool count surfaced to Dify.

## Complexity Tracking

Simple, single-lane enablement: one client module + tests + live verification. No data model beyond audit rows; no external interface beyond the internal lane contract documented in `contracts/windowsmcp-lane.md`.
