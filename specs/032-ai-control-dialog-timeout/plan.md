# Implementation Plan: AI Control Dialog Timeout

**Branch**: `032-ai-control-dialog-timeout` | **Date**: 2026-11-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/032-ai-control-dialog-timeout/spec.md`

## Summary

Shorten the on-screen "AI is controlling this computer" notice so it clears within ~3 seconds of the AI's last desktop action (previously it lingers up to ~15 s via the control-lease tail). The notice is a bitmap inside the WindowsMCP control overlay (no dialog timer exists in the installed 0.8.8), so the change is a **local patch of the installed service's lease-tail constant** (`15.0 → 3.0`) — leaving the 10-second user-revert/wait-for-idle window and all takeover mechanics untouched per the owner's clarifications.

## Technical Context

**Language/Version**: Python 3.14 (the WindowsMCP uv tool env); no WSL-repo language changes.

**Primary Dependencies**: windows-mcp 0.8.8 (installed uv tool at `C:\Users\RLWC145\AppData\Roaming\uv\tools\windows-mcp\`) — patched locally per the house pattern (hermes-agent, OfficeMCP already carry documented local patches).

**Storage**: N/A (behavior timing change).

**Testing**: manual visual validation per `quickstart.md` (V1–V5); WSL suite (346 pytest tests) must stay green (no repo code touched); `ControlStatus.wait_seconds` probe asserts the unchanged 10 s window.

**Target Platform**: Windows 11 (the user's machine, via the `windows-mcp-server` login scheduled task).

**Project Type**: configuration/patch change to a third-party desktop service.

**Performance Goals**: notice auto-dismiss ≤ ~3 s after the AI's last action (SC-001).

**Constraints**: user-revert window and wait-for-idle countdown must remain 10.0 s (FR-003, Clarifications Q1); takeover must remain immediate; the patch must be documented (DEPLOY.md) so a tool upgrade that reverts it is detectable (FR-005).

**Scale/Scope**: one constant change + service restart + verification; no new services, no repo code.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Contract preservation | PASS | No MCP tool schemas, no `ask` fields, no chatflow contracts touched — internal third-party timing only. |
| II. Tests-first | PASS with note | The behavior is visual timing inside a third-party Windows process; the runnable check is the quickstart's V1/V2 measurement protocol (V2's `ControlStatus.wait_seconds` is scriptable). No repo test surface exists for a foreign process's overlay. |
| III. Minimal dependencies | PASS | No new dependencies; a one-constant patch to an already-installed tool. |
| IV. Honest answers | PASS | FR-005 keeps the failure surface honest (reversion is observable; DEPLOY.md documents the patch). |
| V. Spec-driven replacement | PASS | Nothing superseded; additive behavior change per spec. |

No violations — Complexity Tracking table not required.

**Post-Phase-1 re-check**: unchanged — the design (research.md R3, data-model.md) introduces no code in this repo, no contracts, and no dependency changes; all gates still pass.

## Project Structure

### Documentation (this feature)

```text
specs/032-ai-control-dialog-timeout/
├── plan.md              # This file
├── research.md          # Phase 0 output — what the notice is, which constants govern it
├── data-model.md        # Phase 1 output — the control state machine's two timing surfaces
├── quickstart.md        # Phase 1 output — V1–V5 validation scenarios
├── checklists/          # Spec quality checklist (from /speckit.specify)
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
# No repo source changes — the patch surface lives outside this repository:
# C:\Users\RLWC145\AppData\Roaming\uv\tools\windows-mcp\Lib\site-packages\
#   windows_mcp\desktop\control.py        (lease-tail constant, line ~317)
#   windows_mcp\desktop\control_overlay.py / control_overlay_art.py   (notice rendering — read-only)
#
# Repo-side artifacts touched at implementation time:
DEPLOY.md                                  # patch note + re-apply step (FR-005)
reboot.sh                                  # (no change expected — :8800 health check already covers it)
```

**Structure Decision**: zero-repo-code feature; the only repo delta is documentation. Contracts/ directory intentionally omitted — this feature exposes no interfaces (pure internal third-party behavior change).

## Complexity Tracking

> Not required — no Constitution violations to justify.
