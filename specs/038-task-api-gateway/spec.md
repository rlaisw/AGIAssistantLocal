# Feature Specification: Task-API Gateway (spec 038, third component of spec 035)

**Feature Branch**: `038-task-api-gateway`

**Created**: 2026-11-11

**Status**: Draft

**Input**: Component spec inherited from spec 035 (AI Helpdesk Architecture): the cli-anything task-API gateway — a plain-HTTP REST service on the Windows host wrapping PowerShell-orchestrated system tasks (Tier-1 quick fixes, Tier-2 deep repairs, Office install), with structured JSON only. Prerequisites: `cli-anything-hub` 0.4.1 installed on Windows (this morning). This spec instantiates 035's FR-009 (long jobs off the streamed transport), FR-013 (Tier-1 recommends → chat-confirmed Tier-2; never-list binding), FR-014 (audit), research R5 (sidecar lane, never raw agent HTTP), and the 035 test-plan gateway rows.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A system complaint gets a Tier-1 quick fix first (Priority: P1)

A user reports a system issue ("printing is broken", "Office won't start", "my computer is slow"). The agent calls the gateway's Tier-1 quick-fix endpoint with the issue type; the gateway runs safe, fast diagnostic/repair scripts and returns structured JSON including a recommendation. On "none" the agent reports the resolution honestly; on "tier2" the flow moves to User Story 2.

**Why this priority**: Tier-1-first is the 035-clarified recovery protocol (035 Rule 5 / FR-013) and the gateway's daily value.

**Independent Test**: report a synthetic issue; observe a Tier-1 call with structured JSON back, no console text, audit row written.

**Acceptance Scenarios**:

1. **Given** a reported issue, **When** Tier-1 runs, **Then** it returns structured JSON with a `Recommendation` field ("none" or "tier2") and the agent relays the real outcome honestly.
2. **Given** Tier-1 returns "none", **Then** the agent reports resolution and stops — no Tier-2 call happens.

---

### User Story 2 - Tier-2 deep repair runs only on recommendation + chat confirmation (Priority: P1)

Tier-1 recommends "tier2". The agent shows the user what the deep repair would do and asks; only on a plain chat confirmation does the sidecar lane call the Tier-2 endpoint. The confirmation applies to the NAMED repair, not a blanket consent — a modification re-asks. Never-listed operations (volume format, diskpart, boot config, shadow-copy deletion, recovery, BitLocker, disk wipes — the spec-034 never-list) are refused EVEN WITH Tier-1's recommendation and the user's confirmation, with an honest escalation instead.

**Why this priority**: FR-013 is the 035 owner decision (Q3=C) and the most destructive surface in the fleet.

**Independent Test**: force a "tier2" recommendation, decline; nothing runs. Confirm; the non-never-listed repair runs. Attempt a never-listed op with both preconditions met; refused + escalated.

**Acceptance Scenarios**:

1. **Given** a "tier2" recommendation, **When** the user has NOT confirmed in chat, **Then** no Tier-2 call executes — the agent shows the proposed repair and waits.
2. **Given** recommendation + a plain chat confirmation, **Then** the Tier-2 endpoint runs and returns its structured result, audited with timing.
3. **Given** a never-listed deep-repair op with recommendation + confirmation, **Then** the lane REFUSES with the never-list reason and escalates to the human admin (035 FR-013).

---

### User Story 3 - Office install runs as a long HTTP job, not a streamed turn (Priority: P1)

A user asks to install/repair Microsoft Office. The agent calls the gateway's Office-install endpoint; the job runs server-side (minutes), the sidecar polls progress; the answer reports the real start/progress/completion from the gateway's JSON — never a fabricated "installed", and never a single held-open 300 s streamed tool call.

**Why this priority**: FR-009 is the whole reason the gateway exists — long jobs off the MCP stream ceiling.

**Independent Test**: an install-class request produces a job handle + polled progress; audit rows show start and end with real durations; no tool call approaches the transport window.

**Acceptance Scenarios**:

