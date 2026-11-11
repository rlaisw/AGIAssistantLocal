# Contracts: AI Helpdesk Architecture

**Spec**: 035 | **Date**: 2026-11-11

The contract vocabulary each component spec must honor. No interface ships in this spec — these are the binding shapes the component specs (036+) implement and their contract tests pin.

## Sidecar MCP tool surface (additive; Principle I)

Every new lane ships as new MCP tools on the existing sidecar (`:28080/mcp`), additive only:

- Existing schemas never change; new tools appear in `tools/list` (29 → N).
- Each new tool requires the Dify `tool_mcp_providers` rebuild + `docker-api-1`/`docker-worker-1` restart (the known cache staleness rule).
- Each tool's Dify `tool_description` carries the lane's routing rules + gate semantics verbatim (per-component DSL ownership).

## Skill Manager API (spec 036 implements; shapes fixed here)

| Operation | Request | Response contract |
|---|---|---|
| skill_search | `{intent: str, host_id?: str}` | `{found: bool, skills: [{name, description, success_rate, sample}]}` — trust data surfaced so the routing decision can apply FR-003 itself |
| skill_get | `{name: str}` | `{skill}` — full record incl. parameterized workflow; missing name → explicit not-found, never empty-skill |
| skill_save | `{skill}` | `{name, version}` — same name = update + version increment (FR-004); machine-specific literal in `params_template` → rejected (SC-005) |
| skill_feedback | `{skill_name, outcome, error_context?}` | `{acknowledged: true}` — append-only |

Server-side, shared store; the skill loop runs for **operational tasks only** (FR-001).

## Gated-lane protocol (extends spec-034 two-phase)

Applies to: PowerShell/cmd (existing), registry writes/deletes (FR-011 three-tier), RunPython (FR-012), Tier-2 deep repair (FR-013), and any new gated surface.

1. **Draft call** — registers the exact payload (command/code/operation), never-list-scanned, stored conversation-scoped, echoed verbatim, audited with exact text. Nothing executes.
2. **Confirm call** — plain-affirmative only; carries **no payload text** (what was confirmed is structurally what runs). One pending draft per conversation. Cancelled confirm clears it (spec-034 rules); failed-but-uncancelled confirm keeps it re-confirmable.
3. **Skill replay (FR-020)** — a gated step inside a reused workflow re-enters this protocol live at execution time; the skill record never pre-confirms.
4. **Never-list** — system-integrity patterns refused **even with confirmation**, in every gate, including when reached via another service (no gate-shopping, SC-003). Tier-1 recommendation + user confirmation do not override it (FR-013).

## Task-API gateway contract (spec 038+ implements)

- Transport: plain HTTP request/response (FR-009) — never a held-open streamed MCP call for >30 s jobs.
- `POST /api/helpdesk/tier1` → `{Recommendation: "none"|"tier2", ...}` structured JSON only (no console text reaches the agent).
- `POST /api/helpdesk/tier2` → gated by the sidecar lane: requires a fresh tier1 recommendation + chat confirmation (FR-013).
- `POST /api/office/install` → long-running; progress polling, completion event, audited start/end.

## Browser lanes contract (spec 037+ implements)

- Dynamic lane: official Playwright MCP server over SSE — exploratory navigation, screenshots, visual verification.
- Scripted lane: named versioned scripts as tools — `{script, args}` in, structured result + per-step `expect` checkpoints out.
- **FR-019 (binding)**: web content is untrusted context — it informs answers, never initiates tool calls or gate requests; both lanes' agent instructions carry this and every battery includes a prompt-injection adversarial scenario (SC-007).

## Audit contract (all lanes)

Every attempt — success, refusal, or adversarial-trial refusal — writes one append-only audit row: `operation`, `host_id`, `service`, `outcome`, `duration_s`+`timing`, and the exact text for two-phase drafts. `operation` values are per-lane and enumerated by each component spec.