# Bug Assessment: every step holds a long time — no time benchmark anywhere in the desktop-task pipeline, so nobody can see where the minutes go

- **Slug**: `every-steps-hold-long-time`
- **Created**: 2026-11-09T05:00+00:00
- **Source**: pasted text (user request + the relay's Reasoning trace from the latest "open chrome and type hong kong temperature today" turn)
- **Verdict**: valid — as a **diagnosability gap**, not a new latency mechanism: the wait itself is the documented desktop latency floor (closed earlier today in `waiting-long-long-time-at-ai-is-controlling-this-computer-stage`), but the pipeline records **zero timing data** anywhere, and the user explicitly asks for a benchmark to find out what is happening. This is the measurement instrument the prior closure lacked.
- **Severity**: low — turns still complete with honest, verified results; the harm is that the minutes are opaque to the user, the relay, and the audit trail (today the user pressed Stop at 04:50:04 mid-hold out of that opacity). High value as the prerequisite baseline for the deterministic-executor spec.

## Report (verbatim or summarized)

> "every steps hold long time … help to add time benchmark to find out what's happened, here is the last time output:"
>
> Pasted: the Dify relay's Reasoning panel for the latest combined turn — it reasons about passing the FULL task text to `hermes_launch_app` with `conversation_id`, then: "The task completed successfully. Chrome was opened, the search was typed and executed, and the agent read the temperature from the results. Let me relay this honestly to the user." — i.e. the entire multi-minute turn is one opaque hold in the chat, then a single verdict; no per-step or duration information surfaces anywhere.

## Symptom

During a combined desktop turn the chat holds silent for minutes (only the WindowsMCP notice cycles on the desktop), and when the tool returns, neither the tool result, the relay's summary, nor the audit entry says **where the time went**. Expected (the user's ask): a time benchmark — turn duration plus a step/gap breakdown — produced by every desktop turn so "what's happened" is answerable without manual multi-log forensics.

## Reproduction

1. Ask a combined desktop turn ("open chrome and type hong kong temperature today"); the bubble holds for minutes with no chat feedback (documented architectural limit: Dify MCP tool calls are opaque).
2. When the verdict arrives, inspect everything recorded: the tool result text, the relay output, and the audit entry — none contains a duration, a first-token latency, or any gap/step timing.
3. Today's audit timeline (`~/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl`) shows the pattern and the cost of the opacity: 04:21:02 executed (the 128 s turn), 04:28:32 executed (the 274 s turn), **04:50:04 cancelled** (user pressed Stop mid-hold), 04:53:39 executed (the re-ask — the turn behind the pasted trace). Durations had to be reconstructed by hand in the prior assessment exactly because no layer records them.

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_client.py:328-350` — `run_task_stream`'s event loop already **receives every live SSE event** across the whole turn (the stream is live: cancel-by-disconnect interrupts the agent) but consumes only `response.completed`/`response.failed` — every intermediate event, i.e. the timing data, is parsed and discarded.
- `src/agentic_rag_mcp/hermes_client.py:222-262` — blocking `run_task` returns only final text; no elapsed time.
- `src/agentic_rag_mcp/server.py:889-917` — `hermes_launch_app` envelope (`result`, `target`) carries no duration.
- `src/agentic_rag_mcp/hermes_audit.py:36-46` — each JSONL entry gets a single verdict-time `ts`; turn duration is not a field (only inferable by differencing consecutive entries).
- `src/agentic_rag_mcp/server.py:733-761` — `_await_with_keepalive` already tracks `elapsed` for progress pings, then drops it.

## Root Cause Hypothesis

**High confidence.** The timing data already flows through the sidecar and is thrown away at every layer: the gateway streams SSE events for the whole desktop turn, `run_task_stream` discards all non-terminal events, the tool envelopes carry only final text, and the audit writes one verdict timestamp. The chat cannot show progress mid-turn (opaque Dify tool calls — documented in two prior closures), so the post-hoc breakdown in the tool result + audit is the only in-band surface — and today nothing populates it, which is why every prior timing reconstruction was manual cross-log forensics.

## Proposed Remediation

**Preferred**: an in-band **turn timing profile**, three small pieces:

1. `hermes_client.py::run_task_stream` — timestamp each parsed SSE event (`time.perf_counter()`); accumulate a compact profile: `total_s`, `first_event_s`, `event_count`, and the top-N longest inter-event gaps (offset into the turn, gap length, and the event type / short text snippet at each side, so gaps attribute to LLM iteration vs desktop action vs consent idle-wait). Return it as a `timing` dict alongside `ok`/`output` (also on the error/cancel/timeout paths, so stopped turns are benchmarked too).
2. `server.py` — `hermes_launch_app` and `hermes_office_task` (both share `_run_hermes`) append a compact human-readable `TIMING: total 274s | first event +6.2s | 41 events | longest gap 23.8s @+86s "…verifying focus…"` line to the tool result text, so the relay LLM sees it and reports it honestly (existing honest-relay rules already say "report what the tool returned"; no DSL publish required for the minimal version).
3. `hermes_audit.py::write_attempt` — optional `duration_s` + `timing` fields (backward-compatible JSONL addition; old readers ignore unknown keys), populated from the same profile, so every desktop turn is queryable historically.

**Alternatives**:
- Post-hoc cross-log correlation (gateway log, `~/.windows-mcp/` wrapper logs, audit-entry deltas) — works but manual, cross-host, and outside the repo's control; keep as the fallback for gap *anatomy*, not as the benchmark.
- Mid-turn progress streaming into the chat — architecturally blocked (opaque Dify MCP tool calls), rejected in two prior lifecycles; the TIMING line is the honest post-hoc version of it.

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_client.py`
- `src/agentic_rag_mcp/server.py`
- `src/agentic_rag_mcp/hermes_audit.py`
- `tests/unit/test_hermes_launch_tool.py`
- `tests/unit/test_hermes_office_tool.py`

**Tests to add or update**:
- `test_hermes_launch_tool.py` (gateway-mock harness already exists there for the cancel lifecycle): feed a fake SSE event sequence with known pacing → assert the profile (`total_s`, `first_event_s`, gap list ordering/truncation), the `TIMING:` line in the returned envelope, and the audit entry's new fields; assert the cancel path still returns a profile (stopped turns are benchmarked).
- `test_hermes_office_tool.py`: same assertions through the office lane's shared `_run_hermes` path.
- `hermes_audit` unit assertions: old entries without the new fields still parse; new fields round-trip.

## Risks & Considerations

- **Unknown event cadence** (the experiment itself): if the gateway emits only boundary events, the profile degrades to `total_s` + `first_event_s` — still a benchmark; step-level attribution then falls to the Windows-side logs. The instrumentation is what answers this.
- The relay may summarize the TIMING line away unprompted; honest-relay rules help, and a small DSL bullet ("include the TIMING line when the user asks why it was slow") is the optional follow-up if elision is observed — that requires the live publish cycle, so it is deliberately out of the minimal fix.
- Instrumentation must stay purely passive on the stream: the cancel lever depends on the client registration and disconnect semantics; timing capture must not alter consumption or the cancel/cleanup paths.
- Slightly larger audit lines and tool payloads — bounded (profile is compact, top-N gaps), backward-compatible.
- Security unchanged: the profile carries timestamps/snippets of tool narration only — no new data surfaces.

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the gateway's mid-turn event cadence is unknown by design; the benchmark is the experiment that measures it. If the owner later wants the relay to ALWAYS surface the breakdown, that is the small DSL-bullet follow-up above.]