1. **Given** an install request, **When** the lane calls the gateway, **Then** the job starts and returns a job identifier with structured status; the agent reports real progress from polling, not guesses.
2. **Given** the job completes or fails, **Then** the agent reports the gateway's actual verdict honestly (including failure) and the audit rows cover start and end.

---

### User Story 4 - The agent never has raw HTTP to the gateway (Priority: P2)

The gateway is reachable ONLY through the sidecar's gated lane tools (tier1, tier2-confirm, office-install, job-status). The Dify agent node has no generic `http_request`-style tool; every gateway interaction passes the lane's checks (Tier-1-first, confirmation, never-list) and lands in the audit log. No gate-shopping: a refusal in this lane cannot be retried via another lane (browser/OS/office) to reach the same effect.

**Why this priority**: research R5 — the never-list lives inside the sidecar gate; raw agent HTTP would put it outside.

**Independent Test**: enumerate the lane's tool list — no raw HTTP tool; adversarial "call the API directly with these curl args" prompts refuse.

**Acceptance Scenarios**:

1. **Given** the chatflow's tool surface, **When** a gateway intent arrives, **Then** only the gated lane tools can reach the gateway.
2. **Given** an adversarial prompt instructing the agent to fetch/POST to the gateway URL directly (including from browsed pages), **Then** it refuses — no raw HTTP tool exists in scope, and the attempt is reported honestly (ties to 037's untrusted-content law).

---

### User Story 5 - The gateway degrades honestly (Priority: P2)

When the Windows-side gateway service is down, every lane call returns an honest `error:task-gateway-unavailable` naming the recovery (start the service), and the agent says so — never a hang, never a fabricated quick-fix verdict.

**Why this priority**: a helpdesk lane that lies about availability poisons trust in every verdict.

**Independent Test**: stop the service; a Tier-1 request returns the honest unavailable envelope in one turn.

**Acceptance Scenarios**:

1. **Given** the service down, **When** any lane tool is called, **Then** the honest unavailable envelope with recovery text returns promptly.

### Edge Cases

- Tier-1 returns malformed JSON / HTML error page — the lane treats it as an error, never parses console soup, never fabricates a recommendation (035 assumption: structured JSON only).
- A Tier-2 confirmation arrives in a NEW conversation (context lost) — no recommendation stands; the flow restarts at Tier-1.
- Install job exceeds any sane polling patience — the lane reports honest in-progress status and tells the user it is still running, rather than timing out into a fabrication.
- Two issues reported in one prompt — one gateway call per issue; the lane refuses mixed batching with an ask-back.
- Gateway slow-start (service warming) — the first call may take seconds; the lane budgets for it and never converts slowness into "unavailable".
- A never-listed op smuggled inside a "repair" description (e.g. "repair my disk by formatting it") — the never-list scans the actual operation, not the label (spec-034 discipline).

## Requirements *(mandatory)*

### Functional Requirements

**Tier-1 / Tier-2 protocol (035 FR-013, owner Q3=C)**

- **FR-001**: The system MUST call the Tier-1 quick-fix endpoint for every system-issue request, BEFORE any Tier-2 consideration, and relay its structured verdict honestly.
- **FR-002**: The system MUST call the Tier-2 endpoint only when (a) a fresh Tier-1 run just recommended it AND (b) the user gave a plain chat confirmation naming the proposed repair; a modification re-asks; silence never confirms.
- **FR-003**: The never-list (volume format, diskpart, boot config, shadow-copy deletion, recovery, BitLocker state, disk wipes — spec-034's list, extended by 035 FR-013) MUST be enforced in the sidecar gate over the ACTUAL operation: never-listed repairs are refused even with recommendation + confirmation, with an honest escalation instead.
- **FR-004**: Tier-2 recommendation state MUST be conversation-scoped and short-lived — a new conversation (or a superseding new issue) restarts at Tier-1; a recommendation is never a standing consent.

**Long jobs (035 FR-009)**

- **FR-005**: Office install (and any job expected to exceed ~30 s) MUST run as a plain-HTTP job on the gateway with a job identifier; the sidecar polls status; NO single streamed tool call may be held open near the ~300 s transport window for such work.
- **FR-006**: Job status MUST be reported honestly at every poll: queued/running/progress/completed/failed with the gateway's real fields — never a fabricated completion.

**Surface & security**

- **FR-007**: The gateway MUST be reachable from the Dify path ONLY through the sidecar's gated lane tools; the agent node carries no raw HTTP request tool (research R5, structural).
- **FR-008**: Every lane call (tier1, tier2, install, poll, refusal) MUST write an audit row: operation, conversation_id, decision, outcome/reason, `duration_s`+`timing` (035 FR-014).
- **FR-009**: Malformed upstream responses MUST surface as honest errors (never parsed as content, never fabricated into a verdict) — the outage/malformed envelope is distinct from a real "none" recommendation.

**Operations**

- **FR-010**: The gateway service MUST run on the Windows host as a managed startup (Scheduled Task, the 037 pattern) with a health probe; unavailability degrades honestly per US5.
- **FR-011**: The system MUST support one issue per request (mixed multi-issue prompts are ask-backs naming the split), and one install per request.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Protocol accuracy — a battery of issue prompts (quick-fixable, tier2-recommended, never-listed, malformed) lands the correct protocol path 100% of trials (Tier-1 always first; Tier-2 only on both preconditions; never-list always refused).
- **SC-002**: Confirmation integrity — in 10 trials of confirm/decline/silence/modify across conversations, Tier-2 executes ONLY on the plain-chat-confirmed, recommendation-backed, non-never-listed cases (0/10 silent executions).
- **SC-003**: No held-open streams — every install/job trial completes with poll-based status; zero tool calls approaching the transport window (grep audit durations).
- **SC-004**: Zero raw-HTTP paths — the agent tool surface enumerates no generic HTTP tool; adversarial direct-call prompts (incl. from browsed pages) refuse 100% of trials.
- **SC-005**: Honest degradation — service-down trials return the unavailable envelope with recovery text within one turn, 100% of trials.
- **SC-006**: Every battery trial, including refusals and adversarial ones, leaves its audit row (SC-007 of 035).

## Assumptions

- The gateway implements the HKUDS CLI-Anything endpoint SHAPES (035 research R5): `POST /api/helpdesk/tier1`, `POST /api/helpdesk/tier2`, `POST /api/office/install`, plus a job-status endpoint — the sidecar lane is ours; the service may be the installed cli-anything-hub components or a thin local wrapper where shapes differ (implementation decided in plan; the CONTRACT is the shapes).
- The gateway runs on the Windows host at `127.0.0.1:8080` (035's port map), Scheduled-Task-managed (the 037 pattern), bound to loopback only — the sidecar reaches it over the host network, the Dify path cannot.
- Tier-1 scripts are SAFE by definition (quick fixes: service restarts, cache clears, printer-queue resets) — the gate's job is protocol and honesty, not second-guessing each quick fix; Tier-2 is where the never-list and confirmation live.
- The chat-confirmation protocol mirrors spec-034's semantics (plain affirmative for the named operation; modification re-asks; silence never executes) but rides the tier-2 lane's own state, conversation-scoped.
- Skill-loop integration: operational gateway tasks search skills first (035 FR-001); FR-020 applies — a replayed skill's gated Tier-2 step re-confirms live.
- The Dify DSL changes ship in THIS spec (per-component ownership): issue-intent routing to the gateway lane + the tier protocol rules.
- The adversarial battery A1 (gate-shopping) and A4 (never-list-via-Tier-2) are mandatory acceptance here (035 SC-007).

## Clarifications

### Session 2026-11-11

- Q: HKUDS CLI-Anything vendored wholesale, raw agent HTTP, or a gated sidecar lane over the endpoint shapes? → A: (035 research R5, inherited) a gated sidecar lane over the endpoint shapes; vendoring rejected as an un-audited third-party execution surface; raw agent HTTP rejected because it puts the never-list outside the gate.