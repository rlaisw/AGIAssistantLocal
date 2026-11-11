# Bug Fix: Dynamic browsing hang + unsupported-flag banner — visible Chromium, arg-strip recovery, expectations

- **Slug**: you-are-using-an-unsupported-command-line-flag
- **Fixed**: 2026-11-11T09:49:22Z (owner's choice: Option 2, visible Chromium)
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The lane now launches the **Playwright-managed Chromium** (visible, pinned binary — no Chrome-157 unsupported-flag banner, no user-Chrome pollution), the dynamic instructions gained the **direct-channel arg-strip recovery** (the known gateway class killed the first re-test), and the tool + DSL now set the **1–3 minutes expectation**. Live end-to-end proof: the weather prompt returns real Bing observations with `BROWSE: COMPLETED` on the visible Chromium.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `playwright-mcp-server` task (host, cmdlet-registered) | rebuilt | action args now `--executable-path C:\Users\RLWC145\AppData\Local\ms-playwright\chromium-1254\chrome-win64\chrome.exe` — the Playwright-pinned Chromium, HEADED (owner's Option 2), still `conhost --headless` for the invisible service console |
| `src/agentic_rag_mcp/hermes_client.py` | modified | `BROWSER_DYNAMIC_INSTRUCTIONS` gains the **ARG-STRIP RECOVERY** paragraph: zero-arg-calls-work-but-args-stripped → direct SSE session to `http://127.0.0.1:3002/sse` (the same recovery the OfficeMCP/WindowsMCP lanes teach) |
| `src/agentic_rag_mcp/server.py` | modified | `browser_dynamic_task` description: "dynamic browsing typically takes ONE TO THREE MINUTES — tell the user, do NOT treat the wait as failure" |
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | same expectation in the DSL tool description; published |

## Deviations from Assessment

The assessment did not foresee the **gateway arg-strip** hitting the first re-test (live-test finding: zero-arg `browser_snapshot` worked, `browser_navigate`/`browser_type` arrived argument-less; the agent gave up honestly). The house-known recovery pattern was added to the dynamic instructions — the same fix class as the OfficeMCP/WindowsMCP lanes, now applied to PlaywrightMCP. Otherwise exactly the preferred remediation with the owner's Option-2 choice (visible Chromium instead of headless).

## Local Verification

- Task rebuilt via cmdlets (the XML-import route stays retired): `port3002=True`, SSE live
- Sidecar rebuilt (40 tools), chatflow published
- **Live run 1 (pre-recovery)**: honest failure — "every call with arguments is being stripped… I have to stop and report honestly" (the honesty machinery worked; the browser opened visible on about:blank)
- **Live run 2 (post-recovery)**: `status: ok, verdict: completed` — Bing searched, real weather read (22°C Clear, fire warning, 3-day forecast) on the visible Chromium, no banner

## Tests Added or Updated

No new unit logic (launch-args + prompt text). Live verification is the proof; the A2 pins and dynamic-tool pins stay green (562 suite).

## Follow-ups

- The Stop-vs-response 40 ms race remains inherent to the transport; the expectation text is the mitigation — users now know to wait.
- If the owner later prefers invisible browsing: drop `--executable-path`'s headed behavior by adding `--headless` to the task args (one cmdlet rebuild).
- `chromium-1254` is pinned by Playwright CLI 1.65.0 — a future `playwright install` changes the dir name; the task arg must follow (note for DEPLOY.md's host-prereqs doc pass).