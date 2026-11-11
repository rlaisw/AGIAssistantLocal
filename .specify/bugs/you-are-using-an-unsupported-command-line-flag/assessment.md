# Bug Assessment: Dynamic browsing "hung" + Chrome unsupported-flag banner

- **Slug**: you-are-using-an-unsupported-command-line-flag
- **Created**: 2026-11-11T09:45:15Z
- **Source**: pasted text (owner's live re-test error, ~09:40 UTC)
- **Verdict**: valid (two intertwined issues)
- **Severity**: medium

## Report (verbatim)

> "No response hung up, you are using an unsupported command-line flag --disable-blink-feature-automationcontrolled"

## Symptom

The owner re-sent the weather prompt (~09:40). A Chrome window opened showing the "You are using an unsupported command-line flag: --disable-blink-features=AutomationControlled" banner, the chat stayed silent for ~60 s, the owner pressed Stop, and no answer arrived. Expected: browsing completes and the weather is reported — or, at minimum, an expectation of how long it takes.

## Reproduction

1. Send a browser prompt in the Chat UI (~09:40:03, chat `9e1f5668…`).
2. Chrome opens with the unsupported-flag infobar; the chat shows nothing for ~1 minute.
3. Stop at 17:41:06 local. Reproduced once by the owner.

**Forensics (audit + gateway logs)**:
- 09:40:00 skill-search ran; 17:40:03 the browsing directive reached the agent.
- 17:41:07.155 gateway: `response ready … time=63.5s api_calls=22 response=1212 chars` — **the turn actually completed** and had a 1212-char answer.
- 17:41:06 the user's Stop landed (audit: `cancel-turn … the chat stopped this turn`) and 17:41:07.194 `SSE client disconnected` — the cancel **raced the response by ~40 ms** and killed its delivery. The "hang" was a finished-but-uncancelled-in-time turn with zero interim feedback.

## Suspected Code Paths

- **The banner**: `@playwright/mcp` 0.0.85 launches the **system Chrome** (v157.0.8103.40 on this host) with `--disable-blink-features=AutomationControlled` among its default args; Chrome 157 has removed the `AutomationControlled` blink feature, so the flag is now "unsupported" and the browser shows the alarm infobar. The flag is hardcoded in the MCP's browser launch (upstream).
- **The perceived hang**: `src/agentic_rag_mcp/server.py` `browser_dynamic_task` returns only when the whole browsing turn finishes (~60-90 s observed); no interim feedback reaches the chat, and neither the tool description nor the DSL sets the "this takes a minute or two" expectation.
- The windows/playwright-mcp-server task action (just rebuilt headless for the service console): still launches `playwright-mcp.cmd --port 3002 --host 127.0.0.1` — **system Chrome channel, headed**.

## Root Cause Hypothesis

Two causes: (1) the MCP's hardcoded anti-automation flag collided with the host's very new Chrome (157) — cosmetic but alarming, and it makes every browsing turn open the user's real Chrome with a scary banner; (2) the dynamic lane gives no progress signal and takes ~1 minute, so the user reasonably treats it as hung — the Stop then kills the just-finished response (the 40 ms race is logged). Confidence: **high** (all three facts are in the logs; Chrome version verified on-host).

## Proposed Remediation

**Preferred** — switch the lane to the Playwright-managed Chromium, headless, and set expectations:
1. Change the `playwright-mcp-server` task arguments to `--browser chromium --headless` (the Chromium binary shipped by the installed Playwright CLI 1.65.0 — pinned, supports its own flags, no system-Chrome banner, no visible window at all). This removes the banner AND the surprising Chrome window, and decouples the lane from the user's personal Chrome (no profile pollution).
2. Set the expectation in the surfaces: extend `browser_dynamic_task`'s tool description and the DSL browser-lane rule with "dynamic browsing typically takes 1–3 minutes; the tool returns when the browsing completes — do not treat the wait as a failure" so the agent relays it.

**Alternatives**:
- `--browser msedge` headed (Edge may still accept the flag) — keeps consent-visible browsing but keeps the window-opening surprise and a future Edge update could repeat this.
- Upgrading `@playwright/mcp` to a release that drops/controls the flag — blocked on upstream; revisit later.

**Files likely to change**:
- `windows/playwright-mcp-task.xml` (task arguments; note: the live task is cmdlet-registered — the fix pass must re-register via cmdlets, not XML import)
- `src/agentic_rag_mcp/server.py` (tool description text)
- `dify/AGIAssistant/AGI_Assistant.yml` (lane rule expectation sentence)
- possibly `tests/integration/test_browser_a2.py` (no functional pin expected to change)

**Tests to add or update**:
- No new logic — this is launch-args + prompt text. Verification is live: re-run the weather prompt; expect no banner, no visible Chrome window, and a completed report in ~1–3 min (no Stop pressed).

## Risks & Considerations

- **Headless removes consent-visibility**: browsing now happens invisibly. The A2 untrusted-content law is unaffected (it lives in the agent prompt); desktop consent policies are unaffected (browsing is not a desktop action). If the owner prefers visible browsing, use `--browser chromium` without `--headless` — Chromium's own window appears (still no banner), which keeps visibility without the system-Chrome weirdness.
- The 40 ms Stop race is inherent to the transport (response vs cancel); the expectation-setting mitigation is the practical cure.
- `--browser chromium` requires the Playwright-installed Chromium (present — installed this morning).

## Open Questions

- [NEEDS CLARIFICATION: visible or invisible browsing preferred? — the fix defaults to headless per the owner's console-hiding direction; say so if you want the Chromium window kept visible]