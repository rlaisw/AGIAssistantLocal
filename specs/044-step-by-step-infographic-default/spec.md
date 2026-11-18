# Feature Specification: Default step-by-step infographic template policy

**Feature Branch**: `044-step-by-step-infographic-default`

**Created**: 2026-11-18

**Status**: Draft

**Input**: User description: "set DEFAULT step-by-step infographic to sequence-roadmap-vertical-pill-badge; secondary priority sequence-timeline-done-list; third priority list-row-horizontal-icon-arrow" (with intent confirmed in conversation, 2026-11-18)

## Clarifications

### Session 2026-11-18

- Q: Where does "set the default" apply — engine, sidecar, or chat steering? → A: **Chat steering.** The `antv_infographic` tool (spec 012) already renders any of the engine's 276 templates; the owner's directive is a **template-selection policy** for step-by-step content: the agent's infographic generation must default to `sequence-roadmap-vertical-pill-badge`, falling back to `sequence-timeline-done-list`, then `list-row-horizontal-icon-arrow`. The rule lands in the chatflow's steering text (the tool description / answer-format guidance in the DSL); the sidecar's declarative pass-through and the rendering page are unchanged.
- Q: If you explicitly name a different template for a step-by-step infographic, should your explicit choice win over the default chain? → A: Yes — an explicit user-named template always wins; the chain applies only when the request names no template (Option A, confirmed 2026-11-18).
- All three template IDs were verified present in the pinned engine bundle (`@antv/infographic@0.2.20`, CDN probe 2026-11-18) — the spec names them as confirmed IDs, not placeholders.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A step-by-step ask renders the roadmap-pill infographic (Priority: P1)

The owner asks for a step-by-step / how-to / process infographic ("make an infographic showing how to do X, step by step"). The agent generates the declarative infographic with the **`sequence-roadmap-vertical-pill-badge`** template, and the returned page link opens a vertical roadmap with pill badges — the same content, the same steps, now in the owner's preferred default shape.

**Why this priority**: This is the whole directive — one default template for one content family, applied every time.

**Independent Test**: One live step-by-step infographic ask; assert the rendered page's syntax carries `sequence-roadmap-vertical-pill-badge`.

**Acceptance Scenarios**:

1. **Given** a step-by-step/process infographic request, **When** the agent generates it, **Then** the syntax names `sequence-roadmap-vertical-pill-badge` and the page renders (no blank/fallback div).
2. **Given** the same request with different step counts (3, 8, 15 steps), **When** rendered, **Then** the roadmap-pill layout is used every time — the default does not depend on step count.

---

### User Story 2 - The fallback chain is ordered and honest (Priority: P2)

When the primary template genuinely does not fit the content shape or fails to render, the agent falls back in the owner's priority order: first **`sequence-timeline-done-list`**, then **`list-row-horizontal-icon-arrow`** — never a silently different arbitrary template. If none of the three fits, the answer says so honestly instead of forcing a bad layout.

**Why this priority**: A default without an ordered fallback either breaks or silently reverts to arbitrary picks; the owner's directive defines the full chain.

**Independent Test**: Content-shaped mismatch cases (e.g. a done-list of completed items; a flat short list) and a forced render failure; assert the chain order and honest refusal at the end.

**Acceptance Scenarios**:

1. **Given** step content that the roadmap-pill template cannot represent (agent-judged shape mismatch), **When** generating, **Then** `sequence-timeline-done-list` is used before any other template.
2. **Given** both sequence templates unsuitable, **When** generating, **Then** `list-row-horizontal-icon-arrow` is used.
3. **Given** none of the three templates fits the content, **When** asked, **Then** the answer states the limitation honestly rather than rendering a misshapen infographic.
4. **Given** the owner explicitly names a template for stepwise content ("use the timeline-done-list one"), **When** generating, **Then** the named template is used — an explicit user choice always wins over the default chain.

---

### User Story 3 - Everything else is unchanged (Priority: P3)

Non-step-by-step infographics (charts, hierarchies, comparisons, quadrants, plain lists that are not stepwise) keep today's behavior exactly: any family/template may be chosen as before, and the spec 012 tool surface (link-not-inline relaying, honest errors, 276 templates) is untouched.

**Why this priority**: The directive must be additive steering for one content family — no scope creep into the other families.

