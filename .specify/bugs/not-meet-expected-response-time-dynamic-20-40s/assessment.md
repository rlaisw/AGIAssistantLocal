# Bug Assessment: Dynamic-lane response time did not meet the 20–40s expectation

- **Slug**: not-meet-expected-response-time-dynamic-20-40s
- **Created**: 2026-11-12T03:09:52Z
- **Source**: pasted text (owner's live re-test after the dynamic-lane v2 revision)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim)

> "not meet expected response time dynamic ~20–40s"

## Symptom

After the v2 revision, the owner's Chat UI weather test took **~5–6 minutes**, not the promised 20–40 s. The v2 tools themselves executed in **4.8 s** (warm) — the turn's time went elsewhere.

## Reproduction (forensics from the owner's own test window, 03:04–03:10 UTC)

1. The Dify agent routed the weather search to **`browser_scripted_run(search_and_report)`** — per the search-and-report DSL fast-path rule added in the browsing-slow fix.
2. The sidecar sent the PowerShell directive to the **Hermes agent** → gateway turn ran **325.4 s** (gateway log: inbound 11:04:46 → response ready 11:10:12) — the agent's PowerShell execution waits out **USER_CONTROL** while the owner actively tests at the desktop, plus full agent-turn overhead.
3. Only at the tail did the v2 tools fire: `browser-navigate-v2` **4.2 s** + `browser-read-v2` **0.6 s** (warm session) — proving the v2 path is fast and consent-free while the desktop is in use.
4. Corroborating defect: the scripted lane's verification has failed intermittently all day with *"the script emitted 1 steps but 2 checkpoints were declared"* (15:02:51, 01:04:21) — the relay agent returns only the FIRST of the script's JSON step lines, so `verify_steps` aborts an actually-successful run.

## Suspected Code Paths

- `dify/AGIAssistant/AGI_Assistant.yml` — the search-and-report fast-path rule points search traffic at `browser_scripted_run`, whose delivery mechanism is a full Hermes agent turn + PowerShell + USER_CONTROL: the slowest path in the system for a desktop-active user.
- `src/agentic_rag_mcp/server.py` (`browser_scripted_run` directive) — "report the script's JSON step lines verbatim" is not strong enough; the agent relays only step 1, breaking the checkpoint count.
- `src/agentic_rag_mcp/browser_lanes/routing_gate.py` — `_REPEATABLE` sends search shapes to `scripted`.
- `browser_lanes/proxy.py` + v2 tools — working as designed (4.8 s warm) and **not consent-gated** (proven live at 03:10 with the owner active).

## Root Cause Hypothesis

**The fast-path routing is inverted.** The v2 dynamic tools (navigate+read) are now the *fastest and most reliable* way to serve search-and-report intents (~5 s tool time, no agent turn, no consent gate, deterministic URL+read) — but the DSL/routing still sends that traffic to the scripted lane, whose script is equally deterministic but whose *delivery* rides a full agent turn that stalls on USER_CONTROL whenever the desktop is busy. Secondary: the scripted relay drops step lines, making the scripted lane flaky even when idle. Confidence: **high** — every number above is from the owner's own test window.

## Proposed Remediation

**Preferred** — flip the fast path, harden the relay:
1. **Route search-and-report intents to the v2 dynamic tools** (navigate direct-URL + read, ~2–3 tool calls, click only when needed) in both the DSL rule and `routing_gate._REPEATABLE` classification. The scripted lane remains for genuine multi-step flows (login+download, multi-page scrapes) — where its determinism earns its agent-turn cost — and as fallback.
2. **Harden the scripted directive**: demand the agent return EVERY JSON line the script prints, in order, unchanged ("copy the script's complete output; if you omit a line the run fails verification") — fixing the "1 of 2 steps" aborts for the cases where the scripted lane is still used.
3. Expectation: search turns ≈ classifier + 2–3 v2 calls + kimi rounds ≈ **15–30 s**, desktop-active or idle.

**Alternatives**: execute scripts via the v2 proxy session (bigger change, unifies engines); retire the scripted lane for search only (subset of preferred #1).

**Files likely to change**:
- `dify/AGIAssistant/AGI_Assistant.yml` (the fast-path rule → v2)
- `src/agentic_rag_mcp/browser_lanes/routing_gate.py` (+ its pins)
- `src/agentic_rag_mcp/server.py` (scripted directive hardening)
- `tests/unit/test_browser_routing_gate.py`

**Tests to add or update**:
- Routing pins: search-and-report shapes → **dynamic/v2**, not scripted
- A relay pin is not unit-testable hermetically (agent behavior) — instead assert the directive text contains the verbatim-output demand

## Risks & Considerations

- The v2 path must keep the honest-abort discipline for search (fixed URL + read only; report what the page actually shows — the anti-fabrication rules already in the tool descriptions).
- Don't break the scripted lane's real purpose: multi-step deterministic flows stay scripted; only the search-shape routing flips.
- The 325 s agent turns remain available via `browser_dynamic_task`/scripted when genuinely needed; nothing is deleted.

## Open Questions

- None blocking — the fix is a routing flip plus directive text.