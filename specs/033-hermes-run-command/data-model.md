# Data Model: Hermes Run-Command Lane (spec 033)

Phase 1 output. Entities are design-level; field types/implementation live in the contract and tasks.

## CommandVerdict (gate output)

The immutable result of parsing and gating one request, before any execution.

| Field | Type | Values / Rules |
|-------|------|----------------|
| `decision` | enum | `ok` (an allowlisted command parsed) \| `blocked` (refusal with reason) \| `ask-back` (a question for the user) |
| `command` | string \| null | The resolved allowlisted command name (`ipconfig`, `tasklist`, …); null unless `ok` |
| `target` | string \| null | The single validated target token (hostname/IP); non-null only for `ping`/`nslookup`/`tracert` |
| `reason` | string \| null | Verbatim refusal text (names the rule **and shows the allowlist**) or the ask-back question; null on `ok` |

Validation rules: the command must be a member of the fixed allowlist; the target, when present, must match the strict hostname/IP charset (letters, digits, dots, hyphens — one token); any flag, pipe, redirect, separator, quoting metacharacter, second command, or unmapped destructive verb forces `blocked`; an unresolvable-but-plausible request forces `ask-back` offering the list.

State transitions: `request text → CommandVerdict` is a pure function; `ok` is the only verdict that can proceed to execution; `blocked`/`ask-back` terminate at the gate and are audited.

## AllowlistEntry (gate constant)

| Field | Values |
|-------|--------|
| `name` | One of: `ipconfig`, `systeminfo`, `tasklist`, `whoami`, `hostname`, `ping`, `nslookup`, `tracert` |
| `argument_policy` | `bare` (first five) \| `single-target` (last three) |
| `intent_phrases` | The fixed synonym table entries mapping natural language to this entry (e.g. "ip address" → `ipconfig`) |

The list is closed: extension requires a spec amendment. It lives in gate code, never in a prompt.

## AuditEntry (per attempt, append-only)

One JSONL row per attempt in the existing audit log, written at the tool's single verdict point:

| Field | Values |
|-------|--------|
| `ts` | Verdict-time UTC timestamp (existing writer) |
| `decision` | `executed` \| `blocked` \| `error` (existing enum — unchanged) |
| `operation` | `"run-command"` — the lane's discriminator |
| `normalized_path` | The gated command + target (`"ipconfig"`, `"ping 8.8.8.8"`) |
| `reason` / `outcome` | Blocked reason verbatim, or the real bounded output excerpt |
| `duration_s`, `timing` | Turn timing profile (shared stream-path machinery) |

## ToolEnvelope (tool → relay)

| Field | Values |
|-------|--------|
| `status` | `ok` \| `blocked` \| `error` |
| `command` | The command the gate resolved (present on `ok`/`blocked`) |
| `result` | On `ok`: the agent's real output, bounded (~4000 chars), truncation named; carries `COMMAND:`/`OUTPUT:`/`TASK: COMPLETED` markers |
| `reason` | On `blocked`: verbatim gate reason (allowlist shown); on `error`: failure + recovery hint |

Relationships: `CommandVerdict.command` + `.target` compose the agent directive; `ToolEnvelope.status` mirrors the audit decision of the same attempt (one envelope ↔ one audit row ↔ one gate verdict).

## Identity & uniqueness

One request → one gate verdict → at most one executed command → exactly one audit row. The conversation identity is a required tool parameter; a call without it is rejected by the tool schema before the gate runs (it never becomes an attempt).
