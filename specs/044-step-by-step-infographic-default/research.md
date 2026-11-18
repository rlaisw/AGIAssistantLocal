# Research — 044-step-by-step-infographic-default

## R1. Where does the default-template rule live?

- **Decision**: the chatflow's agent system prompt, in two places in `dify/AGIAssistant/AGI_Assistant.yml` — the `antv_infographic` tool-description bullet (~line 345) and the ANSWER FORMAT — VISUALS section (~line 349). The sidecar, the tool schema, and the rendering page are unchanged.
- **Rationale**: the agent *is* the template selector — it writes the declarative syntax and names the template at generation time. Steering text is the only lever that changes selection without new code; the tool already accepts any registry template ID. Both surfaces are needed because the infographic can be generated on-demand (tool call after a request) or proactively (the VISUALS "summary card" path) — one rule must cover both paths.
- **Alternatives considered**:
  - Hard enforcement in the sidecar (classify content shape, rewrite/refuse non-compliant template IDs) — rejected: requires a stepwise-content classifier in code, fragile, and the owner accepted steering-level defaulting in the clarify session ("based on the above conversation", 2026-11-18).
  - Defaulting in the engine (patch the CDN bundle) — rejected: pinned CDN artifact, no fork maintenance.

## R2. Are the three template IDs real?

- **Decision**: yes — all three verified in the pinned engine bundle.
- **Evidence**: `curl -sL https://cdn.jsdelivr.net/npm/@antv/infographic@0.2.20/dist/infographic.min.js` → `grep -c` returns 1 for each of `sequence-roadmap-vertical-pill-badge`, `sequence-timeline-done-list`, `list-row-horizontal-icon-arrow` (probe run 2026-11-18, bundle 860 KB).
- **Constraint carried into FR-006**: the IDs belong to v0.2.20's registry; any engine/CDN version bump re-verifies them before the policy keeps applying (a bundle grep is the cheap re-check; a live render of each is the acceptance-grade check done in implementation).

## R3. How is "the right template was used" verified end-to-end?

- **Decision**: the served infographic page embeds the syntax JSON in the HTML (`const syntax = {syntax_json}` in `src/agentic_rag_mcp/antv/infographic.py` `_PAGE_TEMPLATE`), so `curl <page-url> | grep <template-id>` proves which template the agent selected — no browser needed for the template assertion; the browser check (page renders content, no fallback div) stays in the CDP/visual acceptance path.
- **Rationale**: makes the verification probe cheap, deterministic, and scriptable in the deploy battery style.
- **Alternatives considered**: asking the agent to state the template in its answer (soft, unfalsifiable); MCP-level call interception (heavier than a page grep for the same evidence).

## R4. How does the prompt edit reach production safely?

- **Decision**: edit the repo YAML → `python -m agentic_rag_mcp.deploy chatflow` (project venv) → confirm the served DSL in Postgres (`select graph from workflows where app_id=… order by created_at desc`) carries the new text.
- **Rationale**: the published chatflow is rebuilt from the repo YAML — console-side hand edits revert (known gotcha, and model pins are re-applied by the deploy's model pass). This is the established spec-011 path.
- **YAML safety**: the prompt text sits in double-quoted scalars with `\n` continuations — no bare `: ` in plain scalars; apostrophes doubled in single-quoted runs.

## R5. What "stepwise content" trigger phrasing is used in the rule?

- **Decision**: the steering text keys on content shape ("a sequence of steps / how-to / process / procedure / tutorial"), explicitly noting it applies regardless of whether the word "step" appears — matching FR-001's shape-based trigger, and explicitly stating the user-override exception per the clarify answer (Option A).
- **Rationale**: keyword-only triggers miss "show me the process"; shape wording plus the explicit-override sentence keeps the rule both broad and safe.
- **Alternatives considered**: keyword list ("step", "how to") — rejected as too narrow (spec edge case: "show me the process").
