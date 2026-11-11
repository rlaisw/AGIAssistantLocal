# Feature Specification: AI Helpdesk Architecture (Six-Service Hermes Fleet)

**Feature Branch**: `035-ai-helpdesk-architecture`

**Created**: 2026-11-11

**Status**: Draft

**Input**: User description: "Build AI Helpdesk Architecture" based on the above conversation — a six-service architecture (Windows-MCP, Playwright MCP, Playwright Scripts, office-mcp, cli-anything, Skill Manager) with a skill auto-save/auto-reuse learning loop and a mandatory tool-routing agent prompt, extending the existing Hermes gateway lanes (specs 027–034).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Office document control through the office lane (Priority: P1)

A user asks the assistant to edit a Word document, write cells into Excel, or restyle a PowerPoint deck. The request routes through the Hermes office lane to the Office automation service, which covers ALL of Word, Excel, PowerPoint (plus Outlook/Notes/Calendar) — correcting the draft routing prompt's mis-scoped claim that office-mcp handles "Outlook, Notes, and Calendar ONLY".

**Why this priority**: Office control is the most-used lane today (spec 030/031) and already works; the P1 job is confirming the expanded scope and correcting the routing rules, not building anything.

**Independent Test**: Ask for a Word/Excel/PowerPoint edit; the office lane handles it and the routing prompt no longer deflects document editing to a browser fallback.

**Acceptance Scenarios**:

1. **Given** the fleet routing prompt, **When** the user asks "open Excel and put 12345 in cell A1", **Then** the request routes to the office service and completes, exactly as in the current single-host stack.
2. **Given** the fleet routing prompt, **When** the user asks "add a slide to this deck / change the background to dark", **Then** the request routes to the office service (document control), NOT to a browser fallback or an install API.

---

### User Story 2 - Skills are searched before every task and reused when trusted (Priority: P1)

Before executing any task, the agent searches the skill store. When a matching skill with sufficient success history exists, the agent retrieves and executes its recorded workflow; when none exists, the agent solves manually and — on success — saves a new versioned, parameterized skill. Feedback (success/failure) flows back into the store.

**Why this priority**: The skill loop is the novel value of the whole architecture — it converts one-off fixes into reusable institutional knowledge.

**Independent Test**: Perform a novel task (no matching skill), verify a skill is saved; repeat the same intent, verify the saved skill is found and reused.

**Acceptance Scenarios**:

1. **Given** no matching skill, **When** the agent completes a task successfully, **Then** a new skill is saved with a snake_case name, a description containing trigger keywords, a tier, a workflow with expected outcomes per step, and version 1.
2. **Given** a saved skill with sufficient successful history, **When** a similar intent arrives, **Then** the skill is found by semantic intent match, retrieved, and its workflow executed step by step, then feedback is recorded.
3. **Given** a matching skill exists but its success history is below the trust threshold, **When** the intent arrives, **Then** the agent does NOT blindly reuse it (minimum sample size applies, so one lucky success never becomes "trusted").

---

### User Story 3 - Self-correction with versioning and escalation (Priority: P2)

When a reused skill fails, the agent analyzes the error, adjusts parameters, retries ONCE; a successful retry updates the same skill (version increments); a second failure records failure feedback and escalates to the human admin instead of thrashing or deleting the skill.

**Why this priority**: Trustworthy failure handling is what makes auto-saved skills safe to reuse; without it the loop degrades trust with every incident.

**Independent Test**: Seed a skill whose workflow fails; run the intent; observe retry → update or feedback → escalation, never deletion.

**Acceptance Scenarios**:

1. **Given** a failing reused skill, **When** the first retry succeeds after parameter adjustment, **Then** the skill is saved again under the SAME name and its version increments.
2. **Given** a failing reused skill, **When** the retry also fails, **Then** failure feedback is recorded and the turn ends with an honest escalation to the human admin.

---

### User Story 4 - Correct service routing per intent class (Priority: P2)

Each request class reaches the right service: atomic OS operations (including registry access and PowerShell/cmd execution) to the low-level OS service; long-running recovery/orchestration to the task-API gateway over plain HTTP; known repeatable web flows to scripted browser control; novel exploratory browsing to the dynamic browser. Browser control NEVER goes through the low-level OS service.

**Why this priority**: Routing correctness is the difference between a fast helpdesk and a slow, wrong one; the constraints (no long jobs over MCP streaming, no GUI automation where a script/API exists) come straight from this stack's known limits.

