# Bug Assessment: Dynamic browsing works but is slow

- **Slug**: browsing-is-working-but-very-slow
- **Created**: 2026-11-11T12:09:34Z
- **Source**: pasted text (owner's live experience after the re-tests)
- **Verdict**: valid (performance bug, not a correctness bug)
- **Severity**: medium

## Report (verbatim)

> "browsing is working but very slow"

## Symptom

The dynamic browser lane completes its tasks correctly but each turn takes ~40–230 seconds (measured: 37.3s, 63.4s, 54.1s, **229.5s**, 32.3s, 44.5s across today's runs). Expected: a simple "search and read the weather" in a few seconds-to-tens-of-seconds, not minutes.

## Reproduction

1. Send a browsing prompt; wait for `browser_dynamic_task` to return.
2. Every run lands in the 32–230 s band; the worst (10:04) took 229.5 s for one Bing search + read.

**Measured timing profile** (audit rows, `operation=browser-dynamic`):

| Time | Verdict | duration_s | events | top gaps |
|------|---------|-----------|--------|-----------|
| 09:28 | completed | 37.3 | 480 | — |
| 09:41 | cancelled | 63.4 | 807 | — |
| 10:04 | completed | **229.5** | **3601** | — |
| 12:04 | cancelled | 32.3 | 23 | user stopped early |
| 12:07 | completed | 44.5 | 2004 | 5.7s, 3.0s, 2.8s (item boundaries) |

Key signatures: **first_event_s = 0.0** every time (no transport stall — the gateway responds instantly) and **2000–3600 events per turn** — the volume IS the workload. The gaps are all ≤ 6 s at item boundaries (normal LLM thinking steps), not one big hang.

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_client.py` `BROWSER_DYNAMIC_INSTRUCTIONS` — the current prompt drives the agent step-by-step with full-page `browser_snapshot` reads between every action; kimi-k3 re-reads the entire accessibility tree per step (thousands of tokens per snapshot × several steps × reasoning tokens = the 40–230 s).
- The lane's architecture (035 research R4/R7): an LLM agent steers each browser action — inherently slow; the 035 program's own **deferred "deterministic sidecar executor"** follow-up (in the session work-state from before this program started) names exactly this as "the last latency lever (~10–20 s, no LLM in the mechanical loop)".
- The Playwright MCP server launch args (`windows/playwright-mcp-task` action) — defaults enable full snapshots, no resource blocking.

## Root Cause Hypothesis

Not a stall — a **workload profile**: every dynamic turn is an LLM-in-the-loop browsing session. The agent takes multi-second reasoning steps between each browser action and ingests a full page accessibility snapshot at each step (2000–3600 streamed events, all gaps ≤ 6 s, first event instant). The 229.5 s outlier = extra reasoning cycles + heavier page. The lane is behaving as designed; the design itself is the slowness. Confidence: **high** (timing profiles are unambiguous).

## Proposed Remediation

**Preferred** — three tiers, cheapest first:
1. **Prompt efficiency (days)**: tighten `BROWSER_DYNAMIC_INSTRUCTIONS` — "minimize steps: navigate DIRECTLY to the search URL when one is derivable (`https://www.bing.com/search?q=...`), take ONE snapshot, read, report — do not snapshot between every micro-action". Many turns waste steps on open→type→wait→snapshot→scroll→snapshot. Direct-URL navigation + one-shot reading cuts typical turns to ~2–3 tool calls (~15–30 s).
2. **Launch-arg efficiency (same change window)**: add `--blocked-origins` for ad/analytics CDNs to the playwright-mcp task args (smaller pages, faster loads, fewer snapshot tokens).
3. **The deterministic executor (the real fix, later)**: for known task shapes ("search X and report", "read page Y"), a script-side fast path — the **037 scripted lane already exists for exactly this** (`browser_scripted_run`, ~10–25 s, no LLM steering); teach the classifier to prefer it for any flow with a derivable URL, and grow the script registry. The standing "deterministic sidecar executor" spec remains the structural endgame (~10–20 s, no LLM in the mechanical loop) — a future component spec.

**Alternatives**: switch the agent to a faster model for browsing turns (rejected: model changes are lane-wide policy, not this bug); headless (already known to not matter — the profile shows no rendering stall).

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_client.py` (instruction tightening — tier 1)
- `windows/playwright-mcp-task` action args via cmdlets + the recreate script (tier 2)
- `dify/AGIAssistant/AGI_Assistant.yml` (classifier preference for scripted lane when a URL is derivable — tier 3, if pursued now)
- `scripts/browser/` (tier 3: a `search_and_report` starter script)

**Tests to add or update**:
- No new unit logic for tiers 1–2 (prompt/args). Verification is live timing: re-run the weather prompt and compare `duration_s` in the audit row — target < 30 s typical.
- Tier 3, if pursued: the scripted-run pins extended for the new script.

## Risks & Considerations

- Tier 1 risks over-optimizing into missed content: the instructions must still demand reading what the page ACTUALLY shows (anti-fabrication) — one snapshot is enough for a results page, but the honesty rules stay.
- Tier 2 blocking origins: block only well-known ad/analytics domains, never content CDNs.
- The 229.5 s run also brushed the ~300 s transport ceiling — efficiency work doubles as headroom insurance.

## Open Questions

- None blocking. Tier 3 (scripted-first routing / deterministic executor) is a scope decision for the owner — do it as this bug's follow-up or as its own component spec.