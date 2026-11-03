# Bug Assessment: Gateway→OfficeMCP session intermittently drops tool-call arguments ("no response")

- **Slug**: `officemcp-connection-error`
- **Created**: 2026-11-03
- **Source**: pasted text ("call officemcp no response")
- **Verdict**: valid — a recurring, intermittent reliability defect, reproduced and documented 3× this session; all three layers healthy at probe time (the flake is between failures)
- **Severity**: high — every occurrence blanks an Office-lane turn (300–600 s timeout or "arguments stripped"), and the user experiences "no response"

## Report (verbatim or summarized)

User report: *"call officemcp no response"*. This is the same failure observed three times in this working session alone: (1) the 031 implementation's email compose — *"the tool dropped my `code` argument on every invocation and ran only its default snippet"* (agent report, 2026-11-03); (2) the 031 battery's O1/O2 — *"the harness delivered my tool_call arguments as empty on 9 consecutive attempts"* + *"the PowerShell fallback command was held for user consent and timed out"* (agent report, 2026-11-03); (3) the user's direct email task — same args-stripped + PowerShell-fallback pattern. Each time, the documented recovery (`hermes mcp remove OfficeMCP` + `yes | hermes mcp add` + `hermes gateway restart`) restored it, but the defect **recurs** — the recovery is a band-aid, not a cure.

## Symptom

An Office-lane chat turn intermittently gets **no usable response**: the gateway agent's `RunPython` tool calls arrive at the OfficeMCP server with their `code` argument **empty** (the server executes the default snippet — "hello world from OfficeMCP"), the agent retries (observed: 4–9 consecutive empty deliveries), then either burns the turn to the 300–600 s budget or falls back to a PowerShell COM detour that the gateway's consent gate blocks ("held for user consent"). The user sees "no response" or a confusing partial failure. The OfficeMCP service itself is healthy throughout (direct MCP calls always deliver args — probe-verified again this assessment), and the failure mode disappears after the gateway's MCP session is re-registered — then reappears later.

## Reproduction

1. **Observed pattern (3 occurrences, 2026-11-03)**: after the gateway runs normally for a while (hours), an Office task's RunPython calls begin arriving with empty arguments at the server; the agent report states the count ("9 consecutive attempts") and pivots to PowerShell, which the consent gate holds until timeout.
2. **Frequency evidence (this session's audit trail)**: 22 office-task audit entries mention the args-stripped/default-snippet pattern or its PowerShell fallback; 6 entries are 300 s/600 s turn-budget timeouts; 4 entries explicitly name the "arguments as empty" delivery.
3. **All layers healthy at probe time (this assessment)**: OfficeMCP :8888 reachable; gateway /v1/models 200; `hermes mcp test OfficeMCP` enumerates all 14 tools; a **direct raw MCP RunPython call delivers the `code` argument perfectly**; and a lane-level task through the gateway completed `ok` in 65 s. The defect is intermittent by nature — between failures everything works.
4. [NEEDS CLARIFICATION: the exact time-to-failure — how long the gateway's MCP session stays healthy before the first empty delivery. The three observed failures were separated by hours; the user's report is the fourth signal.]

## Suspected Code Paths

- **The gateway's MCP client session** (`~/.hermes/hermes-agent/` — the hermes-agent runtime, upstream, not this repo): the SSE client session to OfficeMCP degrades silently — the tool-call POSTs reach the server (the server responds — default snippet execution proves the call arrives) but the arguments are lost in the client's serialization or the session's message routing. The agent runtime dispatches through `agent/tool_dispatch_helpers.py` (grep-verified during spec 030's plan); the precise drop point is inside the upstream hermes-agent code, outside this repository.
- **Not implicated**: `src/agentic_rag_mcp/office_gate.py` / `server.py` / `hermes_client.py` — the sidecar's directive construction is upstream of the MCP hop and unchanged across the failure/no-failure states; the OfficeMCP server (`OfficeMCP.py` RunPython) handles the args correctly when they arrive (raw-probe-verified); the mirrored-loopback transport is byte-clean (direct calls always work).
- **Contributing factor — the consent gate**: the agent's PowerShell-COM fallback is a rational recovery attempt, but the gateway's consent system holds it for interactive approval that the API-server caller can never give, converting a degraded-but-recoverable turn into a guaranteed timeout. The fallback path amplifies the failure's cost.