**Independent Test**: Issue one request per class; assert the service chosen matches the routing table.

**Acceptance Scenarios**:

1. **Given** a registry read or a PowerShell diagnostic request, **When** routed, **Then** it goes to the low-level OS service — but only through the sidecar's gated lanes (see FR-011/FR-012).
2. **Given** a task expected to run longer than ~30 seconds, **When** routed, **Then** it goes to the task-API gateway (plain HTTP request/response), never through a streamed MCP tool call.
3. **Given** "log into the portal and download the statement" (a fixed, repeated flow), **When** routed, **Then** it goes to scripted browser control, not dynamic browsing.

---

### User Story 5 - Two-tier recovery protocol (Priority: P3)

When a user reports system issues, the agent always runs the Tier-1 quick-fix API first, evaluates the structured JSON recommendation, and only calls Tier-2 deep repair when Tier-1 recommends it (or the user explicitly demands deep repair).

**Why this priority**: Valuable but the most destructive surface in the fleet; its gating policy is settled in FR-013 (Tier-1 recommends → chat-confirmed Tier-2; never-list still binding) before any automation touches it.

**Independent Test**: Report a synthetic issue; observe Tier-1 first, Tier-2 only on recommendation.

**Acceptance Scenarios**:

1. **Given** a reported issue, **When** Tier-1 returns recommendation "none", **Then** the agent reports resolution and stops.
2. **Given** Tier-1 returns recommendation "tier2", **Then** the agent calls the Tier-2 API only after the confirmation policy applicable to deep-repair operations.

---

### User Story 6 - Fleet topology (multiple Windows clients) (Priority: P3)

The same agent operates across a fleet of Windows PCs, each running the five client-side services, with per-host targeting so a request names (or is scoped to) one machine.

**Why this priority**: True fleet support is the end-state; v1 ships with the single existing client and the architecture must not preclude adding hosts.

**Independent Test**: Address a second host; the request reaches that host's services, not the first one's.

**Acceptance Scenarios**:

1. **Given** a second enrolled host, **When** a request names it, **Then** its services are addressed and its outcomes audited under that host's identity.

### Edge Cases

- The skill store returns a plausible-but-wrong skill (semantic near-miss) — the agent must verify each step's expected outcome and bail out honestly rather than force the workflow.
- A saved skill contains literal parameters from the machine where it was recorded (e.g., a different drive layout) — skills must store parameterized templates, and execution must substitute per-host/per-request values.
- Long-running Tier-2 job exceeds the streamed-transport ceiling — must run over the plain-HTTP gateway with progress polling, not a single held-open call.
- A user asks for a deep-repair operation that the agent's security gates forbid — refusal with an honest reason, never a silent bypass via a different service (no gate-shopping: if one service refuses, routing the same intent to another service to evade the refusal is forbidden and audited).
- Skill store unavailable — the agent degrades gracefully to manual routing rules and says so; tasks still complete, learning is skipped.
- Two skills match the same intent with similar confidence — deterministically prefer higher success history, then lower tier, then lower version recency.

## Requirements *(mandatory)*

### Functional Requirements

**Skill loop**

- **FR-001**: The system MUST search the skill store by semantic intent match BEFORE executing any task, and surface whether a skill was found to the routing decision.
- **FR-002**: The system MUST record for every skill: name, trigger-keyword-bearing description, tier, parameterized workflow (steps with expected outcomes), version, and success/failure counts.
- **FR-003**: The system MUST only auto-reuse a skill when its success rate exceeds 80% AND its sample size meets a minimum count; otherwise manual solving applies.
- **FR-004**: The system MUST save a new versioned skill after a successful novel task, and update the existing skill (same name, version+1) after a successful retry of a failed skill.
- **FR-005**: After two consecutive failures the system MUST record failure feedback, refuse deletion, and escalate to a human admin.
- **FR-006**: Every workflow step MUST carry an expected outcome, and Tier-2 skills MUST include a Tier-1 pre-check as step 1.

**Routing**

- **FR-007**: The routing rules MUST route Office document control (Word, Excel, PowerPoint, Outlook, Notes, Calendar) to the office service — the draft prompt's "office-mcp does NOT handle Word/Excel/PowerPoint" rule is void. Office install/repair routes to the task-API gateway.
- **FR-008**: The routing rules MUST send known/repeatable web tasks to scripted browser control and novel/exploratory browsing to dynamic browser control; browser control must never ride the low-level OS service.
- **FR-009**: The routing rules MUST send tasks expected to exceed ~30 seconds to the plain-HTTP task-API gateway, never through a streamed MCP tool call.
- **FR-010**: The routing rules MUST send atomic OS operations (registry, processes, files, services) to the low-level OS service.

