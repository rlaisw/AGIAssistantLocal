# Data Model: Hermes Office Task Lane

**Feature**: specs/030-hermes-office-tasks/spec.md · Supersedes 029's exclusion for the four Office apps · 2026-11-02

## Entities

### OfficeTask

One prompt's bounded step sequence, targeting one application (plus launching it when needed). No artificial step cap (owner decision): any length is attempted; budget exhaustion stops at the last completed step with an honest resume.

| Field | Type | Rules |
|-------|------|-------|
| kind | `document-write` \| `document-read` \| `compose-email` \| `send-confirmation` \| `cancel` \| `continue` | gate classification; `send-confirmation`/`cancel` resolve against the conversation's `PendingDraft`, else ask-back |
| app | `excel` \| `word` \| `powerpoint` \| `outlook` \| none | derived; drives the agent's directive |
| named_paths | list[str] | every path the prompt names MUST normalize inside the Office work folder (`hermes_office_root`, default `C:\OfficeMCP`) — outside → blocked naming the root |
| code_exec_vectors | list[str] | macro/DDE/external-link-formula requests detected in the prompt → blocked naming the rule (FR-004) |

### TaskStep

| Field | Type | Rules |
|-------|------|-------|
| n | int | 1-based, ordered |
| operation | str | the agent's reported operation (open/create/write/compose/send/save…) |
| outcome | `OK — detail` \| `FAILED — detail` | parsed from `STEP <n>: <op> OK/FAILED — <detail>` lines; a FAILED step stops the chain (FR-005) |
| audit | AuditEntry | one append-only entry per step, `operation="office-task"`, `allowed_root` = the Office work folder (the lane's audit discriminator) |

### PendingDraft (conversation-scoped)

| Field | Type | Rules |
|-------|------|-------|
| conversation_id | str | key; the DSL binds it from `{{#sys.conversation_id#}}` |
| entry_id | str | the Outlook draft's COM EntryID — the only thing a confirmation may send |
| displayed | {recipients, subject, body} | the exact content shown to the user; "the draft shown is the draft that sends, unchanged" |
| lifecycle | pending → sent \| dropped | confirmation sends; cancel or a new compose drops it; modification re-displays a fresh draft and requires fresh confirmation; lives until resolved (no expiry); **never deleted** — dropped drafts stay in the Drafts folder, reported honestly |

### ActiveDocument (conversation-scoped)

| Field | Type | Rules |
|-------|------|-------|
| conversation_id | str | key |
| windows_path | str | the last document this conversation created/edited (from `ACTIVE FILE:` reports); follow-ups without a named file continue on it, the answer names it; naming another file switches it; lost on sidecar restart → honest ask-back |

### Interrupted (conversation-scoped)

| Field | Type | Rules |
|-------|------|-------|
| conversation_id | str | key |
| original_task | str | the prompt that stopped part-way |
| partial_report | str | the `TASK: PARTIAL` report tail (or the budget-timeout error) |
| lifecycle | stored on PARTIAL / budget timeout → replayed by a "continue" (resume directive) → cleared on resumed completion; replaced by the next interrupted task |

### Tool envelope (MCP `hermes_office_task`)

`{status: ok|blocked|error, decision?: executed|blocked, result?: str, reason?: str, active_file?: str, draft_pending?: bool}` — `result` present iff ok (the step reports); `draft_pending` true after a compose turn awaiting confirmation; `ok` requires the agent's `TASK: COMPLETED` marker. Additive (26th tool); no existing schema changes.

### AuditEntry (office)

One JSONL line per executed step and per refusal via the existing `HermesAudit` writer — fields unchanged; `operation="office-task"`, `allowed_root` = the Office work folder (discriminator), outcome/reason carrying the `STEP`/`TASK` line text.

## State transitions

`prompt → gate (kind/app/policy) → [blocked: audit+answer] | state-resolve (confirm/cancel against PendingDraft; continue against the Interrupted record) → agent turn (OFFICE_INSTRUCTIONS + directive; agent drives Office via its MCP connection to OfficeMCP) → parse STEP/ACTIVE FILE/DRAFT ID/TASK markers → per-step audit → envelope + state update (ActiveDocument, PendingDraft, Interrupted on PARTIAL/timeouts)`

In-memory conversation state is lost on sidecar restart — the honest fallback is an ask-back for the next turn; nothing is silently assumed (documented in Assumptions).
