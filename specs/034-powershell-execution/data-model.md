# Data Model: PowerShell Execution Lane (spec 034)

Phase 1 output. Entities are design-level; field types and implementation live in the contract and tasks.

## PSVerdict (gate output)

The result of scanning one **draft** against the never-list. Pure function; no parsing of user language — the draft arrives fully formed from the relay.

| Field | Type | Values / Rules |
|-------|------|----------------|
| `decision` | enum | `ok` (the draft may be registered) \| `blocked` (never-list; reason verbatim) |
| `reason` | string \| null | On `blocked`: names the matched system-integrity rule; null on `ok` |

Validation rule: the scan covers the **complete exact draft text** (chained operators, redirections, nested calls included); the never-list is the closed pattern set in gate code; pipes, filters, `Remove-Item`, and service/process control are **legal** on this lane (only system-integrity destruction refuses).

## PendingCommandDraft (conversation-scoped state)

| Field | Type | Rules |
|-------|------|-------|
| `conversation_id` | key | Exactly one pending draft per conversation; a new draft replaces the old |
| `command` | string | The exact registered text — the only string execution can ever refer to; never-list-scanned at registration and re-scanned at execution |

Lifecycle: `draft → registered (shown verbatim, awaiting confirmation)` → `confirmed (executed once, then cleared)` \| `superseded (a later draft replaces it)` \| `abandoned (a new unrelated request; the registration row remains its audit record)`. Never persists across sidecar restarts — pending drafts are ephemeral; the audit JSONL is the durable record.

## AuditEntry (per attempt, append-only)

| Field | Values |
|-------|--------|
| `ts`, `decision`, `operation`, `normalized_path`, `allowed_root`, `reason`/`outcome`, `duration_s`, `timing` | Existing schema, unchanged |
| `decision` mapping | Draft registration → `executed` (the registration is the attempt) with `outcome` = the **exact draft text**; execution → `executed` with the bounded real output + timing; never-list → `blocked` with the rule; confirm-without-pending → `blocked` ask-back |
| `operation` | `"run-powershell"` — the lane's discriminator |

## ToolEnvelope (tool → relay)

| Phase | Shape |
|-------|-------|
| Draft registered | `{status: "pending-confirmation", command: <the exact registered text — relay this VERBATIM and ask the user to confirm>}` |
| Confirmed + executed | `{status: "ok", command: <executed text>, result: <real output, bounded, truncation named>}` |
| Never-list / ask-backs | `{status: "blocked", reason: <verbatim rule or question>}` |
| Failure / mismatch | `{status: "error", reason: <real failure or mismatch detail + recovery hint>}` |

Relationships: one user request → one draft registration (one audit row) → at most one confirmation → one execution (one audit row). The executed string is by construction the registered string (the confirm call carries no command text).

## Identity & uniqueness

One pending draft per conversation; one audit row per attempt (registration, execution, refusal each distinct); the per-conversation identity is a required tool parameter — a call without it is rejected by the schema before any phase runs.
