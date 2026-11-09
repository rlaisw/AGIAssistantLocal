# Bug Verification: the Stop→cancel chain works at the tool level but the UI route's MCP dance 406s — fix incomplete at the last hop

- **Slug**: `repeated-show-ai-is-controlling-this-computer-many-times`
- **Tested**: 2026-11-09T03:50+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: **failed** — the tool-level chain is verified end-to-end (twice), but the test phase found the **UI stop route's sidecar call is broken** (406) and the launch lane's chat wiring is missing the prompt instruction — both at the last hop, so pressing Stop in the chat today still does not cancel a desktop turn.

## Summary

The agent-interrupt mechanism is real and verified twice at the tool level (cancel tool → connection close → gateway "interrupted agent task" → honest cancelled verdict at +50 s instead of minutes). But the UI-level reproduction found two gaps between the Stop button and the verified tool: (1) the stop route's `cancelSidecarTurn` MCP dance sends no `Accept` header — the sidecar's streamable server rejects every step with **406** ("Client must accept both application/json and text/event-stream") and the fire-and-forget catch swallows it; (2) the chatflow prompt's launch bullet ("Call hermes_launch_app(task)") does not pass the new `conversation_id` param, so the agent never registers chat-side launch turns as cancellable. The symptom would still reproduce for a user pressing Stop today.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix), **tool level** | launch turn with conversation_id `cancel-live-verify-2` + `hermes_cancel_turn` at +45 s (fix phase) | **pass** | Tool returned +50 s with the honest cancelled verdict; gateway: "SSE client disconnected; interrupted agent task"; both audit entries written |
| Reproduction (post-fix), **UI level** | launch turn with conversation_id `ui-stop-verify`; `POST /api/chat/stop {taskId, conversationId}` at +40 s (this phase) | **FAIL** | The route returned `stop failed: Invalid task ID: expected a UUID` (my fake taskId — the real-flow taskId is a UUID, so this part is a probe artifact) — but the decisive evidence is below |
| UI route's sidecar reach | reproduce the route's exact fetch (no `Accept` header) → `initialize` | **FAIL — root cause pinned** | `406 {"error":{"message":"Not Acceptable: Client must accept both application/json and text/event-stream"}}` — every step of the route's 3-POST dance 406s and the `.catch(() => {})` swallows it; **no `cancel-turn` audit entry for `ui-stop-verify`** until the cleanup cancel (which used the correct header and worked immediately: `{'status': 'ok', 'cancelled': True}`, gateway "interrupted agent task resp_1fa7a…") |
| Launch-lane chat wiring | DSL prompt grep | **gap** | Office bullet: "ALWAYS pass conversation_id exactly as '{{#sys.conversation_id#}}'" ✓; launch bullet: "Call hermes_launch_app(task)" — **no conversation_id**, so chat-side launch turns run the uncancellable blocking path (the fix made the param optional, but nothing tells the agent to pass it) |
| New / updated tests | `pytest tests/unit` | **pass** | **359 passed** (registry semantics, stream parse, office stream-mocks) |
| UI suites | `pnpm vitest run` + `typecheck` | **pass** | 143 passed; typecheck clean |

## Output Excerpts

```
route's dance (no Accept header): 406 Not Acceptable — "Client must accept both
  application/json and text/event-stream"  ← cancel never reached the tool
cleanup cancel (correct header): {'status': 'ok', 'cancelled': True} →
  gateway: "SSE client disconnected; interrupted agent task resp_1fa7a…"
  audit 03:46:25 cancel-turn cancelled ✓  (tool-level chain proven AGAIN)
tool-level (fix phase): cancel +45s → verdict +50s, "interrupted agent task"
pytest → 359 passed | pnpm vitest → 143 passed
```

## Residual Risks

- The tool-level chain (registry → cancel tool → gateway interrupt → honest verdict) is fully proven — the remaining work is exactly two one-liners: the `Accept` header in `cancelSidecarTurn`'s fetch calls, and a prompt bullet telling the agent to pass `conversation_id` to `hermes_launch_app` (publish via the console path, same as prior prompt cycles)
- The stop route's Dify-stop call also surfaced a probe artifact: with a non-UUID taskId Dify returns 400 and the route 502s — real Stop presses carry a real UUID, so this is informational, not a defect; but the conversationId cancel fires before the Dify call, so the cancel would have fired anyway once the header is fixed
- The office lane is fully wired (prompt passes conversation_id) — once the Accept header is fixed, office turns are stoppable through the chat today; launch turns need the prompt bullet too

## Recommendation

**Re-run `/speckit.bug.fix` — the fix is one Accept header and one prompt bullet short of complete.** The heavy machinery (stream-mode lanes, registry, cancel tool, gateway interrupt, UI plumbing) is built and proven live twice at the tool level; the test phase pinned the last-mile defects precisely: (1) add `"Accept": "application/json, text/event-stream"` to `cancelSidecarTurn`'s fetches in `stop/route.ts`; (2) update the hermes_agent node's launch bullet to "Call hermes_launch_app(task, conversation_id)… ALWAYS pass conversation_id exactly as '{{#sys.conversation_id#}}'" via the export→patch→publish console path. Then the UI-level reproduction above should turn green with a real turn.
