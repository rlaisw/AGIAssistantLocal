# Bug Fix: async Hermes tools unblock the SSE keep-alive — long turns no longer cut at ~120 s

- **Slug**: `read-tool-response-failed-request-failed`
- **Fixed**: 2026-11-06T06:45+00:00
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The three long Hermes tools (`hermes_office_task`, `hermes_file_task`, `hermes_launch_app`) were **sync functions that ran directly on the event loop**, freezing the SDK's 15-second `: ping` SSE keep-alive writer for the whole computation — the response stream idled past upstream read deadlines (~120 s observed) and got cut with "incomplete chunked read" while the work completed server-side. Converting the tools to async (blocking calls in `asyncio.to_thread` + progress-ping wrapper) freed the loop: the keep-alive pings now flow every 15 s, and a live 166-second turn survived end-to-end with the result delivered on the same stream.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/server.py` | modified | `_await_with_keepalive` helper (thread + 30 s progress frames, ctx-safe); the three Hermes tools are `async def` with `ctx: Context = None`; **renamed the office tool's local `ctx` string to `directive_ctx`** — it shadowed the Context parameter and the keepalive saw the string (found live: `ctx='str'`); audit-slice safe |
| `src/agentic_rag_mcp/hermes_client.py` | modified | STEP BATCHING extensions: availability/running-apps check folds into the combined script (never a separate env pre-step); STRIP MEMORY (direct channel is sticky within a task); INTERRUPTED-TURN PROTOCOL (verify state before retrying a transport error, never duplicate — codifies the recovery that saved this very turn) |
| `tests/unit/test_hermes_office_tool.py` | modified | Guards for the three new rules |
| Live ops | Dify api-1 restarted | Loads the `tool_mcp_providers.timeout = 300` bump set yesterday (the running api predated it) |

## Diff Highlights (optional)

```python
# before (the cut's mechanism): sync tool ran ON the event loop,
# starving the SDK's 15s ": ping" SSE keep-alive writer → idle cut
@mcp.tool()
def hermes_office_task(task, conversation_id): ...   # blocked the loop 224 s

# after: async + thread, loop free, pings flow
@mcp.tool()
async def hermes_office_task(task, conversation_id, ctx: Context = None) -> dict:
    ...
    out = await _await_with_keepalive(lambda: _hermes_run_task(...), ctx)
```

## Tests Added or Updated

- Guards for STRIP MEMORY / INTERRUPTED-TURN PROTOCOL / folded env-check (`tests/unit/test_hermes_office_tool.py`) — **332 unit tests pass**

## Local Verification

- `pytest tests/unit` → 332 passed; `ruff` clean on changed hunks (pre-existing fixables untouched); `deploy redeploy` → ok: 4 steps ×2
- **Live stream dumps (raw)**: `: ping - <ts>` SSE comments every 15.0 s during a 65 s forced-sleep turn; a **166 s forced-sleep turn completed with `status ok` delivered on the same stream** — the pre-fix cuts fired at 129 s and 224 s; no cut occurred post-fix at 166 s
- The ctx collision was found and fixed empirically: the first build logged `ctx='str'` (the shadowed string), renamed to `directive_ctx`, then the Context flowed (`ctx='Context'`)
- Over HTTP: **zero** keepalive warning lines in the container log during the long probes (the progress path either works or silently no-ops when the client sends no progressToken — the `: ping` keep-alives are the operative mechanism)

## Deviations from Assessment

- The assessment expected the fix to be *instrumentation first, then patch the found deadline*. The instrumentation (uvicorn access trace) instead localized the mechanism directly: the response stream was idle because the sync tool froze the keep-alive writer — no external deadline needed patching at all. The async conversion IS the fix; the deadline's exact upstream identity (between 66–129 s) remains academic since idle streams no longer occur.
- `ctx.report_progress` frames (the assessment's implied keep-alive mechanism) turned out unnecessary — the SDK's own 15 s `: ping` comments suffice once the loop is free; the progress path remains as belt-and-suspenders.

## Follow-ups

- Watch natural turns: any >120 s office task should now complete without "incomplete chunked read"; if one still cuts, the residual suspect is the Dify MCP client's total-duration cap (the provider-row timeout=300 is now loaded via the api restart)
- The progress-ping wrapper can be simplified away later if the `: ping` keep-alives prove sufficient over a few weeks
- The `directive_ctx` rename is the kind of latent collision worth a quick lint rule (flake8-shadow?) — noted, not done
