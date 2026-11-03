# Bug Fix: "No PowerPoint tool available" — routing locked by guard; containment refusal made actionable

- **Slug**: `no-powerpoint-tool`
- **Fixed**: 2026-11-03
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The acute component (the misroute to General) was already fixed by the `office-routing-flake` remediation — this fix locks that classification permanently with a battery routing probe for the file-creation-with-path phrasing, and turns the remaining dead end (an out-of-work-folder save location) into an **actionable refusal**: the gate's containment reason now names the owner-configurable `office_root` knob, backed by a DEPLOY.md troubleshooting row covering the lane-root mismatch and today's MCP-transport recovery procedure.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/deploy/battery.py` | modified | `scenario_office_routing` gains the 4th probe: "create a PowerPoint file named test1 … save it to C:\temp\test" → must route to the Hermes branch — the phrasing class from this bug can no longer regress silently |
| `src/agentic_rag_mcp/office_gate.py` | modified | The out-of-work-folder refusal appends the actionable hint: "The work folder is owner-configurable (office_root in the [hermes] config section) — ask the owner to widen it or save inside it" |
| `tests/unit/test_office_gate.py` | modified | `test_outside_work_folder_blocked` now also asserts `"office_root" in reason` — the actionable hint is pinned |
| `DEPLOY.md` | modified | Two troubleshooting rows: the lane-root mismatch (design + the config knob) and the MCP-transport "arguments stripped" recovery (from today's live session — `hermes mcp remove/add + gateway restart`) |

## Diff Highlights (optional)

```diff
  Blocked: {tok} is outside the Office work folder {office_root} — document
  work is confined to the work folder (spec 030 FR-003).
+ The work folder is owner-configurable (office_root in the [hermes] config
+ section) — ask the owner to widen it or save inside it
```

## Tests Added or Updated

- `scenario_office_routing` — 4th probe pins the file-creation-with-path phrasing to the Hermes branch
- `tests/unit/test_office_gate.py::test_outside_work_folder_blocked` — pins the actionable `office_root` hint in the refusal

## Local Verification

- Commands: `pytest tests/unit/test_office_gate.py tests/unit/test_office_state.py tests/unit/test_hermes_office_tool.py tests/contract/test_deploy_cli.py` → **57 passed**; hot-patched `office_gate.py` to the sidecar (restart + health wait)
- Live checks: gate probe — *"create a PowerPoint file named test1 … save it to C:\temp\test"* → `blocked` **instantly** (no agent call) with the full actionable reason; routing+guard scenario live → **PASS** (all four phrasings → hermes, incl. the new one)
- Reproduction note (honest): the original transcript's misroute does not reproduce — today's live probes all route correctly; the fix's contribution is locking that in and making the containment refusal actionable rather than a dead end

## Deviations from Assessment

- None. The optional general-branch wording nit was skipped (the assessment marked it optional; its existing redirect already works).
- The `office_root` re-point alternative was **not** applied — explicitly the owner's decision (open question in the assessment), not part of the preferred remediation.

## Follow-ups

- Owner decision pending (assessment open question): keep `C:\OfficeMCP` or point `office_root` elsewhere (config-only change: `[hermes] office_root` in `~/.config/agentic-rag-mcp/config.toml`, then restart the sidecar).
- Fold this fix into the held T022 commit for spec 030 (same uncommitted working tree).
- The MCP-transport row added to DEPLOY.md documents today's live recovery; the durable fix remains upstream in the hermes-agent MCP client.
- The user's `test1.pptx` was not created by this fix (out of scope); it can be produced on request — inside `C:\OfficeMCP` per the design, or at `c:\temp\test` via the direct path if the owner prefers.
