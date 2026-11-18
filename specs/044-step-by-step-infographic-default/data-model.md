# Data Model — 044-step-by-step-infographic-default

No new storage entities: the feature is a steering rule inside the chatflow prompt. The entities below are the conceptual objects the rule binds; the only persisted artifact is prompt text in the chatflow DSL (and this spec set).

## Steering rule (the one new "entity")

| Field | Value | Notes |
|---|---|---|
| trigger | stepwise content shape | a sequence of steps (how-to / process / procedure / tutorial), by content — not keyword ("step") alone; mixed stepwise+non-stepwise content is judged as a whole (spec edge case) |
| default_template | `sequence-roadmap-vertical-pill-badge` | applied whenever the trigger fires and no template was named |
| fallback_2 | `sequence-timeline-done-list` | only on genuine shape mismatch or render failure of the primary |
| fallback_3 | `list-row-horizontal-icon-arrow` | only when fallback_2 also cannot serve |
| override | explicit user-named template always wins | clarify Option A (2026-11-18): the chain is the *default*, applying only when the request names no template |
| terminal_behavior | honest limitation statement | if none of the three fits: say so — never force a layout, never invent/trim steps to fit a template (Constitution IV) |
| scope | stepwise content only | chart / hierarchy / relation / compare / quadrant families and non-stepwise lists: existing behavior unchanged |
| binding_sites | 2 prompt surfaces in `dify/AGIAssistant/AGI_Assistant.yml` | the `antv_infographic` tool-description bullet; the ANSWER FORMAT — VISUALS section (covers proactive summary cards too) |

## Validation rules (from the spec's FRs)

- The chain order is exact and closed: primary → `sequence-timeline-done-list` → `list-row-horizontal-icon-arrow`; a skip happens only on shape mismatch or render failure; nothing outside the chain for stepwise content unless the user named it (FR-002).
- Template IDs are registry names of the pinned `@antv/infographic@0.2.20`; a version bump re-verifies before the rule keeps applying them (FR-006).

## Unchanged entities (explicitly)

- **antv_infographic tool** (spec 012): schema, declarative syntax pass-through, stored-page serving, page-URL relaying — all identical.
- **antv_chart tool**: untouched; the policy never applies to statistical charts.
- **Infographic page**: the rendered HTML contract (embedded syntax, engine CDN, fallback div) is unchanged.
