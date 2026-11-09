# Bug Fix (cycle 2): the last two wires — Accept header in the stop route, conversation_id in the launch bullet

- **Slug**: `repeated-show-ai-is-controlling-this-computer-many-times`
- **Fixed**: 2026-11-09T03:55+00:00 (supersedes the cycle-1 fix.md — its machinery (stream lanes, registry, cancel tool, gateway interrupt) stands; git preserves cycle 1)
- **Assessment**: ./assessment.md
- **Status**: applied — the failed UI-level reproduction now passes end-to-end

## Summary

The test phase pinned two last-mile breaks; both are fixed and the full UI-level chain is verified: an in-flight launch turn cancelled through the chat's own stop route — `{"result":"ok"}` at +40 s, the tool returned at **+44 s** with the honest cancelled verdict, and both audit entries written. The Accept header was the 406 root cause; the prompt bullet makes the agent pass the cancellable conversation id to every launch call.

## Changes

| File / surface | Change | Notes |
|------|--------|-------|
| `ai-chat-landing/app/api/chat/stop/route.ts` | modified | `cancelSidecarTurn`'s fetches now send `Accept: application/json, text/event-stream` — the streamable MCP server 406s without it (root cause pinned in the test phase) |
| Live Dify workflow (`hermes_agent` node prompt) | modified | Launch bullet: "Call hermes_launch_app(task, conversation_id)… **ALWAYS pass conversation_id exactly as '{{#sys.conversation_id#}}'** (it lets the Stop button cancel the turn; a turn without it cannot be stopped)" — applied export→patch→publish via the console API; live-graph check `LIKE '%lets the Stop button cancel%'` → **true** (03:48:02); repo artifact synced |

## Diff Highlights (optional)

```ts
headers: {
  "Content-Type": "application/json",
  Accept: "application/json, text/event-stream",  // the 406 root cause
},
```

## Tests Added or Updated

- No new unit tests (config-level one-liners; the UI-level reproduction is the behavioral proof); all existing suites stay green

## Local Verification

- `pnpm typecheck` → clean
- **UI-level reproduction (03:48:56–03:49:40)** — the exact scenario that failed in the test phase: launch turn in flight with conversation_id `ui-stop-verify-2` → `POST /api/chat/stop {taskId: <uuid>, conversationId}` at +40 s → **`{"result":"ok"}`** (Dify no-task tolerated + the cancel reached the sidecar this time) → the launch tool returned at **+44 s** with *"the turn was cancelled — the chat stopped it; any partial desktop state was left as-is"*; audit: `cancel-turn` cancelled at 03:49:36, `launch-app` error at 03:49:40. The turn that previously ran to natural completion (minutes) now stops in ~4 seconds from the UI's own stop button path

## Deviations from Assessment

- None — this cycle applied precisely the two one-liners the failed verification pinned.

## Follow-ups

- `/speckit.bug.test` re-run should turn green: re-run the UI-level reproduction (above) plus the suites; a natural user Stop press on a live desktop turn is the final field sample
- The office lane's prompt bullet already passed conversation_id — both desktop lanes are now stoppable through the chat
- Tool count (27) and the sync were already live from cycle 1; no redeploy needed this cycle (the sidecar code is unchanged)
