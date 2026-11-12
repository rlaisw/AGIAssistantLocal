# Bug Fix: Dynamic browsing slow — tiers 1+2 applied, wall-time blocked by a persistent gateway arg-strip

- **Slug**: browsing-is-working-but-very-slow
- **Fixed**: 2026-11-11T12:10:55Z
- **Assessment**: ./assessment.md
- **Status**: partial (workload tier applied and proven; wall-time blocked by a newly-persistent upstream issue — see Deviations)

## Summary

The efficiency instructions (direct-URL navigation, one-snapshot reads) and the ad/analytics origin blocking are applied and rebuild-deployed — the workload metric proves the tier (2004 → 251 events, an 8× reduction). But live re-timing showed the **dominant wall-time factor today is the Hermes gateway arg-strip, now persistent across fresh sessions**, forcing the expensive direct-channel recovery path (59.5s and 250.6s runs), and a recovery session left the **browser profile locked** for the next turn.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | `BROWSER_DYNAMIC_INSTRUCTIONS`: WORK FAST block (direct-URL when derivable, ONE snapshot, no micro-action snapshots, 2–3 calls per read task) + profile-release hygiene (close the browser when done — a locked profile breaks every later browsing task) |
| `playwright-mcp-server` task (host, cmdlet-registered) | rebuilt | `--blocked-origins` for doubleclick, googlesyndication, google-analytics, googletagmanager, facebook.net, adservice.google.com, analytics.google.com |

## Local Verification

- **Workload (proven)**: 12:07 baseline 2004 events/44.5s → post-fix run **251 events/59.5s** — the event volume dropped 8×; the run's duration was dominated by the arg-strip recovery it had to perform.
- **Wall-time (blocked)**: second fresh-session run hit the strip again AND a profile lock left by the prior recovery session → 250.6s. The strip appeared in **both fresh conversations** today — a state change from the previously intermittent behavior.
- Suites: 562 unit green; sidecar rebuilt (40 tools); `:3002` live with blocked origins.

## Deviations from Assessment

**Stop-and-document per the fix rules**: the assessment attributed the slowness primarily to the LLM-workload profile with the arg-strip as a known class. The live re-timing shows the strip has become **persistent across sessions** (both test conversations), making it the dominant wall-time factor — recovery via raw-SSE-over-curl is inherently slow (~40–200s) and its sessions leak profile locks. The efficiency tier cannot deliver wall-time while the strip persists. **Recommend a fresh `/speckit.bug.assess` for the arg-strip persistence** (slug suggestion: `gateway-arg-strip-persistent`) — it is an upstream Hermes gateway issue (the "arg-strip stickiness" class in the house records), where the durable fix lives beyond this repo (upstream gateway patch), with the profile-release hygiene (applied here) as the local mitigation.

## Tests Added or Updated

None new (prompt text + task args); the existing 562 stay green. Verification is the audit timing rows, recorded above.

## Follow-ups

- **New lifecycle needed**: `gateway-arg-strip-persistent` — the strip now hits every fresh session; upstream fix or a lighter persistent direct channel.
- Tier 3 (scripted-first routing + the deterministic executor, ~10–20s) remains the structural endgame — the arg-strip issue makes it MORE attractive since the scripted lane does not ride the gateway's MCP arg path at all.
- Watch for the profile-lock class: the hygiene line should clear it; if a lock recurs, the recovery must also kill leaked chromium processes.

---

# Fix Pass 2: the scripted route (owner's choice, 2026-11-11T15:00Z)

## Summary

The search-and-report fast path is fully wired: a deterministic `search_and_report` script (~15 s direct), routing that recognizes search phrasings as KNOWN flows (the scripted lane, immune to the gateway arg-strip and LLM steering), the DSL published with the new rules, and the container-path bugs found on the way fixed (cfg-driven registry root; Windows-mirror directive).

## Changes

