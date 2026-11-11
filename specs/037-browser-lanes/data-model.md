# Data Model: Browser Lanes (spec 037)

**Spec**: 037 | **Date**: 2026-11-11 | Inherits [035 data model](../035-ai-helpdesk-architecture/data-model.md)

## BrowserScript (file in `scripts/browser/`)

| Field | Type | Rules |
|---|---|---|
| name | str | snake_case identity; file `<name>.py`; unique in the registry |
| version | int | checked-in, bumped on edit; determinism pin (SC-002) |
| params | list[slot] | `{slot, description}`; every slot the body consumes; args validated against this at run boundary |
| expect | list[str] | ordered checkpoints, one per step; a missing/failed checkpoint aborts naming the step (FR-005) |
| body | code | Playwright script emitting **one JSON line per step** (`{"step": n, "ok": bool, "summary": str}`); NO credentials or machine-specific literals (FR-006 — validated at registry load) |

**Lifecycle**: checked in → synced to host → routed to by classifier → run with args → checkpoint-verified → aborted-or-completed (audited). Never auto-deleted; versioned by edit like `ppt-master` skills.

## BrowserRun (ephemeral, per execution)

| Field | Type | Rules |
|---|---|---|
| script + version + args | — | as resolved at run start (args substituted, validated) |
| steps | list[checkpoint result] | per-step `{step, ok, summary}` from the script's structured stdout, verified against `expect` in order |
| outcome | completed \| aborted \| error | aborted = a checkpoint failed (named); error = transport/host failure (honest envelope) |
| duration_s + timing | — | audited (FR-009) |

## DynamicStep (ephemeral, per agent action)

The dynamic lane has no store — steps are agent-driven `mcp__PlaywrightMCP__*` calls whose results the agent reports. The durable trace is the audit row per turn (FR-009) and the conversation itself. Screenshots are evidence in the answer, never authority (FR-007).

## AuditRecord (existing JSONL, extended)

New `operation` values: `browser-scripted-run` (per run: outcome, steps summary, `duration_s`+`timing`, `conversation_id`), `browser-status` (probe results, honest-unavailable rows). A2 adversarial refusals MUST leave their rows (SC-006).

## RoutingGate verdict (ephemeral)

| Field | Rules |
|---|---|
| lane | `scripted` \| `dynamic` \| `refused-os` \| `ask-back` |
| script | resolved name when scripted; else None |
| reason | refusal/ask-back text — always honest, always named (FR-002 pins: browser intent NEVER lands on the OS lane) |

## Relationships

```
BrowserScript 1──* BrowserRun        (executions; versioned file + ephemeral runs)
Skill (036) *──* BrowserScript      (a saved skill's workflow step may name a script by slot)
BrowserRun/DynamicStep *──* AuditRecord (every attempt, one row)
ServiceEndpoint: dynamic-browser → 127.0.0.1:3002/sse (host loopback; Scheduled Task FR-010)
```

## Validation rules (testable at the boundary)

- Script registry load rejects: name/schema mismatch, missing `expect` entries, credential-looking literals, machine-specific paths (same regexes as 036's validator — reused, not duplicated).
- `browser_scripted_run` rejects: unknown script (honest not-found), missing args slot (ask-back), extra args (named).
- Routing gate refuses: browser intent → OS lane (FR-002 pin); no-script exploratory intent → dynamic.
- `browser_status` never fabricates: probe failure → `error:browser-lane-unavailable` + recovery text (start the Scheduled Task), audit row.