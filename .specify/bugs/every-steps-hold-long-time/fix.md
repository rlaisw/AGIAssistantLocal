# Bug Fix: turn timing profile — every desktop turn now self-benchmarks (total, first event, event count, top gaps)

- **Slug**: `every-steps-hold-long-time`
- **Fixed**: 2026-11-09
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The desktop-task pipeline no longer discards its own timing data: `run_task_stream` now timestamps every SSE event arrival it already receives and returns a compact `timing` profile (`total_s`, `first_event_s`, `event_count`, top-3 inter-event gaps with labels) on **all** nine return paths — ok, error, timeout, and the Stop/cancel path; the launch and office lanes render it as a `TIMING:` line in the tool result (the relay's only post-hoc view, since Dify tool calls stream nothing mid-turn) and write `duration_s` + the profile into every audit entry. The sidecar container is hot-patched and live.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | `_GAP_MIN_S`/`_TOP_GAPS`, `_event_label`, `_timing_profile`; `run_task_stream` instruments event arrivals (purely passively — cancel semantics untouched) and returns `"timing"` on all paths incl. ReadError/cancel and Timeout |
| `src/agentic_rag_mcp/hermes_audit.py` | modified | `write_attempt` gains optional `duration_s` + `timing`; legacy entries keep their exact shape (absent keys) |
| `src/agentic_rag_mcp/server.py` | modified | `_timing_line` renderer; launch lane: timing into all 3 audit calls + `TIMING:` line appended to ok results; office lane: `turn_timing` threaded through `_audit`/`_error_envelope` (per-step entries are self-contained) + `TIMING:` line on completed tasks; send/continue paths inherit it via `_run_agent` |
| `tests/unit/test_hermes_launch_tool.py` | added tests | fake-clock exact profile, cancel-path profile, tool-level TIMING + audit fields (ok and error) |
| `tests/unit/test_hermes_office_tool.py` | modified harness + added test | `_server` accepts `timing`; TIMING line + audited profile through the office lane |
| `tests/unit/test_hermes_audit.py` | added test | legacy-shape preservation + new-fields round-trip |

## Diff Highlights (optional)

```python
# hermes_client.py — passive capture inside the existing loop (cancel lever untouched)
now = time.perf_counter()
event_count += 1
if first_event_s is None:
    first_event_s = now - t0
else:
    gap = now - last
    if gap >= _GAP_MIN_S:
        gaps.append((gap, now - t0, _event_label(event)))
last = now

# server.py — the relay-facing surface
return {"status": "ok", "decision": "executed",
        "result": f"{output}\n\n{tline}" if tline else output, ...}
# → "TIMING: total 84.2s | first event +5.1s | 17 events | gap 23.8s @+40.2s before response.output_text.delta 'verifying focus'"
```

## Tests Added or Updated

- `test_hermes_launch_tool.py::test_timing_profile_orders_and_truncates_gaps` — top-3 gaps, descending, exact rounding
- `test_hermes_launch_tool.py::test_run_task_stream_records_timing_profile` — the full loop on a fake clock: `total_s`/`first_event_s`/`event_count`/gap list asserted EXACTLY, including delta-snippet labels
- `test_hermes_launch_tool.py::test_cancelled_turn_still_carries_timing` — a Stop-path disconnect still returns a (zero-event) profile — stopped turns are benchmarked
- `test_hermes_launch_tool.py::test_ok_launch_appends_timing_line_and_audits_duration` — TIMING line in the tool result; `duration_s` + `timing` in the executed audit entry
- `test_hermes_launch_tool.py::test_error_turn_audits_duration_too` — errored turns carry the benchmark too
- `test_hermes_office_tool.py::test_turn_timing_line_and_audited_profile` — office lane: exact TIMING rendering + per-step audit entries carry `duration_s`/`timing`
- `test_hermes_audit.py::test_optional_timing_fields_round_trip` — legacy entries byte-shape unchanged; new fields round-trip verbatim

## Local Verification

- Commands: `pytest tests/unit/test_hermes_launch_tool.py tests/unit/test_hermes_office_tool.py tests/unit/test_hermes_audit.py -q` → **43 passed** (7 new).
- Commands: `pytest tests/ -q` → **502 passed, 5 failed** — all 5 failures pre-existing and unrelated (antv/ppt tool-count contracts, web-research cap, OneDrive staleness integration; the 5th — antv live-chart — passes standalone and is flaky only in full-suite runs). **Evidence they are not mine**: re-ran the same 5 on a stashed (pre-change) tree → identical 4 failed / 1 passed; the changed hermes paths are fully green.
- Live: hot-patched the 3 source files into the sidecar container (`docker cp` + `docker restart agentic-rag`), health ok on :28080, in-container code confirmed (`_timing_profile` present; `TIMING:` renderer in server.py). No tool added/removed — the MCP tool surface is unchanged (27).

## Deviations from Assessment

- None. The remediation was applied exactly as proposed (client profile → audit fields → TIMING line in both lanes). Test-only choice: the stream profile is asserted exactly via a fake clock instead of real sleeps — determinism, not a scope change.

## Follow-ups

- Live verification on the next real desktop turn (the `/speckit.bug.test` phase): the relay's answer should carry the `TIMING:` line and the audit entry should gain `duration_s` + `timing` — that turn also answers the open question about the gateway's mid-turn event cadence (the instrumentation is the experiment).
- If the relay summarizes the TIMING line away unprompted, add the small DSL bullet ("include the TIMING line when the user asks why it was slow") via the live publish cycle — deliberately out of this minimal fix.
- Pre-existing contract-suite drift (antv 21→23, ppt 16→21, web-research limit cap, OneDrive staleness) fails identically without this change — worth its own cleanup lifecycle.
- Fold this fix into the next lifecycle commit together with the two `waiting-long-long-time-…` closure docs.
