# Tool Contract: hermes_run_command (spec 033)

Phase 1 output — the client-facing MCP tool contract. Additive only (Constitution I): existing tools, their schemas, and their verdict shapes are untouched.

## Schema

```
hermes_run_command(
    task: str,              # the user's full request text, passed unchanged by the relay
    conversation_id: str,   # REQUIRED — schema rejects calls without it (spec FR-006)
) -> ToolEnvelope
```

The required identity parameter is the contract-level difference from `hermes_launch_app` (whose identity is optional and was observed omitted live on 2026-11-09): every run-command turn is timing-instrumented and cancellable from the chat Stop button by construction.

## ToolEnvelope shapes

### ok (executed)

```json
{
  "status": "ok",
  "command": "ipconfig",
  "result": "COMMAND: ipconfig\nOUTPUT:\nWindows IP Configuration\n…\nTASK: COMPLETED\n\nTIMING: total 12.4s | first event +0s | 96 events | …"
}
```

- `result` carries the agent's real output, bounded (~4000 chars); when truncated, the envelope itself says so.
- `ok` is stamped ONLY on: attestation present (`TASK: COMPLETED`) AND the agent's echoed `COMMAND:` matches the gated directive after normalization. A mismatch, missing markers, or a report of anything else running → `error`, never a fabricated success (spec FR-005; the 029 FR-007 lesson generalized).

### blocked (gate refusal — nothing ran)

```json
{
  "status": "blocked",
  "command": null,
  "reason": "Blocked: 'Get-NetIPAddress' is not on the run-command allowlist — read-only diagnostics only, one command per request. Allowed: ipconfig, systeminfo, tasklist, whoami, hostname, ping <host>, nslookup <host>, tracert <host>."
}
```

Refusal reasons always name the violated rule **and show the list** (spec FR-002). Distinct reasons at minimum: not-on-allowlist, flags/pipes/redirection/separators refused, single-simple-target rule, one-command-per-request ask-back, and unmapped-request ask-back.

### error (honest failure — nothing claimed)

```json
{
  "status": "error",
  "reason": "error:the local agent failed to run the command — <failure detail> — <recovery hint>"
}
```

## Relay contract (DSL instruction additions)

- Route system-state/diagnostics requests to `hermes_run_command`, passing the user's task text unchanged and `conversation_id` exactly as `{{#sys.conversation_id#}}`.
- Relay `ok` by reporting the real output (target the slice that answers the question; name truncation if the envelope says it was cut); relay `blocked` verbatim including the list; relay `error` with the recovery hint.
- One command per request; on the gate's ask-back, relay the question verbatim.
- Shell phrasing that arrives on the launch lane still refuses there; its message points the user here for allowlisted diagnostics (launch contract unchanged in substance — append-only text).
- The ANTI-FABRICATION LAW and the structural honesty check cover this tool: an answer claiming a run without this turn's tool call is replaced (the honesty-check `claims` pattern gains `hermes_run_command`).

## Audit contract

Exactly one append-only audit row per attempt, `operation="run-command"`, with the turn's timing profile (`duration_s` + `timing`) on executed/error turns. Blocked turns record the verbatim reason. No execution path exists without an audit row (spec FR-004).

## Backward compatibility

- New tool only; the MCP tool count grows 27 → 28 via the established `sync-tools` flow.
- The launch gate's shell-refusal message keeps every pinned phrase; the new pointer sentence is appended text, and the launch gate suite re-runs green in the task list.
- The honesty-check node's regex change extends a pattern added the same day; no published consumer matches on its exact form.
