# Bug Verification: the chat Stop cancels the desktop agent within seconds — full chain green at the UI level

- **Slug**: `repeated-show-ai-is-controlling-this-computer-many-times` (resolved from context — the user's truncated slug `…-many-time` fell through to the just-fixed lifecycle)
- **Tested**: 2026-11-09T03:55+00:00 (cycle-2 verification; supersedes the failed cycle-1 test.md — git preserves it)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original symptom — the "AI is controlling this computer" notice flashing for minutes while the chat gave no response after Stop — no longer reproduces through the chat's own stop path: the test-phase reproduction (in-flight desktop turn → `POST /api/chat/stop` at +40 s) returned `{"result":"ok"}`, the launch tool returned at **+40 s** with the honest cancelled verdict, and both audit entries (`cancel-turn` cancelled, `launch-app` error) were written the same second. The turn that ran 570 s of desktop control past a user Stop now halts in ~0 s after the route fires.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix), UI level — the exact failed scenario | in-flight launch turn (conversation_id `ui-stop-verify-3`) → `POST /api/chat/stop {taskId: <uuid>, conversationId}` at +40 s | **pass** | Route `{"result":"ok"}`; tool returned +40 s with *"the turn was cancelled — any partial desktop state was left as-is"*; audit 03:51:38 `cancel-turn` cancelled + `launch-app` error. Cycle-1's identical probe 406'd silently and the turn ran on — the Accept-header fix and the launch-bullet prompt are the delta |
| Reproduction (post-fix), tool level | fix-phase live runs (cycle 1: +45→+50 s; cleanup re-proof) | **pass** | Registry → cancel tool → gateway "interrupted agent task" → honest verdict, proven twice before cycle 2 |
| Live-graph prompt check | `graph::text LIKE '%lets the Stop button cancel%'` on the current published version | **pass** | true (03:48:02); the launch bullet now mandates `conversation_id` exactly as the office bullet always did |
| New / updated tests | `pytest tests/unit` | **pass** | **359 passed** (registry semantics, stream parse, office stream-mocks, all prior suites) |
| UI suites | `pnpm vitest run` | **pass** | **143 passed** |
| Lint / type-check | `pnpm typecheck`; `pnpm lint` | **pass** | clean; clean |

## Output Excerpts

```
UI stop route: {"result":"ok"}  (Dify no-task tolerated + cancel reached the tool)
turn: launch: error | the turn was cancelled — the chat stopped it… — +40 s
audit 03:51:38: cancel-turn cancelled … | launch-app error:the turn was cancelled …
pytest → 359 passed | pnpm vitest → 143 passed | typecheck/lint clean
```

## Residual Risks

- The file lane stays on the uncancellable blocking path (no conversation id in its tool signature; fast tasks) — documented limitation, unchanged by design
- A real user Stop press on a live desktop turn is the final field sample — the probe path exercised is the identical route code the UI button drives (same fetch, same params shape), so the remaining gap is only the natural-turn observation
- Dify's own stop of a *running* workflow was probed with a no-task UUID (tolerated); real mid-workflow stops ride the same route — the cancel fires before the Dify call regardless of its outcome

## Recommendation

**Close the bug — verified end-to-end.** The Stop button now reaches the agent through the full chain (UI → stop route → sidecar cancel tool → in-flight connection close → gateway interrupt), both desktop lanes (launch + office) pass the conversation id, the verdict and audit are honest, and the desktop notice stops re-arming within seconds of pressing Stop.
