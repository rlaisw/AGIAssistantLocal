# Bug Verification: turn timing profile — every desktop turn self-benchmarks, verified live end-to-end

- **Slug**: `every-steps-hold-long-time`
- **Tested**: 2026-11-09
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The fix holds live: a real desktop turn through the live instrumented sidecar (minimal `open notepad` launch, stream path, real gateway, real Windows launch — Notepad PID 24868) returned its verdict with the `TIMING:` line (`total 20.4s | first event +0s | 123 events | gap 4.7s @+4.7s … | gap 2.8s @+10.1s …`) and the audit entry gained `duration_s: 20.4` plus the full profile — the pre-fix symptom (no timing recorded anywhere in the pipeline) no longer reproduces. The assessment's open experiment is also answered: the gateway streams live intermediate SSE events at high cadence (123 events in a 20.4 s turn), so the benchmark has full resolution. No regressions: hermes suites 43/43, full suite's only failures proven pre-existing.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix, LIVE) | `hermes_launch_app("open notepad", conversation_id="bench-verify-1109")` via MCP streamable-http against the live sidecar :28080 → real gateway → real desktop | **pass** | Real desktop turn, wall 20.5 s, status ok, `LAUNCH: SUCCESS`; tool `result` ends with the `TIMING:` line; the identical code path a chat turn takes (launch lane, stream mode, conversation key). The pre-fix behavior — no timing anywhere — did not reproduce. |
| Audit surface (LIVE) | read last `audit.jsonl` entry after the probe | **pass** | Entry keys now include `duration_s: 20.4` + `timing` (`first_event_s: 0.0`, `event_count: 123`, 2 top gaps with event-type labels) alongside the unchanged legacy fields (`ts`/`decision`/`operation`/`outcome`). |
| New / updated tests | `pytest tests/unit/test_hermes_launch_tool.py tests/unit/test_hermes_office_tool.py tests/unit/test_hermes_audit.py -q` | **pass** | 43 passed (7 new), re-run fresh in this phase. |
| Regression suite | `pytest tests/ -q` (fix phase) + stashed re-run of the 5 failures | **pass** | 502 passed / 5 failed — all 5 proven pre-existing by re-running them on a stashed (pre-change) tree: identical 4 fail + 1 flaky-in-full-run (antv live-chart) that passes standalone on both trees. Hermes paths fully green. |
| Lint / type-check | `ruff check <6 changed files>` | **pass (with notes)** | 31 findings pre-existing on these exact files (ruff is not an enforced gate in this repo — AGENTS.md prescribes pytest for python; the UI has its own pnpm checks) → 35 post-change: **+4 new, all cosmetic, all in the new TEST code** (2× FLY002 join-style, 1× ISC004, 1× RUF059 unused `cfg` unpack; 3 are "unsafe-fix" categories). This verification command must not modify code, so they are recorded, not fixed. |

## Output Excerpts

```
MCP tool result (live probe, wall 20.5 s):
  "result": "…Notepad started fresh on the Windows host, confirmed running as
   PID 24868 with a visible window.\n\nLAUNCH: SUCCESS\n\nTIMING: total 20.4s
   | first event +0s | 123 events | gap 4.7s @+4.7s before
   response.output_item.added | gap 2.8s @+10.1s before response.output_item.done"

audit.jsonl (last entry):
  duration_s: 20.4   timing: {"total_s": 20.4, "first_event_s": 0.0,
  "event_count": 123, "gaps": [{"gap_s": 4.7, "at_s": 4.7,
  "event": "response.output_item.added"}, {"gap_s": 2.8, "at_s": 10.1,
  "event": "response.output_item.done"}]}

pytest hermes suites: 43 passed in 2.67s
```

## Residual Risks

- The **Dify relay layer** was not exercised in this probe (sidecar-direct call): the DSL's honest-relay rules say "report what the tool returned", but kimi-k3 may still summarize the TIMING line away unprompted — the assessment's optional DSL bullet ("include the TIMING line when asked why it was slow") is the remedy if the user's next real chat turn elides it.
- The live turn was a **minimal launch** (20.4 s), not a minutes-long combined turn — the code path is identical and the profile is size-independent, but the gap *anatomy* of a heavy turn (LLM iteration vs gated action vs consent idle-wait) is exactly the data the instrument will now collect on the user's next real desktop request; that reading feeds the deterministic-executor spec baseline.
- 4 cosmetic ruff nits in the new test code (+31 pre-existing in these files) — fold into the next fix cycle.
- The probe left a Notepad window open on the user's desktop (harmless, closable).
- Keepalive progress pings (Dify transport path) unchanged and unmodified — verified in their own lifecycle (`read-tool-response-failed`).

## Recommendation

Close the bug — verified end-to-end live: the timing data that the pipeline used to discard now surfaces in the tool result (the relay's view), the audit log (the historical record), and at high event resolution (123 events / 20.4 s). On the user's next heavy combined desktop turn, the `TIMING:` line will show exactly where the minutes go — collect that reading as the baseline for the deterministic-executor spec, and add the DSL bullet only if the relay turns out to elide the line.
