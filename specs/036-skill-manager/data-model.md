# Data Model: Skill Manager (spec 036)

**Spec**: 036 | **Date**: 2026-11-11 | Inherits and concretizes [035 data model](../035-ai-helpdesk-architecture/data-model.md)

## Skill (SQLite table `skills`)

| Column | Type | Rules (validation at save boundary — FR-004/005/006) |
|---|---|---|
| name | TEXT PRIMARY KEY | snake_case regex `^[a-z][a-z0-9_]*$`; identity key — upsert on collision, version+1 |
| description | TEXT NOT NULL | non-empty; trigger keywords required by FR-004; concatenated with name as the embedding surface |
| tier | INTEGER CHECK (tier IN (1,2)) | tier-2 workflows MUST have a tier-1 pre-check as step 1 (rejected at save otherwise) |
| workflow_json | TEXT NOT NULL | `[{step, tool, service, params_template, expect}]`; every step carries `expect`; `params_template` slots are `{{snake_case}}`; machine-specific literals (`C:\Users\`, hostnames, absolute host paths) rejected (SC-005) |
| version | INTEGER DEFAULT 1 | starts 1; +1 on every same-name save |
| success_count | INTEGER DEFAULT 0 | trust numerator; reset semantics: an update that changes the workflow keeps the counters (history is feedback, not the workflow's) |
| failure_count | INTEGER DEFAULT 0 | trust denominator partner |
| created_at / updated_at | TEXT (ISO) | updated_at bumps on upsert |

**Trust rule (FR-002, mechanical)**: `reusable = (success_count / (success_count + failure_count) > 0.80) AND success_count >= 3` — pre-computed in every `skill_search` hit; decay is purely these counters moving (no time expiry, FR-003).

**Lifecycle**: saved(v1) → trusted (thresholds met) → demoted (failures drop rate) → escalated (2 consecutive failures, kept — never deleted) → re-earned via manual solve + same-name update.

## SkillFeedback (SQLite table `skill_feedback`)

| Column | Type | Rules |
|---|---|---|
| skill_name | TEXT | FK→skills.name; appending to a missing skill → explicit error, never a silent orphan |
| outcome | TEXT CHECK (IN ('success','failure')) | one row per reuse attempt (FR-008) |
| error_context | TEXT NULL | required when outcome=failure; feeds retry-one self-correction |
| ts | TEXT (ISO) | composite PK (skill_name, ts) — append-only ordering |

## Intent vector (LanceDB table `skills`)

| Field | Type | Rules |
|---|---|---|
| name | TEXT | joins to SQLite by PK |
| text | TEXT | `"{name}\n{description}"` — embedded by `Embedder` at save/update only |
| vector | FIXED_SIZE_LIST | ANN search surface for `skill_search` |

Re-embed on every save/update (description may change); delete+insert on upsert (no stale vectors — the eviction lesson from `store/state.py`).

## AuditRecord (existing JSONL, extended)

New `operation` values: `skill-search`, `skill-get`, `skill-save`, `skill-feedback`, `skill-replay-start`, `skill-replay-abort` — each row carries `conversation_id`, outcome, `duration_s`+`timing` (house pattern). Adversarial-trial refusals write their rows too (A3 evidence).

## PendingConfirm (existing spec-034 state, reused)

Replay of a gated step registers its draft in the **existing** conversation-scoped state; confirm executes the stored text and resumes the walk; cancel clears (spec-034 rules) and aborts the walk without skill-failure feedback (R4). No new state store.

## Relationships

```
skills 1──* skill_feedback          (append-only outcomes; trust counters derive)
skills 1──1 lance skills row         (name join; re-embedded on save)
skills *──1 params slots             ({{slots}} filled per request at replay)
replay walk *──* PendingConfirm      (per gated step, existing state)
AuditRecord 1:1 every operation      (six new operation names)
```

## Validation rules summary (testable at the boundary)

- Save rejects: non-snake name, empty description, tier outside {1,2}, missing `expect`, machine literal in params_template, tier-2 without tier-1 pre-check first step.
- Search returns: trust data + `reusable` per row; `found:false` (miss) is a distinct envelope from `error:skill-store-unavailable` (outage).
- Update: same name → upsert version+1, counters preserved; different name → new skill v1.
- Escalation: 2 consecutive failures on a skill → escalation surfaced; delete is not an operation the API exposes.