# Bug Verification: "open chrome search hong kong weather, show me the temperature today" — executes to a real weather answer

- **Slug**: `blocked-more-than-one-application-named-20261108`
- **Tested**: 2026-11-08T07:15+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original symptom — the exact request blocked as "more than one application named" — no longer reproduces: the full sequence now executes end-to-end, from the search typed into Chrome to the agent reading the live Google weather result and reporting today's actual Hong Kong temperature (27°C now, high 28°/low 23°, humidity 67%, wind 23 km/h).

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Environment precondition | `qwinsta` → session **Active**; WindowsMCP task started (SSE 200); gateway session refreshed (21 tools); `ControlStatus: ready, generation 1` | **pass** | The fix's environmental blocker (RDP disconnect) cleared; standard recovery path exercised: start task + one `hermes mcp test` |
| Reproduction (post-fix) — the exact request | live `hermes_launch_app("open chrome search hong kong weather , show me the temperature today")` | **pass** | `status ok` — *"Chrome launched fresh (profile picker appeared; opened the Raymond profile, window maximized and focused), then typed 'hong kong weather' into the address bar and pressed Enter. The Google weather result for Hong Kong is now showing… Today's temperature in Hong Kong: 27°C right now (Sunday 3:00 pm, sunny), with a high of 28°C and a low of 23°C. Humidity 67%, wind 23 km/h, no precipitation."* — 403 s, full audit entry |
| Gate unit matrix | `pytest tests/unit/test_hermes_launch_gate.py tests/unit/test_hermes_launch_tool.py` | **pass** | 44 passed — incl. the 5 new tests (bare-space search split, observe-clause tail, context nouns, "open search" ask-back, chaining bypass) |
| Regression suite | `pytest tests/unit` | **pass** | **346 passed** |
| Lint | `ruff check src/agentic_rag_mcp/hermes_launch_gate.py` | **pass** | clean |

## Output Excerpts

```
ControlStatus: {"state":"ready","generation":1,"wait_seconds":0.0}
live: "… typed 'hong kong weather' into the address bar and pressed Enter.
  The Google weather result for Hong Kong is now showing in the active
  window. Today's temperature in Hong Kong: 27°C right now… high of 28°C
  and a low of 23°C…" → status ok, LAUNCH: SUCCESS — 403 s
pytest tests/unit → 346 passed
```

## Residual Risks

- The RDP-disconnect fragility remains (WindowsMCP 0.8.8 dies/degrades on every disconnect): recovery is now proven routine — reconnect, `Start-ScheduledTask windows-mcp-server`, one `hermes mcp test WindowsMCP` — but a watchdog or a newer windows-mcp version is the durable answer (follow-up from the fix report)
- The observe step quality was good this run (the agent read the live weather widget) — that's one sample; watch natural occurrences
- Multi-step desktop turns take ~4–7 minutes (desktop-control idle waits + LLM iterations) — the standing latency floor
- The bare-space verb split means a hypothetical app literally named "search"/"find" would ask-back rather than launch — acceptable trade, pinned by test

## Recommendation

**Close the bug — verified end-to-end.** The exact blocked request from the report now runs to a real, live-data answer with the full audit trail; the gate matrix and complete suite hold; and the environmental recovery path is exercised and documented. The recurring WindowsMCP disconnect fragility is the remaining rough edge, already queued as its own follow-up lifecycle.