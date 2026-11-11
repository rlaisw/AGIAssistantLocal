# Data Model: Task-API Gateway (spec 038)

**Spec**: 038 | **Date**: 2026-11-11 | Inherits [035 data model](../035-ai-helpdesk-architecture/data-model.md)

## Tier1Outcome (ephemeral, per call)

| Field | Type | Rules |
|---|---|---|
| recommendation | "none" \| "tier2" | the protocol driver (FR-001); anything else → honest error (malformed ≠ none) |
| actions | list | the quick fixes actually run, with their real outcomes — relayed verbatim |
| detail | str | structured summary; raw console text never surfaces |

## Tier2Recommendation (conversation-scoped state, `Tier2State`)

| Field | Type | Rules |
|---|---|---|
| conversation_id | str | scope key — new conversation = clean slate (FR-004) |
| issue_type | str | the tier-1 call's issue class |
| repair_name | str | the NAMED repair from the service catalog — what the user confirms |
| repair_text | str | the operation text the never-list scans (R3) |
| created_at | ts | short-lived: superseded by a new tier1 run in the same conversation |

**Lifecycle**: created by a tier1 "tier2" result → shown as `pending-confirmation` → consumed by a plain `confirm=True` (executes only the stored repair) → cleared on execution, cancellation, or supersession. Mirrors `PendingConfirm` semantics (034).

## Job (gateway job table + JSONL)

| Field | Type | Rules |
|---|---|---|
| id | str | opaque job identifier |
| kind | str | e.g. `office-install` |
| status | queued \| running \| progress \| completed \| failed | real at every poll (FR-006); `failed` carries detail |
| detail | str | progress/completion summary from the install |
| started_at / ended_at | ts | duration derivable |

**Lifecycle**: created by POST install → background-thread execution → terminal row. Append-only `jobs.jsonl` rows at each transition.

## NeverListPattern (shared module, `neverlist.py`)

| Field | Type | Rules |
|---|---|---|
| pattern | regex | byte-identical to 034's set + tier-2 additions (format/diskpart/boot/shadow-delete/recovery/BitLocker-state/wipe class) |
| scope | powershell \| tier2-repair | one source, two gates (R3); 034's tests re-pin against the shared module |

## AuditRecord (existing JSONL, extended)

New `operation` values: `task-tier1`, `task-tier2-draft` (recommendation registered, nothing executes), `task-tier2-executed`, `task-tier2-refused` (never-list/missing-confirmation), `task-office-install`, `task-job-status`. Every row carries `conversation_id`, decision, `duration_s`+`timing`. Adversarial A1/A4 refusals MUST leave rows (SC-006).

## Relationships

```
Tier1Outcome 1──1 Tier2Recommendation   ("tier2" creates pending state, same conversation)
Tier2Recommendation 1──1 repair execution (confirm executes the STORED named repair)
Job 1──* JSONL rows                     (append-only transitions)
NeverListPattern *──1 both gates         (034 powershell + 038 tier2 — one source)
Skill (036) *──1 task_gateway steps      (operational gateway tasks search skills first; FR-020 replays re-confirm)
```

## Validation rules (testable at the boundary)

- Tier-1 response must parse as JSON with a known `recommendation` value; anything else → `error:task-gateway-malformed-response` (never a fabricated "none").
- Tier-2 confirm without pending recommendation → honest blocked reason (never execution).
- Confirm with payload/operation text → the STORED repair runs (034 structural rule).
- Never-list scan runs at draft AND execution (defense-in-depth); a match at either → refused + escalated, even confirmed.
- Install request without a `version/channel`-class param → ask-back; job poll on unknown id → honest not-found.
- Service down (connect refused/timeout) → `error:task-gateway-unavailable` + recovery text, one turn, no hang.