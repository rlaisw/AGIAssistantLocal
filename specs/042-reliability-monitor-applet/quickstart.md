# Quickstart: validate the Reliability Monitor applet (042)

Runnable validation for the new target — mirrors the sweep pattern proven across the other 34 surfaces.

## Prerequisites

- Sidecar rebuilt with the new target + launch form; the Windows-MCP service running (full 21-tool surface); an active interactive desktop.
- The owner present for hands-off rhythm (type the request, then hands off ~10 s).

## A. Unit battery (tests-first in implement)

```
.venv/bin/python -m pytest tests/unit/test_windows_mcp_applets.py -q
```

Pins:
1. "reliability monitor", "reliability history", "stability monitor" all resolve to the one target (0% guessed launches for unknown variants — the ask-back pin already covers the negative side).
2. The launch form pins to the live-verified per-host form (regression pin: the plain `perfmon /rel` form must never return — it silently exits from the service's context).
3. The other 34 targets keep resolving (regression sweep of the resolution battery).

## B. Live E2E

1. **Open**: in chat say "open the reliability monitor" (or through the container tool: `windows_mcp_open_settings(target="reliability monitor")`). Expected: `{status: ok}` < 15 s desktop-quiet, and a "Performance Monitor" mmc window visible in the interactive session.
2. **Ask-back**: "open the reliability thingamajig" → the blocked ask-back naming the (now 35-surface) list.
3. **Audit cross-check**: `windows-mcp-open` executed row present for the open conversation.

## C. Regression

- The full unit suite stays green (`pytest tests/unit -q` — 715+ at the time of writing).
- One spot-check open of a pre-existing target (e.g., "open device manager") still works — the launcher's new per-host branch must not disturb the existing three forms.

## Post-verification note

The reliability chart fills over seconds after the window opens — the relay says the window opened; it never claims the chart is ready.
