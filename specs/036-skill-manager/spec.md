# Feature Specification: Skill Manager (spec 036, first component of spec 035)

**Feature Branch**: `035-ai-helpdesk-architecture`

**Created**: 2026-11-11

**Status**: Draft

**Input**: Component spec inherited from spec 035 (AI Helpdesk Architecture): the Skill Manager — server-side shared skill store with semantic intent search, parameterized workflow records, versioned updates, trust-based reuse, and feedback-driven decay. This spec instantiates spec 035's data model (Skill/Step/SkillFeedback), contracts (skill_search/get/save/feedback API shapes), and test-plan sections 1a/1b, E1/E5/E6, and A3 for the Skill Manager surface.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A novel task becomes a reusable skill (Priority: P1)

A user asks the assistant for an operational task no saved skill matches. The agent solves it manually through the existing lanes; on success it saves the run as a new skill — snake_case name, trigger-keyword description, tier, parameterized workflow with per-step expected outcomes, version 1. The save is audited.

**Why this priority**: This is the learning half of the loop — without trustworthy saving, nothing else in the component has value.

**Independent Test**: Perform a novel task end-to-end; verify the skill row exists with version 1 and an audit row; verify the search finds it by intent next time.

**Acceptance Scenarios**:

1. **Given** no matching skill, **When** an operational task completes successfully, **Then** a skill is saved with name/description/tier/workflow(version 1, per-step expects) and an audit row records the save.
2. **Given** a save attempt whose workflow contains a machine-specific literal (e.g., a user-profile path), **When** saved, **Then** the save is rejected naming the literal — only `{{parameterized}}` templates enter the store.

---

### User Story 2 - A saved skill is found by intent and reused only when trusted (Priority: P1)

On the next similar intent, the skill store is searched semantically BEFORE the task executes. A found skill is auto-reused only when its success history clears both thresholds (rate > 80% and ≥3 successes); otherwise the agent solves manually and updates the skill on success.

**Why this priority**: This is the reuse half — the round-trip that makes the fleet learn.

**Independent Test**: Seed skills at various trust levels; issue the same intent; observe reuse exactly when trusted, manual solve otherwise.

**Acceptance Scenarios**:

1. **Given** a trusted skill (rate > 80%, ≥3 successes), **When** a similar intent arrives, **Then** the search surfaces it with its trust data, and the workflow replays with live parameter substitution.
2. **Given** a matching skill below the sample floor (e.g., 100% rate but 2 successes), **When** the intent arrives, **Then** it is NOT auto-reused — manual solve, then same-name update.
3. **Given** a matching skill whose failures dropped its rate below 80%, **When** the intent arrives, **Then** it is demoted to manual-solve-and-update without any time-based expiry.

---

### User Story 3 - Feedback closes the loop with escalation, never deletion (Priority: P1)

Every reuse attempt records success or failure feedback. A failing reused skill retries once with adjusted parameters; success updates the skill in place (version+1); a second failure records honest failure feedback and escalates to the human admin. The system never deletes a skill.

**Why this priority**: Trustworthy failure handling is what makes auto-saved skills safe; it completes the loop the architecture depends on.

**Independent Test**: Seed a failing skill; run the intent; observe retry → update or feedback → escalation, and confirm the skill still exists afterward.

**Acceptance Scenarios**:

1. **Given** a failed reuse, **When** the retry succeeds after adjustment, **Then** the skill updates under the SAME name with version+1.
2. **Given** a failed reuse whose retry also fails, **Then** failure feedback (with error context) is recorded, the turn escalates honestly, and the skill remains in the store.

---

### User Story 4 - Gated steps in a replayed skill re-confirm live (Priority: P2)

When a reused workflow contains a confirm-gated step (PowerShell, registry write, Tier-2, RunPython), replay pauses and the gated step passes its own live draft→confirm gate at execution time. The skill record alone never executes anything gated.

**Why this priority**: Spec 035 FR-020 is the security invariant that keeps skill replay from becoming a bypass; it must be acceptance-tested, not just designed.

**Independent Test**: Seed a trusted skill containing a gated step; replay it; observe the live confirm prompt and zero gated execution without it.

**Acceptance Scenarios**:

1. **Given** a trusted skill whose workflow includes a gated step, **When** it replays, **Then** execution pauses at that step for a live confirm — the record pre-confirms nothing.
2. **Given** a replayed gated step the user cancels, **Then** the pending confirm clears (spec-034 rules) and the workflow aborts honestly without marking the skill itself failed.

---

### User Story 5 - The store degrades gracefully (Priority: P2)

When the skill store is unavailable, operational tasks still complete: the agent says so honestly, skips learning, and routes manually. Questions/chat are unaffected (they never touched the loop).

**Why this priority**: The store is a new single point of learning, never a single point of failure for the helpdesk itself.

**Independent Test**: Stop the store; run an operational task and a question; observe completion with an honest notice, and no learning.

**Acceptance Scenarios**:

1. **Given** the store unreachable, **When** an operational task runs, **Then** it completes via manual routing with an honest degradation note; zero feedback is silently dropped.
2. **Given** the store unreachable, **When** a question/chat turn runs, **Then** nothing changes — questions never consulted the store (FR-001 scope).

### Edge Cases

