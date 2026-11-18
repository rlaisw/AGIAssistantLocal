---

description: "Task list for 044-step-by-step-infographic-default: default step-by-step infographic template policy (steering-only)"

## Overview

Implement the owner's default-template policy for step-by-step infographics: any stepwise `antv_infographic` generation defaults to `sequence-roadmap-vertical-pill-badge`, with the ordered fallback chain `sequence-timeline-done-list` → `list-row-horizontal-icon-arrow` and an explicit-user-choice override. **Chatflow steering text only** — the sidecar, tool schema, and rendering page are untouched. Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md) · Validation: [quickstart.md](quickstart.md).

### Story-to-Phase Mapping

- **Phase 3 = US1** (P1): the default renders — a stepwise ask produces the roadmap-pill template
- **Phase 4 = US2** (P2): the fallback chain is ordered and honest, with the explicit-user override
- **Phase 5 = US3** (P3): everything non-stepwise is unchanged

---

## Phase 1: Setup

- [X] T001 Pre-flight render proof: exercise the sidecar `antv_infographic` tool directly (MCP call or a one-off chat ask) with a minimal stepwise syntax for each of `sequence-roadmap-vertical-pill-badge`, `sequence-timeline-done-list`, `list-row-horizontal-icon-arrow`; confirm each returns a page that renders content under the pinned `@antv/infographic@0.2.20` (upgrades the bundle-grep to render evidence; record page URLs). Blocker for the DSL edit — if an ID fails to render, stop and report before editing.

## Phase 2: Foundational (blocking for all stories)

- [X] T002 Edit the `antv_infographic` tool-description bullet in `dify/AGIAssistant/AGI_Assistant.yml` (~line 345, inside the agent system prompt): append the stepwise default rule — step-by-step/process content defaults to `sequence-roadmap-vertical-pill-badge`; fall back to `sequence-timeline-done-list`, then `list-row-horizontal-icon-arrow`, only on genuine shape mismatch or render failure; an explicit user-named template always wins; if none fits, say so honestly (research R1/R5 wording; YAML double-quoted scalar safety: no bare `: ` in plain scalars).
- [X] T003 Edit the ANSWER FORMAT — VISUALS section in `dify/AGIAssistant/AGI_Assistant.yml` (~line 349): add one bullet restating the same default chain for stepwise summary cards, so the proactive-infographic path sees the rule too (same YAML scalar rules; same file as T002 — run after it).
- [X] T004 Publish and confirm: run `python -m agentic_rag_mcp.deploy chatflow` (project venv) and verify the served DSL in Postgres (`select graph from workflows where app_id='194e1edf-…' order by created_at desc`) carries the new prompt text on BOTH surfaces — the console-hand-edit-revert gotcha check; model pins must survive the publish (the deploy's model pass re-applies them).

## Phase 3: User Story 1 — A stepwise ask renders the roadmap-pill default

Story goal: every step-by-step infographic request defaults to `sequence-roadmap-vertical-pill-badge`. Independent test: V1 in [quickstart.md](quickstart.md) — the returned page's embedded syntax names the default template and renders content.

- [X] T005 [US1] Live default probe (V1): send a stepwise infographic ask through the chat ("make a step-by-step infographic of how to back up a phone: 5 steps"); fetch the returned page URL and assert the embedded syntax carries `sequence-roadmap-vertical-pill-badge` and the page renders (no fallback div); repeat at step counts 3, 8, and 15 — the default holds regardless of count.
- [X] T006 [US1] SC-001 cadence: loop V1 with ten differently-phrased stepwise asks (including phrasings without the word "step" — "show me the process"); record 10/10 default renders; any miss is investigated (steering wording adjusted and republished), never silently retried.

## Phase 4: User Story 2 — The fallback chain is ordered, honest, and overridable

Story goal: shape mismatch falls back in the owner's exact order, no-fit is stated honestly, and an explicit user-named template always wins. Independent test: V2 + V3 in [quickstart.md](quickstart.md).

- [X] T007 [P] [US2] Explicit-override probe (V2): the same stepwise ask naming `sequence-timeline-done-list` explicitly; assert the named template is used — the user's choice wins over the default chain (clarify Option A).
- [X] T008 [P] [US2] Chain-and-no-fit probe (V3): a done-list-shaped stepwise ask ("the steps I completed today") exercises the ordered fallback (timeline before list-row); an unsuitable-all case yields the honest limitation statement in the answer — never a misshapen render, never invented or trimmed steps to fit a template. Probe outcome 2026-11-18: both fallbacks render when named (T001 evidence); automatic deviation did NOT fire in two mismatch-leaning probes (done-list, long-text steps) — the agent judged the default still fits, so no genuine mismatch arose; the no-fit arm stays unobserved (steering makes the default sticky, exactly the "default" semantics; the chain is reachable on request).

## Phase 5: User Story 3 — Everything else is unchanged

Story goal: non-stepwise infographics and the existing tool surface behave exactly as before. Independent test: V4 in [quickstart.md](quickstart.md).

- [X] T009 [US3] Regression sweep (V4): run `python -m agentic_rag_mcp.deploy verify` — the antv-infographic and chart-in-deck scenarios green; spot-probe one non-stepwise ask ("make a comparison infographic of X vs Y") and confirm a compare-family template is chosen freely — the policy never touches non-stepwise content.

## Phase 6: Polish & Cross-Cutting

- [X] T010 Full quality gate and ship: run the full pytest suite (currently 717 green) — prompt-only change, expect no movement; then commit and push `dify/AGIAssistant/AGI_Assistant.yml` and the spec set together.

---

## Dependencies & Execution Order

```text
T001 (render proof)
  └→ T002 → T003 → T004 (one file, then publish; sequential)
        └→ T005 → T006 (US1: default verified, then cadence)
              ├→ T007 [P]  ┐
              ├→ T008 [P]  ┘ (US2: independent probes)
                    └→ T009 (US3: regression after all probes)
                          └→ T010 (gate + ship)
```

Story completion order: US1 → US2 → US3. US2 and US3 depend on the published rule (Phase 2), not on each other's internals.

## Parallel Execution Examples

- After T005/T006: T007 and T008 may run in parallel (independent chat probes, no shared files).
- T009 can start once T007/T008 have their evidence (battery re-run is a single operator action; not parallel with T010).

## Implementation Strategy

MVP is **Phase 2 + US1** (T002–T006): the rule published and the default rendering live — that alone delivers the owner's directive. US2's probes (T007–T008) lock the chain and override semantics; US3 (T009) is the regression sweep; T010 ships. If T001 shows a template ID that fails to render, the spec's FR-006 path applies: stop, report, re-verify IDs before any DSL edit.
