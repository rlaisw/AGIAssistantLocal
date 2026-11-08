# Bug Assessment: Desktop followup turn killed at ~600 s — the Dify plugin-daemon's timeout is the binding ceiling on long desktop-control tasks

- **Slug**: `desktop-followup-timeout-600s`
- **Created**: 2026-11-08T08:35+00:00
- **Source**: pasted text (the re-reported Control Panel transcript) + live investigation — the pasted "blocked" reasoning turned out to be the OLD pre-fix turn; the actual new failure is a silent in-flight kill
- **Verdict**: valid — a distinct root cause from the (fixed, verified) parsing bugs in the sibling lifecycle
- **Severity**: medium — long desktop-control tasks (multi-window navigation under consent waits) die silently with no verdict and no audit trail; the user sees a generic workflow error

## Report (verbatim or summarized)

> "The launch tool can't run commands with arguments. However, the desktop followup capability can type into programs." (re-paste of the earlier blocked Control Panel transcript)

Investigation of the actual recent turns: the parsing class is fixed (08:06 Control Panel ran end-to-end; 08:15 task manager in 15 s), but the 08:17:15 turn — "open windows control panel , display my network adapter" — **never produced a verdict**: the workflow run failed at 601.9 s with `PluginDaemonInternalServerError: killed by timeout`, and the audit log has no entry after 08:15:23.

## Symptom

A desktop-followup turn that runs longer than ~600 seconds is killed mid-flight by the Dify plugin-daemon — the user gets a generic "Run failed" with no honest verdict from the lane (the sidecar's own Hermes budget is also 600 s, so whichever fires first, the turn dies without the audit trail the honesty rules depend on). Expected: either the turn completes or it fails honestly inside the envelope with an audit entry.

## Reproduction (evidenced, 2026-11-08 UTC)

1. 08:06–08:13 — the first Control Panel followup (`show me network adapter configuration…`): **succeeded in 470 s** — close to the ceiling
2. 08:17:15 — the follow-on Control Panel turn (`display my network adapter`): **killed at 601.9 s** (`PluginDaemonInternalServerError: killed by timeout`; workflow run `failed`; message `status=error`, answer empty) — **no audit entry** (the audit writes at verdict time; a killed call produces none)
3. Context: WindowsMCP tree captures were slow in the window (19.75 s / 26.11 s desktop captures in its logs), Control Panel was already open (navigating an existing window adds steps), and desktop-control consent waits apply whenever the user is active — all of which stretch these turns toward the ceiling
4. The stream-cut class is already fixed (keep-alives carry the SSE past 120 s) — this is a **different, later ceiling**: total tool duration

## Suspected Code Paths

- Dify plugin-daemon kill timer: ~600 s on an in-flight tool call (the `PluginDaemonInternalServerError: killed by timeout` at 601.9 s; `MAX_TOOLS_NUM`-adjacent env had no timeout knobs — the earlier hunt in `close-excel-wait-long-time` found none, and the keep-alive fix moved the effective failure from ~120 s to the daemon's own ceiling)
- `src/agentic_rag_mcp/config.py` — `[hermes] timeout_s = 600`: the sidecar's Hermes budget, equal to the daemon's kill timer, so a slow turn is a race between two silent killers — and when the daemon wins, **no honest verdict and no audit entry** reach the user
- The desktop-followup execution itself (agent + WindowsMCP): 470–600+ s turns are structurally possible (cold app + window navigation + consent waits + slow UIA captures), so the ceiling will keep being hit on complex navigation tasks

## Root Cause Hypothesis

**High confidence.** Long desktop-control turns legitimately need 8–10+ minutes under consent waits and slow accessibility captures; both the sidecar's Hermes budget and the Dify plugin-daemon's kill timer sit at 600 s. When the daemon's timer fires first, the tool call dies with a generic plugin error, the sidecar's verdict/audit never materializes, and the honesty envelope (which every other failure mode respects) is bypassed entirely. The prior keep-alive fix (read-tool-response-failed) solved the *stream idle* ceiling; this is the *total duration* ceiling one level up.

## Proposed Remediation

**Preferred**: make the honest envelope smaller than every external kill timer. (1) Lower the sidecar's Hermes budget for launch-followup tasks so the sidecar always finishes first and reports honestly inside the envelope — e.g. `[hermes] timeout_s` stays 600 generally, but the launch lane's `_await_with_keepalive` budget is capped at ~540 s (90% of the daemon ceiling), guaranteeing the user gets "Hermes did not finish within 540s — try a smaller task" (an honest, auditable verdict) instead of the daemon's silent kill. (2) Additionally, the launch instructions should tell the agent to prefer the **fastest navigation path** (e.g., for adapter settings: `control /name Microsoft.NetworkAndSharingCenter` is argument-blocked at launch, but the agent's own PowerShell tool can open the direct settings dialog — that is a consent-gated desktop action, not a launch argument — cutting minutes off navigation turns). This is instruction-level and keeps the launch scope intact.

**Alternatives**:
- Raise the plugin-daemon timeout — its knob was never found in the earlier hunt; patching a Dify component adds drift for marginal gain (the honest 540 s envelope is simpler)
- Split followups into multiple turns ("open control panel", then "show me adapter settings") — works today by user discipline; the 540 s envelope doesn't remove that option but stops the silent kills when users don't split

**Files likely to change**:
- `src/agentic_rag_mcp/server.py` — `_await_with_keepalive` budget parameter (540 for the launch lane), keeping the generic Hermes budget untouched for other lanes
- `src/agentic_rag_mcp/hermes_client.py` — LAUNCH_INSTRUCTIONS: fastest-path navigation guidance for known settings destinations
- `tests/unit/test_hermes_launch_tool.py` — budget assertion

**Tests to add or update**:
- Unit: the launch tool passes a ≤540 s budget to the keepalive wrapper (so the honest verdict always precedes the daemon kill)
- Instruction guard: the fastest-path guidance text

## Risks & Considerations

- Capping at 540 s converts some would-be-completing slow turns (470–600 s) into honest failures — the trade is explicit: an honest "try a smaller task" beats a silent kill with no verdict; the fastest-path guidance should push most turns well under the cap anyway
- The 470 s Control Panel success shows complex turns CAN complete under the ceiling — the cap only binds the tail
- WindowsMCP's slow UIA captures (19–26 s per snapshot observed) are a major time sink; the `WINDOWS_MCP_EXCLUDE_PROCESSES` knob exists if a pathological app is identified — separate concern, not this fix
- The daemon kill applies to ALL sidecar tools (office lane too: the 600 s Hermes budget has the same race) — the same 540 s cap logic could extend to office tasks later if 600 s kills appear there

## Open Questions

- [NEEDS CLARIFICATION: should the 540 s cap apply to ALL Hermes lanes now (office included — same race exists) or launch-followup only for this fix? Recommend launch-only now, office later if kills appear there — smaller blast radius.]