## Root Cause Hypothesis

**Medium-high confidence in the layer, low in the precise statement.** The hermes-agent's MCP-over-SSE client session to OfficeMCP degrades after a period of uptime — tool-call arguments are silently dropped between the gateway and the server (the server receives the call, executes with empty/default arguments, and responds normally — so the gateway never sees an error). The degradation is cleared by re-registering the MCP connection + restarting the gateway (the DEPLOY.md row's procedure, applied successfully three times today), which resets the SSE session state. The precise upstream statement (session reconnect logic, serialization, or the message-routing table) is inside `~/.hermes/hermes-agent/`, outside this repo, and needs upstream debugging with a `docker logs`-equivalent trace on the gateway during a failing window.

## Proposed Remediation

**Preferred (this repo — mitigation, not a cure)**: make the **sidecar detect and auto-recover** the stale session so the user never sees "no response":
1. Add an `OFFICE_INSTRUCTIONS` rule: "if 2+ consecutive RunPython calls return only the default echo (the code argument was dropped), STOP retrying, say the Office session is degraded, and report TASK: FAILED with the reason 'OfficeMCP session stale — recovery: hermes mcp remove/add + gateway restart'." — the agent stops burning the turn on doomed retries and the user gets an actionable error instead of silence.
2. Add a **battery/lane watchdog probe** (extend `scenario_hermes_office_task`'s O-matrix): a pre-flight `RunningApps()` call per scenario run — if the gateway's MCP session is degraded, the pre-flight fails fast (< 5 s) instead of burning a 600 s turn, and the scenario reports "session stale, run recovery".
3. **DEPLOY.md**: upgrade the existing troubleshooting row from "recovery procedure" to "recurring known defect" with the three-probe diagnosis (service direct → session test → lane probe) and the upstream-filed note.

**Alternatives**:
- **Fix upstream** (the real cure): file the bug against hermes-agent — the MCP client's SSE session drops tool-call arguments after a period; provide the reproduction (direct calls always deliver; the gateway's don't, cleared by remove/add + restart). This is the only path to eliminating the flake entirely; everything this repo can do is detection + fast recovery + honest reporting.
- **A cron-style session refresh**: a scheduled `hermes mcp remove/add + gateway restart` on an interval (ugly — bounces the whole gateway, interrupts any in-flight turn; rejected unless the frequency demands it).

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_client.py` (OFFICE_INSTRUCTIONS: the stop-retrying rule)
- `src/agentic_rag_mcp/deploy/battery.py` (the watchdog pre-flight)
- `DEPLOY.md` (the upgraded troubleshooting row)

**Tests to add or update**:
- Unit: the instructions text contains the new rule (a text assertion in the tool suite)
- Battery: the watchdog pre-flight runs and reports honestly on a degraded session (hard to unit-test the degradation itself — the pre-flight's healthy-path pass is covered by every existing green scenario)

## Risks & Considerations

- The stop-retrying rule must not fire on legitimate default-snippet returns (the agent calling RunPython with no code deliberately) — the rule triggers on **2+ consecutive** empty deliveries during a real task, not one.
- The watchdog adds ~2–5 s per battery run (a cheap RunningApps call).
- The upstream fix is the real answer — this repo's changes convert a 300–600 s silent failure into a <10 s honest, actionable one.
- No security impact: the degraded session fails safe (arguments dropped = no code executed, not wrong code).

## Open Questions

- [NEEDS CLARIFICATION: how long the gateway's MCP session typically stays healthy before degradation — hours? Until the gateway or OfficeMCP process restarts? This determines whether a scheduled refresh is worth considering.]
- [NEEDS CLARIFICATION: whether the user wants the upstream bug filed now (I can draft the report with the reproduction evidence from this session's three occurrences).]
