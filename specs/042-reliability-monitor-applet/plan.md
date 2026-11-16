# Implementation Plan: Reliability Monitor applet (042)

## Summary

Add the Reliability Monitor ("reliability monitor" / "reliability history" / "stability monitor") as a new target on the proven tier-1 open surface. The launch uses the live-verified per-host form `Start-Process mmc.exe -ArgumentList 'perfmon.msc','/rel'` — plain `perfmon.exe /rel` is the newest silent-die case on this Windows build (exits instantly from the service's context, no window, no crash event), resolved by planning-phase A/B exactly as the device-manager case was. Everything else — the bounded target list, ask-backs, audit, honest envelopes — is inherited unchanged from the 34-surface-verified open tier.

## Technical Context

**Language/Version**: Python 3.12 (sidecar stack); no host-side changes.

**Primary Dependencies**: the existing `windows_mcp` lane (`targets.py` inventory, `open.py` launcher, the `PowerShell` tool path on the live 21-tool service), the shared `HermesAudit` funnel, the existing unit batteries.

**Storage**: N/A — stateless; audit rows land in the existing trail under `windows-mcp-open`.

**Testing**: pytest unit pins (target resolution + the launch form) + one live E2E (open → "Performance Monitor" mmc window in session 1). Tests-first in the implement phase per the house pattern.

**Target Platform**: sidecar container → bridge → the Windows-MCP service; the owner's interactive desktop.

**Project Type**: one-entry extension of an existing lane — no new tool, no DSL rule change (the APPLETS tier-1 rule already covers "any name on the reviewed target list").

**Performance Goals**: opens < 15 s desktop-quiet (the sweep baseline for every applet); the reliability chart itself fills over seconds after the window opens — never claimed as ready.

**Constraints**: the per-host launch-form lesson (research R1) — never assume the owner's named command (`perfmon /rel`) survives the service's context; A/B first. The inherited honesty contracts bind unchanged.

**Scale/Scope**: 1 target entry + 3 synonyms, 1 launch form, 2 unit pins, 1 live E2E.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **One runnable check per non-trivial behavior**: the launch form is A/B-verified live before pinning (R1), the target resolution pinned, the live E2E proves the window. PASS.
- **Measured, not assumed**: the A/B evidence is recorded with PIDs and window titles; SC-001 rides the sweep baseline. PASS.
- **Lazy engineering**: one inventory entry + one launcher branch — the shortest working diff that closes the ask. PASS.
- **Anti-fabrication**: inherited contracts unchanged; the chart-fills-later edge is documented so the relay never claims data readiness. PASS.
- **Suite green before commit**: maintained. PASS.

**Gate verdict: PASS** (re-checked post-design: unchanged).

## Project Structure

Single-project layout. Changed files (implementation orientation):

- `src/agentic_rag_mcp/windows_mcp/targets.py` — the reliability-monitor entry + synonyms in the reviewed inventory.
- `src/agentic_rag_mcp/windows_mcp/open.py` — the per-host launch form for the perfmon.msc/rel target (alongside the existing `.msc` direct and `.cpl` forms).
- `tests/unit/test_windows_mcp_applets.py` — resolution pins + the launch-form pin.

Not changed: server.py (no new tool), the DSL (the tier-1 rule covers the new target by construction), the gates, the service.

## Complexity Tracking

Minimal: a one-entry inventory extension with one live-verified launch branch and two pins — the smallest complete change on a lane proven across 34 surfaces and two bug lifecycles.
