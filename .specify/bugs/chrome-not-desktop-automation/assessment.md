# Bug Assessment: Browser lanes unusable in live re-test — service down, registry empty, dynamic lane unwired

- **Slug**: chrome-not-desktop-automation
- **Created**: 2026-11-11T09:10:04Z
- **Source**: pasted text — the Dify agent's actual reasoning trace from the owner's live re-test of the weather prompt (conversation `69d3d6d9…`)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim, condensed)

The owner re-sent the weather prompt. The agent's trace shows: routed to the browser lanes correctly ("Chrome + search + read = web intent, not desktop automation" — **the no-response-test-playwright fix worked**), ran `skill_search` (nothing reusable), then `browser_status`: **dynamic lane UNREACHABLE — Playwright MCP on 127.0.0.1:3002 connection refused**; scripted registry **0 scripts**. The agent honestly relayed the recovery hint, refused to fabricate, and refused to self-run the recovery or fall back to launch+GUI typing — exactly per spec. But the user still got no weather: **the browser lanes have no usable execution path right now.**

## Symptom

A correct browser-lane routing ends in an honest-unavailable answer instead of a result: the dynamic server is down, and even when up the Dify agent has no tool to drive it (the trace: "I don't see mcp__PlaywrightMCP__* tools in my function list"). Expected: the lane executes the search and reports observed content.

## Reproduction

1. Ensure `:3002` is not listening (it is down now — probe returns nothing; schtasks shows the task **Status: Ready**, i.e. its process died since the 05:15 manual start).
2. Send the weather prompt → correct routing → `browser_status` error → honest unavailable answer. Reproduced by the owner at ~09:05 UTC.

## Suspected Code Paths

- **(1) Service down**: the `playwright-mcp-server` Scheduled Task's process died sometime after 05:15 (task Status: Ready = not running). `windows/playwright-mcp-task.xml` — no keep-alive beyond RestartOnFailure×3 (PT1M); if the process exits cleanly (like today's sidecar Exit-0), RestartOnFailure does NOT fire and the task sits Ready until next logon.
- **(2) Registry empty in-container**: `src/agentic_rag_mcp/server.py` `_browser_registry_root()` resolves to `Path(__file__).parent.parent.parent / "scripts" / "browser"` — in the container that is `/usr/local/scripts/browser`, which **does not exist** (verified: both candidate paths False). The 037 starter scripts ship in the repo only; neither the Dockerfile nor `deploy/docker_ops.py` MOUNTS carries them — so `browser_scripted_run` has 0 scripts in production forever.
- **(3) Dynamic lane unwired from Dify**: spec-037 research R3 wired PlaywrightMCP natively on the **Hermes** agent (25/25 tools, verified), but the **Dify** browser-lane node's tool list has no path to it — there is no `hermes_browser_task`-class sidecar tool, and `mcp__PlaywrightMCP__*` is not a Dify tool. The dynamic lane as published is instructionally described but **structurally unreachable**.

## Root Cause Hypothesis

Three independent gaps, all exposed by the first real end-to-end use of the lanes: (1) the host service died and its task has no recovery for clean exits; (2) the scripted registry was never containerized (the registry-root default only works on the dev checkout — my unit tests ran against the repo, the container has no copy); (3) the dynamic lane's design assumed the Dify agent could reach Hermes's Playwright tools, but no Dify-side tool exists to carry that directive. The 037 battery verified tools-surface (39 tools) but never validated lane executability in-container. Confidence: **high** — all three verified live within the last 10 minutes.

## Proposed Remediation

**Preferred** — three parts:
1. **(operational)** Restart the task now (`schtasks /run /tn playwright-mcp-server`) and make recovery robust: the lane's honest-unavailable envelope already names this; additionally add a `RestartInterval`-independent safety by having `browser_status`'s error text (which the agent relays) suggest the two-phase PowerShell lane as the confirmed way for the agent to start it FOR the user (state-changing → draft→confirm, consistent with the gates).
2. **(registry)** Ship the scripts into the container the way ppt-master ships: add `("scripts/browser", "/usr/local/scripts/browser")` to `deploy/docker_ops.py` MOUNTS (repo-relative, the `_PPT_MOUNT` precedent — no image rebuild needed) + update the mount-count pin to 6.
3. **(dynamic lane)** Add the missing sidecar tool `browser_dynamic_task(task, conversation_id)` — the hermes-channel directive pattern (033/034/030 style): it probes `browser_status` first, then sends the browsing directive to the Hermes agent, which owns the `mcp__PlaywrightMCP__*` tools, and relays observed content (web content stays untrusted per FR-008/019 — the Hermes-side instructions carry the law). Register in the DSL browser-lane tool list; A2 tool-scope pins updated.

**Alternatives**: for (3), register PlaywrightMCP as a Dify tool provider directly (rejected: bypasses the sidecar gate/audit layer and adds a second SSE hop); for (2), bake scripts into the image via Dockerfile (rejected: needs rebuild per script edit — the mount matches the ppt-master workflow).

**Files likely to change**:
- `src/agentic_rag_mcp/server.py` (browser_dynamic_task tool)
- `src/agentic_rag_mcp/browser_lanes/` (probe reuse; maybe a dynamic directive instructions block)
- `src/agentic_rag_mcp/deploy/docker_ops.py` (MOUNTS + pin)
- `dify/AGIAssistant/AGI_Assistant.yml` (new tool on the lane)
- `tests/unit/test_deploy_docker_ops.py`, `tests/integration/test_browser_a2.py` (pins)

**Tests to add or update**:
- Mount pin: 6 mounts incl. `scripts/browser:/usr/local/scripts/browser`
- Registry-in-container pin: registry root resolves to the mounted path in-container (integration)
- `browser_dynamic_task`: probe-down → honest unavailable envelope (no Hermes call); probe-up → directive sent, observed content relayed, audit rows written
- A2 scope: the dynamic tool joins the lane's allowed set

## Risks & Considerations

- (1) is a Windows host op (UAC not needed for `schtasks /run` of a user task — the earlier `Start-Process` route worked unelevated for /run; import needed UAC but running does not).
- (3) adds a 17th hermes-lane tool — additive only (Principle I); the DSL publish rides the next deploy window.
- Keep the dynamic tool read/browse-scoped: the browsing directive must never become a general "do anything on the desktop" channel — the Hermes-side instruction block must constrain to PlaywrightMCP browsing + reporting.
- The A2 untrusted-content law must be restated in the dynamic directive block (Hermes side), since Hermes reads page content now.

## Open Questions

- Why did the playwright-mcp-server process exit? (task Last Result / Windows event log — check during the fix pass; if it's a recurring playwright-mcp crash, that's its own follow-up.)