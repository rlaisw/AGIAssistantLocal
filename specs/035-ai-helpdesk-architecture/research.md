# Research: AI Helpdesk Architecture

**Spec**: 035 | **Date**: 2026-11-11 | **Status**: resolved

## R1: Skill Manager index technology (semantic search)

- **Decision**: SQLite (skills, feedback, versions) + an embedding-backed semantic search over skill descriptions/workflows, served by the Skill Manager as sidecar-adjacent tooling on WSL.
- **Rationale**: FR-001 needs *intent* matching, not keyword matching ("my computer is slow" ≠ "fix_print_spooler" by text). The existing sidecar already runs a vector stack for the knowledge base (LanceDB + embeddings), so the same embedding path serves skill search with zero new dependencies. SQLite handles the transactional version/feedback counters trivially.
- **Alternatives considered**: pure SQLite FTS keyword search (rejected: intent vocabulary drifts from skill names — the whole point of the loop fails); external vector DB (rejected: violates Minimal Dependencies for a single-host store); Chroma as proposed in the original diagram (deferred: a second vector store beside the existing one buys nothing until multi-host).

## R2: Skill workflow parameterization format

- **Decision**: Workflows store steps as `{tool, service, params_template, expect}` where `params_template` is a JSON object with `{{placeholder}}` slots; execution substitutes per-request values from the current user intent; machine-specific literals are forbidden (SC-005 pins this).
- **Rationale**: SC-005 ("no machine-specific literal breaks execution on another host") requires templates, and FR-006's per-step `expect` gives the executor a verification checkpoint at each hop — which is also the near-miss bailout mechanism (Edge Cases).
- **Alternatives considered**: recorded literal params + a diff/patch layer (rejected: replay-by-substitution is simpler and testable); free-form Python snippets per step (rejected: that is arbitrary code execution — FR-012/FR-020 territory, and skills must be data, not code).

## R3: Skill trust thresholds

- **Decision**: reuse requires success_rate > 80% AND ≥3 successes (sample floor); below that, manual solve + `skill_save` update. Decay is purely feedback-driven (clarified): failures pull the rate down, demotion is automatic. No time-expiry, no environment stamps.
- **Rationale**: one lucky success must not become "trusted" (spec User Story 2.3); the sample floor is the smallest rule that prevents it. Feedback-driven decay avoids building environment fingerprinting that the fleet (v1: one host) cannot validate.
- **Alternatives considered**: fixed 90-day expiry (rejected: kills the store's cold-start value); environment stamps + forced re-verification (rejected for v1: untestable with one host; re-visit if multi-host lands and skills drift).

## R4: Dynamic vs scripted browser lanes

- **Decision**: two Dify lanes over one Playwright engine. Dynamic lane = the official `@playwright/mcp` server (SSE) for exploratory navigation; scripted lane = a thin MCP wrapper exposing named, versioned Playwright scripts as tools (args in, structured result out, `expect` checkpoints per step).
- **Rationale**: FR-008 splits by *determinism*, not engine — the official MCP server already exists (no build), and the scripted wrapper is the only new code, small by design. Both lanes inherit FR-019 (web content = untrusted context) via the DSL anti-fabrication/honesty guards.
- **Alternatives considered**: one browser lane with inline scripting (rejected: destroys the determinism/auditability split the spec's routing table depends on); scripting inside the agent via PowerShell (rejected: violates "never use the OS service for browser control" FR-008).

## R5: cli-anything task-API gateway

- **Decision**: adopt HKUDS CLI-Anything's *shape* (HTTP REST endpoints `/api/helpdesk/tier1`, `/api/helpdesk/tier2`, `/api/office/install` returning structured JSON) implemented as a small PowerShell-wrapping service on the Windows host; the agent reaches it through a **new sidecar lane** (`hermes_task_api`-class tools), NOT raw HTTP from the LLM.
- **Rationale**: FR-009 (long jobs off the streamed transport) is satisfied by plain HTTP request/response; FR-013 (Tier-2 only after Tier-1 recommends + chat confirm) is enforceable in the sidecar gate where the never-list lives — an agent-side raw `http_request` tool would put the never-list outside the gate. Structured JSON only (assumption) keeps the agent out of console parsing.
- **Alternatives considered**: vendoring HKUDS CLI-Anything wholesale (rejected for v1: un-audited third-party execution surface; the *endpoint shape* is the contract we need, the implementation is ours and gated); exposing raw `http_request` to the agent (rejected above); running Tier-2 through the PowerShell lane (rejected: it duplicates the never-list in a second gate and loses the Tier-1-recommendation precondition).

## R6: Fleet transport & enrollment (designed-for, not shipped)

- **Decision**: FR-018 — gateway-native MCP per host, reusing consent-retry/direct-SSE-fallback wiring; multi-host = more registered endpoints. Per-host targeting rides `conversation_id` scoping (existing pattern) + a host tag in audit rows. Enrollment machinery is deferred to a later spec.
- **Rationale**: proven on this stack (WindowsMCP/OfficeMCP wiring), zero new protocol surface.
- **Alternatives considered**: unified per-PC relay (rejected: new failure layer, no new capability); direct WSL→Windows SSE per service bypassing the gateway (rejected: loses consent retries and the arg-strip fallback recovery).

## R7: Where the honesty guards extend

- **Decision**: existing DSL guards (`ANTI-FABRICATION LAW`, `honesty_check`, dispatch-leak detector) are extended per lane as each component spec publishes its node; FR-019 adds web-content-as-untrusted-context to the browser lanes' agent instructions; FR-020 (gated steps re-confirm live during skill replay) lives in the Skill Manager executor, not the DSL.
- **Rationale**: guards are per-node DSL state; extending them incrementally per component spec avoids a big-bang chatflow republish (clarified: per-component DSL ownership).
- **Alternatives considered**: one global guard rewrite in this spec (rejected: contradicts the per-component delivery model and risks the live chatflow mid-series).

**All NEEDS CLARIFICATION resolved; none remain.**