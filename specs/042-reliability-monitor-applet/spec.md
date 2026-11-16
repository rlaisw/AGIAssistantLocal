# Feature Specification: Reliability Monitor applet (perfmon /rel) in the applet tier

**Feature Branch**: `042-reliability-monitor-applet`

**Created**: 2026-11-16

**Status**: Draft

**Input**: User description: "enable Windows Reliability Monitor through the command 'perfmon /rel' and add to Windows-MCP powershell tools"

## Clarifications

### Session 2026-11-16

- Q: Should Reliability Monitor be a new target on the existing open-settings tool, or its own separate chat tool? → A: New target on the existing open tier (Option A, confirmed) — one entry plus synonyms on the proven `windows_mcp_open_settings` surface; everything (launcher, ask-back, audit, honest envelopes) inherited.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Open Reliability Monitor by name (Priority: P1)

The owner asks in chat "open the reliability monitor" (or "reliability history"). The Windows Reliability Monitor window — the stability-history chart of crashes and failures — opens on the owner's desktop within seconds, exactly like the other 34 verified settings surfaces. Opening it is nondestructive: it is a read-only diagnostic view; nothing changes until a human acts inside it.

**Why this priority**: This is the whole feature — one more named surface on the proven, gated open tier; everything else (bounds, ask-backs, honest relays, audit) is inherited and already verified end-to-end.

### Edge Cases

- The Reliability Monitor takes a few seconds to compute its chart on first open — the window appears before the chart fills; the relay does not claim readiness of the data, only that the window opened.
- Unknown or ambiguous phrasing ("open reliability") still asks back with the target list if it cannot resolve — never a guessed launch.
- The desktop-activity deferral and service-down envelopes behave exactly as on every other target (inherited, already live-proven).
- A second "open reliability monitor" opens/focuses per Windows' own behavior for perfmon instances — relayed honestly, never claimed as "already done" without evidence.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: "reliability monitor" (and natural synonyms such as "reliability history", "stability monitor") resolve to the new target on the tier-1 open surface; the launch uses the proven `perfmon /rel` command form through the lane's existing PowerShell tool path.
- **FR-002**: The launch is bounded exactly like every other target — one target per request, nothing beyond the command passed, unknown or ambiguous phrasing asks back with the list.
- **FR-003**: Every attempt is audited under the existing `windows-mcp-open` operation class (executed/blocked/error) in the shared append-only trail.
- **FR-004**: The inherited honesty contracts bind unchanged: no claim without the same turn's call, refusals verbatim, the shared down/deferral envelopes, the hands-off-for-seconds guidance.

### Key Entities

- **Settings target**: the reliability-monitor entry added to the reviewed target inventory (the bounded list the launcher accepts); natural-phrasing synonyms resolve to the same entry.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- SC-001: "open the reliability monitor" in chat opens the Reliability Monitor window on the owner's desktop in under 15 s (desktop-quiet), audited as executed.
- SC-002: The synonyms resolve to the same target; unknown variants still ask back with the list (0% guessed launches).
- SC-003: The existing 34 targets keep working unchanged (regression: the full open-tier battery and target-resolution pins stay green).

## Assumptions

- Reliability Monitor joins the existing tier-1 open surface (`windows_mcp_open_settings`) as a new entry in the reviewed target inventory — no new tool, no DSL change beyond the target list, no new gate machinery; the launch form (`perfmon /rel`) is verified live before pinning.
- The lane's launcher gains no special case: `perfmon /rel` runs through the same proven PowerShell-tool path used by the applets (per-host launch forms apply only where the generic form fails live — decided by the live A/B, as with the `.msc` case).
- The window-presence check for verification uses perfmon's process/window title, mirroring the sweeps already run for the other 34 surfaces.
