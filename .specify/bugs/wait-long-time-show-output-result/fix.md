# Bug Fix: done-at-`message_end` — the UI spinner clears at answer completion, immune to held upstream streams

- **Slug**: `wait-long-time-show-output-result`
- **Fixed**: 2026-11-09T03:05+00:00
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The chat route now finalizes the UI stream (`done` + close + upstream cancel) the moment Dify sends `message_end` — the terminal answer-complete event — instead of continuing to wait for the upstream body to close, which can lag indefinitely (plugin-daemon holds, tool-time cuts). The "Thinking" spinner now clears exactly when the answer is final.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `ai-chat-landing/app/api/chat/route.ts` | modified | `message_end` case: after forwarding sources, sets a `finalized` flag, emits `done`, closes the controller, cancels the upstream reader, returns. The `finally` closes the controller only when not already finalized (double-close guard). Error and cut-stream paths unchanged (they end via body close / throw as before) |
| `ai-chat-landing/app/api/chat/route.test.ts` | added | 2 route tests: done emitted at `message_end` while the upstream body **never closes** (the held-stream specimen), and done still relayed on plain upstream close without `message_end` (cut-stream compatibility) |
| `ai-chat-landing/vitest.config.ts` | modified | include gains `app/api/**/*.test.ts` — route handlers are plain `(Request) => Response` functions, directly testable in vitest (the repo's first route test) |

## Diff Highlights (optional)

```ts
case "message_end": {
  …sources as before…
  // message_end is Dify's terminal answer-complete event — finalize the UI now
  finalized = true
  send({ type: "done", conversationId: difyConversationId })
  controller.close()
  reader.cancel().catch(() => {})
  return
}
…
} finally {
  if (!finalized) controller.close()
}
```

## Tests Added or Updated

- `app/api/chat/route.test.ts` — the held-stream specimen (upstream never closes; done must still arrive) and the cut-stream fallback; 143 UI tests pass total (141 existing + 2 new)

## Local Verification

- `pnpm vitest run` → **143 passed**; `pnpm typecheck` → clean; `pnpm lint` → 1 pre-existing warning only (scripts/stop-button-check.mjs, unchanged)
- **Live through the dev server** (`POST /api/chat` "Say OK."): chunks streamed, then `{"type":"done","conversationId":"1464…"}` arrived — the dev server hot-reloaded the route and the full path works end-to-end
- The spinner-clear timing on a simple turn is unchanged by design (measured in the assessment: body close follows `message_end` promptly there); the fix's value shows on held/cut streams, where the spinner previously out-lagged the answer by the whole hold

## Deviations from Assessment

- None — the preferred remediation applied exactly (done at `message_end` + close + cancel; no UI change; sources ordering preserved).

## Follow-ups

- The mid-turn narration behavior (answer text visible while the agent continues iterating — the honest "report each step" design) is unchanged and correct; the remaining perceived latency is the known turn-duration floor (the deterministic-executor follow-up)
- Watch one natural ceiling-cut turn: the cut path now ends without `message_end` via upstream close → `done` — the same relay as before, no regression expected
- The vitest include extension opens route-level testing for future API-route fixes; keep route tests in `app/api/**/route.test.ts` siblings
