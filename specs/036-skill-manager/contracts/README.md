# Contracts: Skill Manager (spec 036)

**Spec**: 036 | **Date**: 2026-11-11 | Inherits [035 contracts](../035-ai-helpdesk-architecture/contracts/README.md); this file fixes the concrete shapes the contract tests pin.

## MCP tool surface (additive: 29 → 33; Principle I)

All four tools: `conversation_id` REQUIRED (house pattern), audit row per call with `duration_s`+`timing`, honest error envelopes. No existing tool schema changes.

### skill_search

```
skill_search(intent: str, conversation_id: str) -> {
  found: bool,                      # false on miss — DISTINCT from outage
  skills: [ { name, description, success_rate, sample, reusable } ]   # top-k by semantic score
}
```

- `reusable` pre-computed (trust rule: >80% AND ≥3) — the lane's reuse decision is a field read, not model judgment (R5).
- Outage → `error:skill-store-unavailable` naming the outage; never `{found:false}` masking a down store.
- Searched BEFORE operational tasks only; the General lane never calls it (FR-001/012).

### skill_get

```
skill_get(name: str, conversation_id: str) -> { skill } | error:skill-not-found
```

- Unknown name → explicit not-found (never an empty workflow). Full record incl. workflow + version + counts.

### skill_save

```
skill_save(skill: {name, description, tier, workflow}, conversation_id: str) -> { name, version }
```

- Boundary validation (see data-model): rejects with the offending field named — non-snake name, empty description, bad tier, missing `expect`, machine literal in `params_template`, tier-2 without tier-1 first step.
- Same name → upsert, version+1, counters preserved; returns the new version.
- NOT confirm-gated (it creates data, not machine effects).

### skill_feedback

```
skill_feedback(skill_name: str, outcome: "success"|"failure", error_context?: str,
               conversation_id: str) -> { acknowledged: true }
```

- Append-only. Missing skill → explicit error. `error_context` required on failure.
- The API exposes no delete (escalation, not deletion — FR-009).

## Replay protocol (executor; FR-010/011 — 035 FR-020 made structural)

1. `skill_get` the skill → substitute `{{slots}}` from the live request (unfilled slot → honest ask-back, never a guess).
2. Walk steps in order; each step calls its target lane's **existing** tool handler (gates included).
3. A confirm-gated step → `pending-confirmation` envelope; the draft registers in the **existing** spec-034 conversation state; confirm executes the stored text and **resumes the walk at the next step**.
4. Cancel → draft cleared (spec-034 rules), walk aborts, **no failure feedback for the skill** (user cancellation ≠ skill failure).
5. Any step's `expect` mismatch → walk aborts naming the failed expectation; near-miss bail-out (Edge Cases); feedback records the failure honestly.
6. Every walk start/abort audits (`skill-replay-start`/`skill-replay-abort`).

**Structural invariant (A3)**: there is no code path in the executor that reaches a gated tool's execution side without the live confirm — the gates are called, never bypassed.

## DSL wiring (per-component ownership rule)

- Intent classifier: operational classes route as today; **questions/chat stay General** — General lane tools list does NOT include the four skill tools (structural enforcement of FR-001 scope).
- Hermes lane instructions gain the skill-loop rules: search before acting (operational), reuse iff `reusable`, manual-solve + save on novel success, feedback after every reuse, retry-once then escalate, never claim skill actions without a tool call (ANTI-FABRICATION LAW extends to the skill lane — A6).
- `tool_mcp_providers` rebuild + `docker-api-1`/`docker-worker-1` restart after publishing (the staleness rule).

## Audit contract

Six new `operation` values: `skill-search`, `skill-get`, `skill-save`, `skill-feedback`, `skill-replay-start`, `skill-replay-abort` — same row shape as today (operation, conversation_id, outcome, `duration_s`+`timing`, exact text where applicable). Adversarial battery refusals (A3/A6) MUST appear as audit rows (SC-007).