**Independent Test**: The existing antv battery (`antv-infographic`, `chart-in-deck` scenarios) re-runs green unchanged.

**Acceptance Scenarios**:

1. **Given** a non-sequential infographic request (e.g. a quadrant or comparison), **When** generated, **Then** the template choice follows today's behavior — the new default never applies.
2. **Given** the full spec 012 acceptance battery, **When** re-run, **Then** all previously-green scenarios stay green.

---

### Edge Cases

- A step-by-step request phrased without the word "step" ("show me the process", "how do I…, as a visual") still counts as stepwise content — the policy keys on content shape, not keywords alone.
- An explicit user-named template for stepwise content overrides the chain entirely — the default policy never argues with a named choice.
- A request mixing stepwise and non-stepwise content (a process plus a comparison table) — the stepwise part defaults to the roadmap-pill template only if the whole infographic is stepwise; a genuine mix may use a different family, honestly.
- The engine's template registry could rename IDs in a future version — the rule names the pinned v0.2.20 IDs; a CDN upgrade is a deliberate re-verification, not automatic.
- The engine CDN unreachable → the existing honest error path (spec 012) applies unchanged; the policy adds no new failure modes.
- Long step texts may overflow the pill layout — the agent may trim step labels to their essence, but never invents or drops steps to make a template fit (honesty over aesthetics).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Any infographic whose content is a sequence of steps (how-to, process, procedure, tutorial — by content shape, not keyword alone) MUST be generated with the `sequence-roadmap-vertical-pill-badge` template by default.
- **FR-002**: The fallback chain MUST be ordered exactly: primary `sequence-roadmap-vertical-pill-badge` → `sequence-timeline-done-list` → `list-row-horizontal-icon-arrow`; a template is skipped only on genuine shape mismatch or render failure, and never in favor of a template outside the chain for stepwise content — **except when the user explicitly names a template: an explicit user choice always wins over the chain** (the chain is the *default*, applying only when the request names no template).
- **FR-003**: If none of the three templates fits, the answer MUST state that honestly (no forced layout, no fabricated steps to make a template fit).
- **FR-004**: The policy MUST apply only to stepwise content: chart / hierarchy / relation / compare / quadrant families and non-stepwise lists keep their existing, unrestricted template behavior.
- **FR-005**: The rule MUST live in the chatflow's steering surface (the `antv_infographic` tool description and/or answer-format guidance in the published chatflow) — the sidecar's declarative pass-through, the rendering page, and the tool schema are unchanged (additive steering only, Constitution I).
- **FR-006**: The three template IDs are those of the pinned engine version (`@antv/infographic@0.2.20`); any engine/CDN version bump MUST re-verify the IDs before the policy keeps applying them (verify-first, documented in the change).

### Key Entities

- **Stepwise content shape**: a sequence of steps (ordered actions/phases) recognized by content, regardless of phrasing — the trigger for the policy.
- **Template priority chain**: the ordered triple (`sequence-roadmap-vertical-pill-badge`, `sequence-timeline-done-list`, `list-row-horizontal-icon-arrow`) — confirmed IDs in the pinned engine registry.
- **Steering surface**: the chatflow's tool-description / answer-format text where the selection rule lives; all other spec 012 entities (declarative syntax, render page, link relaying) unchanged.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A live step-by-step infographic ask renders the roadmap-pill template — the returned page's syntax names `sequence-roadmap-vertical-pill-badge` and the page shows content (10/10 consecutive stepwise asks over the battery).
- **SC-002**: Shape-mismatch probes produce the chain in order (timeline before list-row), and a no-fit case produces an honest limitation statement — 0 arbitrary-template stepwise renders.
- **SC-003**: The existing spec 012 acceptance battery (antv-infographic, chart-in-deck) and the chatflow verification suite stay green — 0 regressions on non-stepwise infographic behavior.

## Assumptions

- The chatflow steering text is the single lever; no prompt-engine or sidecar code change is required (the sidecar already accepts any template ID the syntax names).
- The engine's pinned CDN version (0.2.20) remains the runtime; the template IDs verified against it on 2026-11-18 carry forward until a deliberate version bump.
- The policy is documented in the chatflow DSL prompt only; spec 012's published contract is untouched (no Supersedes — this is an additive usage directive layered on 012).
- Publishing follows the established path: DSL edit → `python -m agentic_rag_mcp.deploy chatflow` (or `all`) → live verify.
