# Data Model: AI Helpdesk Architecture

**Spec**: 035 | **Date**: 2026-11-11

The shared entity vocabulary every component spec inherits. The Skill Manager (036) owns the skill-side persistence; audit/pending-confirm already exist in the live stack.

## Skill

The reusable unit of learned work. Persisted server-side (WSL) in the shared skill store — one store, not per-host (clarified).

| Field | Type | Rules |
|---|---|---|
| name | str | snake_case, unique identity key — same name = same skill across versions (FR-004) |
| description | str | must bear trigger keywords (what it does + when to use it) — the semantic search surface (FR-002) |
| tier | 1 \| 2 | Tier-2 skills MUST have a Tier-1 pre-check as workflow step 1 (FR-006) |
| workflow | list[Step] | parameterized template steps (see Step); machine-specific literals forbidden (SC-005) |
| version | int | starts 1; +1 on same-name save (FR-004) |
| success_count / failure_count | int | trust inputs; decay is feedback-driven, no time expiry (clarified) |
| created_at / updated_at | timestamp | monotonic update on same-name save |

**Step** (workflow item): `{tool: str, service: str, params_template: JSON object with {{placeholder}} slots, expect: str}` — every step carries `expect` (FR-006); execution substitutes per-request values into `params_template` (research R2); a failed `expect` at any step is the near-miss bailout (Edge Cases).

**Trust rule (FR-003)**: auto-reuse iff `success_count / (success+failure) > 0.80` AND `success_count ≥ 3`. Otherwise manual solve; a successful manual solve of an existing skill's intent updates that skill (same name, version+1).

**Lifecycle**: draft-saved (v1) → trusted (thresholds met) → demoted (failures drop rate below 80%) → manually re-earned or escalated after 2 consecutive failures (FR-005 — never deleted by the system).

## SkillFeedback

Append-only outcome record per reuse attempt.

| Field | Type | Rules |
|---|---|---|
| skill_name | str | references Skill.name |
| outcome | success \| failure | |
| error_context | str \| null | required on failure — feeds self-correction and the retry decision |
| timestamp | ts | append-only |

## ServiceEndpoint

Per-host service registry entry (fleet topology, FR-015/016/018).

| Field | Type | Rules |
|---|---|---|
| service | str | one of: os-control, dynamic-browser, scripted-browser, office, task-gateway, skill-manager |
| host_id | str | Windows client identity (v1: the single existing host) |
| transport | mcp/sse \| http | streamed vs plain HTTP — the >30 s routing key (FR-009) |
| port | int | port plan resolves 3001–3004 proposal vs live 8800/8888 (FR-015, component specs fix the concrete map) |

## AuditRecord

Existing append-only lane audit (`~/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl`), extended per new lane.

| Field | Type | Rules |
|---|---|---|
| operation | str | per-lane operation name (…+ skill-reuse, browser-*, task-api, registry-*) |
| host_id / service / outcome | — | fleet scoping (FR-014) |
| duration_s + timing | — | timing profile, as live today |
| adversarial rows | — | every refusal in a battery trial MUST have its audit row (SC-007) |

## PendingConfirm

Conversation-scoped stored command awaiting a plain-affirmative confirm (spec-034 state, unchanged). **New rule (FR-020)**: during skill replay, each gated step re-enters PendingConfirm state live — a skill record never pre-confirms its own gated steps.

## Relationships

```
Skill 1──* SkillFeedback        (append-only outcomes)
Skill *──1 ServiceEndpoint      (steps name their service; endpoint resolves host+transport)
Skill *──* PendingConfirm       (replay of gated steps creates live confirms, cleared per spec-034 rules)
AuditRecord *──1 ServiceEndpoint (every attempt, one row, per host)
```