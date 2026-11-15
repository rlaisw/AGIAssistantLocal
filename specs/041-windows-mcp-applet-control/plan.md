# Implementation Plan: Windows-MCP Applet Control (041)

## Summary

Enable the four applet-control tiers over the now-verified full Windows-MCP surface (21 tools live, FR-001 resolved during planning — the "4-tool" observation was a stale filtered instance, gone since the 2026-11-14 service restart). Each tier gets the gate class agreed in the spec: bounded launches (tier 1), a read-only allowlist (tier 2), the existing two-phase draft→confirm machinery with the extended never-list (tier 3), and the UI gate (tier 4, safe starter applets). The owner's explicit requirement: a test plan with **unit tests + end-to-end cases + error handling** is a first-class deliverable.

## Technical Context

**Language/Version**: Python 3.12 (sidecar stack); the host service is upstream Python (not modified by this feature — gates live on our side).

**Primary Dependencies**: the `agentic_rag_mcp.windows_mcp` lane module (spec 040, verified live), the full live tool surface (`App`, `PowerShell`, `Snapshot`, `Screenshot`, `Click`, `Type`, `Move`, `Scroll`, `Shortcut`, `Wait`, `WaitFor`, `DisplayInventory`, …), the existing gate machinery (`hermes_powershell_gate.py` never-list, `hermes_powershell_state.py` draft/confirm store, `hermes_run_gate.py` allowlist pattern), the shared `HermesAudit` funnel + loop gate, and the Dify Hermes Local Agent lane for routing.

**Storage**: existing draft/confirm SQLite store and audit trail; no new storage.

**Testing**: pytest unit pins + behavioral fakes (house style), live E2E harness per tier (`quickstart.md` = the owner-required test plan), error-handling cases at every tier.

**Target Platform**: sidecar container (:28080) → bridge (:18800) → Windows-MCP (:8800); the Windows desktop (interactive session required by the service).

**Project Type**: lane extension + gate wrappers + DSL routing (no new host service; no passthrough of the service's raw PowerShell to the chat).

**Performance Goals**: SC-006 — opens <15 s, reads <30 s, writes <60 s post-confirm; all inside the ~300 s turn budget.

**Constraints**: the anti-fabrication and consent contracts bind every tier; the never-list (extended with the remote-access-cutting class, firewall-rule boundary per the 2026-11-15 clarification) is enforced in OUR wrappers — the service itself has no such list; the service's USER_CONTROL deferral and interactive-desktop dependency are inherited; the container's bridge reach means the wrappers must be the ONLY chat-facing path (never register a raw passthrough of the service's `PowerShell` tool — destructiveHint=True, ungated).

**Scale/Scope**: 4 new sidecar tools (open / read / draft+confirm reuse / GUI flow), one never-list extension, ~5 DSL rules, 4 test classes + live harness.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **One runnable check per non-trivial behavior**: each tier's gate (ask-back, allowlist refusal, two-phase, never-list, credential ban, UAC stop, cascade re-confirm) gets a deterministic pin; live E2E per tier. PASS by design.
- **Measured, not assumed**: SC-001..006 are live-measurable; the 2026-11-15 surface probe supplies the baseline (21 tools; process listing ~0.6-1.5 s; opens expected ~2-5 s). PASS.
- **Lazy engineering**: tiers 2-3 reuse the existing allowlist/never-list/draft-confirm modules; the only new gate code is the UI-sequence confirmation and the remote-access never-list class. PASS.
- **Anti-fabrication**: no claim without the call; refusals verbatim; never-list binding at every tier incl. GUI clicks; no raw PowerShell passthrough. PASS.
- **Suite green before commit**: maintained. PASS.

**Gate verdict: PASS** (re-checked post-design: unchanged).

## Project Structure

Single-project layout. New/changed (implementation phase orientation):

- `src/agentic_rag_mcp/windows_mcp/` — tier wrappers: `open.py` (bounded launcher), `read_gate.py` (settings read allowlist, mirrors `hermes_run_gate.py`), `gui.py` (tier-4 sequence confirm + Click/Type/Wait orchestration), extension of `client.py` for the new tool calls; never-list additions in `hermes_powershell_gate.py` (remote-access class) and a GUI binding of the same list.
- `src/agentic_rag_mcp/server.py` — tool registrations: `windows_mcp_open_settings`, `windows_mcp_read_settings`, GUI tools per the two-phase pattern (draft surfaces the sequence; confirm executes stored text).
- `dify/AGIAssistant/AGI_Assistant.yml` — Hermes-lane routing rules per tier.
- `tests/unit/` + `tests/integration/` — per the test plan in `quickstart.md`.

Not changed: the Windows-MCP service (upstream), the bridge, tier-3's existing `hermes_run_powershell` execution channel (the tier-3 drafts execute through the existing gated machinery — the lane's GUI tier uses the service's input tools, never its raw PowerShell).

## Complexity Tracking

Moderate: four small gate modules + wrappers + routing + a dense test plan. No data model beyond confirmations/audit; the surface restoration prerequisite resolved itself (research R1).