**Security gates (extending specs 028–034)**

- **FR-011**: PowerShell/cmd execution MUST flow through the existing two-phase draft→confirm gate with the never-list (system-integrity operations refused even with confirmation). Registry access MUST flow through a gated lane with a three-tier policy (owner decision Q1): reads auto-allowed; writes/deletes to non-critical paths behind the two-phase confirm; persistence-critical keys (Run key, services, BCD, SAM) refused with manual-only instructions — never a silent write.
- **FR-012**: The office service's arbitrary-code execution tool (RunPython) MUST be admitted only behind the two-phase draft→confirm gate with full audit of the exact executed code (owner decision Q2) — never exposed raw to the agent; a cancelled confirm clears the pending draft.
- **FR-013**: The agent MAY call the Tier-2 deep-repair API only when (a) a Tier-1 run has just recommended it, and (b) the user confirmed the deep repair in chat (owner decision Q3). The Tier-2 call MUST NOT become a bypass around the spec-034 never-list: system-integrity operations refused by the never-list stay refused even when Tier-1 recommends and the user confirms; they escalate to a human admin instead.
- **FR-014**: Every attempt on every lane MUST be audited (append-only log) with operation type, outcome, and duration/timing profile, as in the current stack.

**Topology**

- **FR-015**: The client-side services MUST be reachable on stable, documented ports per host, with a port plan that resolves the collision between the proposed port map (3001–3004) and the live services (8800/8888).
- **FR-016**: v1 MUST support at least the existing single Windows client, and the design MUST NOT preclude enrolling additional hosts with per-host targeting.

### Key Entities *(include if feature involves data)*

- **Skill**: name, description (trigger keywords), tier (1|2), parameterized workflow (steps: tool, service, params-template, expected outcome), version, success/failure counts, creation/update timestamps.
- **SkillFeedback**: skill reference, outcome (success|failure), error context, timestamp.
- **ServiceEndpoint**: service name, host identity, transport (MCP/SSE vs plain HTTP), port, capability class.
- **AuditRecord**: operation, host, service, outcome, duration/timing profile — append-only.
- **PendingConfirm**: conversation-scoped stored command awaiting a plain-affirmative confirm (two-phase lanes), as in spec 034.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A task successfully completed once is recognized on its next occurrence: the skill is found, reused, and completes without manual re-solving (the "learned task" round-trip) in at least 9 of 10 trials.
- **SC-002**: 100% of tasks route to the correct service per the routing table, verified over a scenario battery covering at least one request per service.
- **SC-003**: No security-gated operation (PowerShell, registry write, deep repair, office arbitrary code) executes without passing its gate, and no refusal is bypassed via another service — verifiable in the audit log for every trial including adversarial "gate-shopping" prompts.
- **SC-004**: A long-running job (>30 s) completes without any single held-open streamed call — verifiable by timing profiles in the audit log.
- **SC-005**: Skills saved by the system are reusable across restarts and (parameterized) across hosts — a skill recorded on one machine names no machine-specific literal that breaks execution on another.
- **SC-006**: Every failed reused skill escalates to a human admin within two attempts (one retry), 100% of trials.

## Assumptions

- The existing Hermes gateway + sidecar + audit infrastructure (specs 027–034) is the substrate; this feature extends routing and adds services rather than replacing them.
- The office service already covers Word/Excel/PowerPoint (verified against its upstream project); Outlook/Notes/Calendar tooling gaps, if any, are handled within the office service, not by another lane.
- Dynamic browser control and scripted browser control are two distinct services with one shared engine (Playwright); the split is about determinism and auditability, not engine choice.
- The task-API gateway exposes structured JSON APIs only; raw console-output parsing never reaches the agent.
- Fleet multi-host support is designed-for but v1-deployed on the single existing client; per-host enrollment machinery may land in a later feature.
- The user's draft agent routing prompt is the starting text; its Rule 2 office-scope error is corrected by FR-007, and its "ALWAYS confirm destructive operations" constraint aligns with the gate architecture.
- Trusting a skill requires both a success-rate threshold (80%) and a minimum sample size (a reasonable default like 3 successes) — exact threshold values are tunable, not load-bearing for the architecture.