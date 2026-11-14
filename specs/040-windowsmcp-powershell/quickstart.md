# Quickstart: validate the Windows-MCP lane (040)

Runnable validation scenarios that prove the feature end-to-end. Every scenario is expected to pass on a healthy stack with the implementation in place; the first one has already been demonstrated live during planning (2026-11-14) with the raw fixed-transport probe.

## Prerequisites

- Sidecar container running (`agentic-rag` :28080), WSL bridge active (`systemctl --user is-active wsl-port-bridge.service` → active).
- Windows-MCP service up: `schtasks /query /tn windows-mcp-server` → Ready (auto-starts at logon).
- The venv: `.venv/bin/python`.

## E2E-1: the acceptance case — top-5 processes (SC-001)

Run the lane's process listing (unit of work: one lane call, `Process mode=list sort_by=memory limit=5`).
Expected: genuine host process table (top row historically `vmmemWSL`, ~19 GB) relayed verbatim, round-trip **< 30 s** (baseline measured: seconds). Read-only — no consent prompt expected (verified live 2026-11-14).

## E2E-2: honest down-state (SC-002)

Stop the host service (`schtasks /end /tn windows-mcp-server`), then run E2E-1's request again.
Expected: the `error:windows-mcp-lane-unavailable` envelope with the recovery hint, in **< 5 s**; then `schtasks /run /tn windows-mcp-server` and confirm E2E-1 passes again. (Do not leave the service stopped.)

## E2E-3: genuine error relayed (error handling)

Call with an invalid tool argument shape (e.g. `Process mode=list limit="not-a-number"` — the lane blocks locally) and a service-side error (e.g. a nonexistent Registry path read).
Expected: blocked envelope for the local validation (no service call), and the service's genuine error text relayed verbatim for the service-side failure — never "success".

## E2E-4: output bounding (error handling)

Request a listing large enough to exceed the bound (e.g. limit at the service's maximum).
Expected: bounded output with the truncation named honestly in the relay.

## E2E-5: post-reboot durability (SC-003)

After a host reboot + logon (no manual reconfiguration), run E2E-1.
Expected: passes. Check the audit trail for `windows-mcp-process` rows with `decision: executed`.

## Unit tests (run all, expect green)

```
.venv/bin/python -m pytest tests/unit/test_windows_mcp_lane.py -q
.venv/bin/python -m pytest tests/unit -q        # full suite stays green
```

Pinned contracts: the canonical Host header on every lane request (the 400-fix), the honest-unavailable envelope text + recovery hint, probe-before-envelope ordering (no fabricated reachable — the browser-lane lesson), args validation before dispatch, audit rows (operation/decision/conversation_id) through the shared funnel, and the fake-SSE behavioral cases (accept-then-close → unavailable; responder → ok; missing Host header → the 400 reproduced).

## Audit verification

```
grep 'windows-mcp' ~/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl | tail
```
Expected: one row per attempt with the correct decision class; refusals and errors present alongside successes.