- Semantic near-miss: a plausible-but-wrong skill matches the intent — the executor's first failed per-step `expect` aborts the replay honestly; the agent falls back to manual solve.
- Unknown skill name on retrieval — explicit not-found, never an empty workflow silently executing.
- Two skills match with similar confidence — deterministic preference: higher success history, then lower tier, then more recent version.
- Empty or whitespace name/description on save — rejected at the boundary.
- Workflow step missing its `expect` field — rejected (FR-006: every step carries one).
- Skill name collision from a different host (fleet later) — same name = same skill globally (shared store, clarified in 035); versioning absorbs divergence.
- Store corrupted/restarted mid-save — SQLite transactional guarantees; a partial save never becomes a trusted skill.

## Requirements *(mandatory)*

### Functional Requirements

**Search & reuse (from 035 FR-001/003)**

- **FR-001**: The system MUST search the store by semantic intent match before executing any operational task, and surface found skills WITH their trust data (rate, sample) so the reuse decision is made on the numbers, not the model's mood.
- **FR-002**: The system MUST auto-reuse a skill only when success rate > 80% AND successes ≥ 3; below either, manual solve with same-name update on success.
- **FR-003**: The system MUST NOT apply time-based or environment-stamped expiry — decay is feedback-driven only (failures lower the rate, demotion is automatic).

**Persistence & integrity**

- **FR-004**: The system MUST record for every skill: snake_case name (identity key), trigger-keyword description (the semantic search surface), tier (1|2), parameterized workflow (steps: tool, service, params-template, expect), version, success/failure counts, timestamps.
- **FR-005**: The system MUST reject any save whose workflow step lacks `expect`, whose params-template contains machine-specific literals (user paths, hostnames), or whose name/description is empty — with the offending field named.
- **FR-006**: Same-name saves MUST update in place with version+1; the store NEVER contains two versions of one skill simultaneously as separate reusable records.
- **FR-007**: The system MUST persist skills across restarts (the store survives sidecar/service restarts; SC-005 of 035).

**Feedback & escalation**

- **FR-008**: Every reuse attempt MUST append one feedback record (outcome, error context on failure, timestamp) — append-only.
- **FR-009**: After two consecutive failed attempts the system MUST record the failure feedback, keep the skill, and surface an honest escalation to the human admin; deletion of skills is never automated.

**Replay security (from 035 FR-020)**

- **FR-010**: A replayed workflow's gated steps MUST each pass their own live gate (draft→confirm) at execution time; the skill record never pre-confirms, and a cancelled confirm clears per spec-034 rules.
- **FR-011**: Replay MUST substitute per-request values into params-templates; an unfilled placeholder is an honest ask-back, never a guessed substitution.

**Scope & degradation**

- **FR-012**: Questions, chat, and knowledge-base lookups MUST NOT consult the skill store (035 FR-001 scope).
- **FR-013**: Store unavailability MUST degrade gracefully: honest notice, manual routing, task completes, learning skipped — never a hang or a fabricated "skill not found" that masks an outage.

**Audit (from 035 FR-014)**

- **FR-014**: Every skill operation (search, get, save/update, feedback, replay start/abort) MUST write an audit row with operation, outcome, and duration/timing, append-only.

### Key Entities *(include if feature involves data)*

Inherited verbatim from spec 035's [data-model.md](../035-ai-helpdesk-architecture/data-model.md): **Skill** (with Step), **SkillFeedback**; the store lives server-side (WSL), one shared store. **AuditRecord** extended with `skill-*` operation names.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The learned round-trip works: a novel task saved once is found and reused (without manual re-solve) on its next occurrence in ≥9 of 10 trials (inherited from 035 SC-001).
- **SC-002**: Trust gating is exact: in a seeded matrix of rate/sample combinations, auto-reuse occurs iff rate > 80% AND successes ≥ 3 — 100% of matrix cells.
- **SC-003**: No gated step in any replayed skill executes without a live confirm — verified by adversarial trial A3 (035 test-plan) with its audit rows; any silent execution is a failure.
- **SC-004**: Skills survive restart unchanged: save → restart the store → search returns the identical record (byte-equal fields), 100% of trials.
- **SC-005**: Every failed reuse escalates within two attempts with the skill intact, 100% of trials; zero automated deletions ever.
- **SC-006**: Store-down degradation completes 100% of operational trials with an honest notice, and never blocks a question/chat turn.

## Assumptions

- The Skill Manager runs server-side on WSL beside the existing stack (035 clarification), as sidecar-adjacent tooling — the agent reaches it through the Dify lane, not raw HTTP.
- Semantic search rides the existing embeddings/vector-stack path in the sidecar (research R1 of 035); SQLite persists the transactional records.
- The routing/agent-side "when to search" decision is the classifier lane's job (035 FR-017); this spec owns the store, the search, the executor's substitution/verification, and the feedback surface.
- Trust thresholds (80%, ≥3) are the 035-clarified defaults; they are config-tunable but the spec pins their default behavior.
- Multi-host fleet considerations (host tags, cross-host name collisions) are designed-for but v1 ships on the single existing client; enrollment is out of scope here.
- Chatflow DSL changes for the skill loop (classifier prompt rules, lane instructions) ship in THIS spec per the per-component DSL ownership rule (035 clarification).
- The adversarial battery A1–A6 subset applicable here (A3 skill-replay bypass, A6 fabricated completion) is mandatory in acceptance (035 SC-007).