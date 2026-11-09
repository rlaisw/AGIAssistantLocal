# Bug Fix: the chat Stop now reaches the agent — the gateway interrupts the desktop turn within seconds instead of running for minutes

- **Slug**: `repeated-show-ai-is-controlling-this-computer-many-times`
- **Fixed**: 2026-11-09T03:45+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — live-verified end-to-end at the tool level

## Summary

The launch and office lanes now run their gateway calls in **stream mode** with the connection registered per conversation, and a new `hermes_cancel_turn` tool closes it — the gateway's SSE branch then **interrupts the running agent** (its own disconnect handler, verified in its code and live). The chat UI's Stop button extends its stop route to call the cancel tool through the sidecar, so pressing Stop now halts the desktop work in seconds instead of the desktop notice flashing for minutes with no response. The blocking-JSON path (measured) ran turns to natural completion despite client disconnect; the SSE path is the platform's cancellable lever.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | New: `_INFLIGHT` registry (per-key `httpx.Client`, lock-guarded, owner-checked unregister), `cancel_inflight(key)` (closes the registered client), and `run_task_stream` — a stream-mode `POST /v1/responses` (`"stream": true`) that parses `response.completed`/`response.failed` into the same `{"ok", "output"/"error"}` contract; aborted connections map to an honest `error:the turn was cancelled — the chat stopped it; any partial desktop state was left as-is`; registered in a `finally` |
| `src/agentic_rag_mcp/server.py` | modified | `_run_hermes` helper: with a conversation key → `run_task_stream` (cancellable); without (battery, probes, file lane) → the unchanged blocking path. Launch and office lanes pass their conversation id; the launch tool gains an optional `conversation_id` param (empty = uncancellable, all old callers byte-identical). New MCP tool **`hermes_cancel_turn(conversation_id)`**: closes the in-flight connection, writes an audit entry, returns `{status: ok|noop, cancelled}` (noop = completion race) |
| `ai-chat-landing/app/api/chat/stop/route.ts` | modified | Accepts an optional `conversationId`; after the Dify stop, fire-and-forget calls the sidecar's `/mcp` → `hermes_cancel_turn` (3-step stateless streamable-HTTP dance, 5 s timeout, non-fatal) |
| `ai-chat-landing/app/page.tsx` | modified | The generation record tracks `convDifyId` (set at send time and on the `task` event); the stop POST passes it |
| `tests/unit/test_hermes_launch_tool.py` | +2 tests | Registry semantics (cancel closes once, idempotent re-close, unknown key = race, owner-checked unregister) and the response-envelope parse; the 540 s budget pin updated to the new call shape |
| `tests/unit/test_hermes_office_tool.py` | mocks extended | All six run_task monkeypatch sites also patch `run_task_stream` (the office lane is stream-mode now) |
| Live sidecar | redeployed | `sync-tools 26→27` (the new tool); all lanes served from the new code |

## Diff Highlights (optional)

```python
# hermes_client.py — the Stop lever
def cancel_inflight(key: str) -> bool:
    with _INFLIGHT_LOCK: client = _INFLIGHT.get(key)
    if client is None: return False
    client.close()   # gateway SSE branch: "SSE client disconnected; interrupted agent task"
    return True
```

## Tests Added or Updated

- `test_cancel_inflight_registry_semantics`, `test_run_task_stream_parses_response_completed` (via `_extract_text` on the completed envelope), plus the six office mocks — **359 passed** (was 357); UI: 143 passed; typecheck clean; ruff clean on the changed files

## Local Verification

- **Decisive disconnect measurements** (drove the design): the blocking-JSON path survived a mid-run client abort to natural completion (+139 s, no `run.cancelled`); the SSE path's disconnect handler interrupts the agent (`_abandon_agent_task` → "SSE client disconnected; interrupted agent task", gateway source 1198-1199) — so the lanes must run stream-mode to be stoppable
- **Live end-to-end (03:36:31–03:37:21)**: a launch turn with conversation id `cancel-live-verify-2` was in flight; at +45 s `hermes_cancel_turn` returned `{'status': 'ok', 'cancelled': True}`; **the launch tool returned at +50 s** with the honest cancelled verdict — total 50 s instead of the turn's natural 150 s+. The gateway log confirms: *"SSE client disconnected; interrupted agent task resp_f3375926…"*. Both audit entries written (`cancel-turn` at 03:37:16, `launch-app` error at 03:37:21)
- First live attempt surfaced a parser fact (my test task "open notepad and wait…" hit the honest MULTI ask-back — "wait" is not a recognized followup verb; retried with a well-formed task)

## Deviations from Assessment

- The assessment proposed the control socket or `/v1/runs/{id}/stop` as the lever; the investigation found a **better one**: the gateway's own SSE disconnect handler interrupts the agent (no run-id plumbing needed — the connection itself is the handle). The blocking-JSON disconnect test (natural completion, measured) ruled out the naive abort and justified the stream-mode switch.
- The file lane stays on the blocking path (its tool signature has no conversation id; its tasks are fast) — documented limitation, stop-scoping is per-conversation for the two desktop-control lanes where the bug lived.

## Follow-ups

- A natural user-driven Stop on a live desktop turn completes the verification at the UI layer (the stop route's sidecar call is fire-and-forget; its failure is logged client-side but never blocks the chat stop)
- The office lane's cancel scoping uses the same conversation id the chatflow passes — no chatflow change needed; if a future spec adds conversation ids to the file tool, its lane becomes cancellable by deleting its blocking fallback in `_run_hermes`
- The MCP tool count change (26→27) was synced by the redeploy; future Dify console visibility of `hermes_cancel_turn` is harmless (the agent prompt does not mention it, and calling it cancels only that conversation's own turn)
