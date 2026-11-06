# Bug Fix: close/save tasks batch to one sub-minute script; MCP timeout raised; badge re-syncs

- **Slug**: `close-excel-wait-long-time`
- **Fixed**: 2026-11-06T05:55+00:00
- **Assessment**: ./assessment.md
- **Status**: applied (with one documented deviation on the deadline hunt)

## Summary

Save/close/quit tasks now batch unconditionally into ONE combined script (live-verified at 50 s vs the bug's 129 s + stream cut + full retry ≈ 3 min), the Dify MCP provider row's tool timeout was raised 30 → 300 s, and the chat UI's model badge re-syncs after every completed turn instead of freezing at its mount-time value (the "Deepseek" lie).

## Changes

| File / surface | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | CLOSE/SAVE tasks batch unconditionally: "save the file then close Excel (or Word, PowerPoint) is ONE combined script — save, close workbook, quit app, verify 0 processes, verify the file on disk — never separate steps", with the 129 s/deadline incident recorded in the text |
| Dify DB `tool_mcp_providers` (live) | `timeout` 30 → 300 | The agentic-rag MCP provider row; `sse_read_timeout` was already 300. **Not in git — re-apply after any `sync-tools`/provider re-sync if it resets** (note added to DEPLOY.md) |
| `ai-chat-landing/app/page.tsx` | modified | `/api/models/current` fetched on mount **and after every completed turn** (`busy → false` transition) — a long-lived tab no longer shows a stale model badge (it displayed Deepseek long after the lane was pinned to kimi-k3) |
| `tests/unit/test_hermes_office_tool.py` | modified | Guard: the close/save batching phrases pinned (incl. "129 s") |
| `DEPLOY.md` | annotated | The provider-row timeout note |

## Diff Highlights (optional)

```python
"CLOSE/SAVE tasks batch unconditionally: 'save the file then close Excel'
… is ONE combined script — save, close workbook, quit app, verify 0
processes, verify the file on disk — never separate steps; these turns
must finish well under a minute (… 4 separate steps took 129 s and
crossed the caller's tool deadline, killing the response stream)."
```

## Tests Added or Updated

- `tests/unit/test_hermes_office_tool.py::test_office_instructions_contain_attach_failure_protocol` — close/save batching guard added (332 unit tests pass)
- Chat UI: `pnpm typecheck` clean, `pnpm lint` 1 pre-existing warning in `scripts/stop-button-check.mjs` (not from this change)

## Local Verification

- `pytest tests/unit` → **332 passed**; `ruff` clean; `deploy redeploy` → ok: 4 steps
- **Live (05:50)**: create turn ok (visible-state rule held); then the user's exact complaint task — "save the file then close Excel" — completed as **ONE combined script** ("attached, saved, closed the workbook, Quit(), verified EXCEL.EXE count = 0, verified file on disk, 8465 bytes") in **50 s** through the direct channel, with 0 EXCEL.EXE after. No stream cut possible at that duration.
- Badge route probe: `/api/models/current` returns `moonshotai/kimi-k3` (correct); the UI now re-fetches it per turn.

## Deviations from Assessment

- **The exact ~120 s deadline location was not pinned.** Hunted thoroughly: the agent strategy (no timeout), the mcp SDK (session idle = 1800 s; no 120 constant), the plugin-daemon env (no tool-timeout vars), the api env (none), and the MCP provider row (30/300 — both allow >129 s reads). The observed cut (66 s OK → 129 s cut) is real but its source remains unlocated. The fix therefore takes the fully controllable path: keep every close/save turn far below the observed boundary (50 s live), and raise the one tunable knob found (provider timeout 30→300). If cuts recur on slow turns, instrument next: add sidecar-side disconnect logging to timestamp the exact cut and its initiating side.
- The badge fix was expanded slightly from the assessment's "fallback fix" to a per-turn re-sync, since the route itself was returning the correct model — the staleness was the mount-only fetch.

## Follow-ups

- Watch natural turns for any recurrence of "incomplete chunked read" — if it appears on a sub-minute turn, the deadline hypothesis is wrong and the sidecar disconnect instrumentation (above) becomes the next bug's first step
- The DEPLOY.md note covers the DB-row timeout re-application after provider re-syncs
- The user should refresh the chat tab once to pick up the new badge code; after one completed turn the badge will read kimi-k3