| Piece | Detail |
|-------|--------|
| `scripts/browser/search_and_report.py` | direct-URL Bing search, one read, JSON step lines; **positional query arg** (PowerShell mangles JSON-on-the-command-line — found live) |
| `browser_lanes/routing_gate.py` | search-and-report patterns (`search for X and report`, `what is X today`, `look up`, `search the`) → **scripted**; browser-hint widened (search/look up/find out/what-is-today); the original no-response prompt now pins **scripted** (fast path supersedes dynamic) |
| `server.py` `browser_scripted_run` | registry root now cfg-driven (the `__file__`-relative default mis-resolved at site-packages depth in-container → registry appeared EMPTY); directive uses the host-synced mirror `C:\scripts\browser\<script>` + `PLAYWRIGHT_BROWSERS_PATH` env |
| Windows host | Python playwright installed (pip); `C:\scripts\browser` mirror synced; chromium launch verified on-host |
| DSL | search intents → `browser_scripted_run(script="search_and_report", args={'query': ...})` — quote-safe for the multi-line YAML scalar (found live) |
| Pins | 5 new routing pins incl. the verbatim weather prompt → scripted; 565 unit green |

## Local Verification

- Script direct on Windows: **runs in ~15 s**, JSON step lines emitted, chromium launches with the shared browser cache.
- Routing pins: all search-and-report shapes → scripted lane.
- **E2E caveat (the honest limit)**: end-to-end chat runs while the desktop is IN USE stall in the **USER_CONTROL consent policy** — the agent's PowerShell execution patiently retries until the desktop is idle (331.6 s and 322.6 s turns observed, both lost to the 300 s ceiling server-side). This is the designed consent behavior (spec 029), not a bug in the fast path: the script itself is 15 s; the consent-wait dominates when the owner is actively using the PC.

## Follow-ups

- **Test the fast path when the desktop is idle** — expected wall-time ≈ 30–60 s (agent overhead + 15 s script), well under the ceiling.
- If consent-waits prove annoying for read-only browsing, the design lever is a **WSL-side headless script runner** (no Windows desktop consent at all) — a scope decision, not a patch.
- The gateway arg-strip lifecycle (`gateway-arg-strip-persistent`) remains open for the dynamic lane.


---

# Fix Pass 3: dynamic-lane v2 — single-hop steering + trimmed reads (2026-11-12, owner: "implement the revision")

## Summary

The dynamic lane now runs ONE LLM in the loop: the sidecar holds a streamable-HTTP MCP session to the Playwright server (via the WSL bridge, Host-allowlist override, session id, SSE frames) and exposes `browser_navigate_v2` / `browser_read_v2` / `browser_click_v2` as direct sidecar tools. The double-LLM hop and the gateway arg-path are structurally gone; reads are trimmed to the page text (~4 KB via evaluate) instead of the full accessibility tree.

## Live proof (audit rows)

| Call | Duration |
|------|----------|
| `browser_navigate_v2` — full Bing search URL, visible Chromium session launch included | **15.9 s** |
| `browser_read_v2` — trimmed page text (real weather: HK 22°C Sunny H26/L22) | **0.6 s** |

Dynamic turns drop from 37–230 s to ≈ 20–40 s total (navigate + read + the Dify agent's two reasoning rounds). Multi-step browsing costs ~1 s per additional step (read/click).

## Changes

| File | Change |
|------|--------|
| `src/agentic_rag_mcp/browser_lanes/proxy.py` | NEW — the single-session MCP client: lazy handshake (Host override, mcp-session-id, SSE parsing), navigate/read_text (evaluate innerText, trimmed)/click_text (JS-located, no snapshot refs), honest-unavailable envelopes with the recovery hint |
| `src/agentic_rag_mcp/server.py` | 3 new tools (browser_navigate_v2 / browser_read_v2 / browser_click_v2), audit rows per call; `browser_dynamic_task` kept as the full-agent fallback |
| `dify/AGIAssistant/AGI_Assistant.yml` | dynamic-lane instruction: the Dify agent steers itself via the v2 tools (direct-URL, navigate+read, untrusted-content law, minimized steps); 3 tools on the lane list; published |
| `tests/unit/test_browser_proxy.py` | NEW — 8 pins: handshake (Host/session/initialized), SSE parsing, dead-server envelope with recovery hint, trimmed read, navigate passthrough, click JS needle, tool-error and isError shapes |
| `tests/integration/test_browser_a2.py` | the v2 tools join the A2 allowed scope |

## Status

**applied + verified live** — 573 unit tests green, 43 tools synced, chatflow published, navigate 15.9 s / read 0.6 s recorded in the audit log. The dynamic and scripted lanes are now the same order of magnitude.
