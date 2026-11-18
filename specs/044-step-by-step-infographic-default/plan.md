# Implementation Plan: Default step-by-step infographic template policy

**Branch**: `044-step-by-step-infographic-default` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/044-step-by-step-infographic-default/spec.md`

## Summary

Make step-by-step infographics render in the owner's preferred default shape: any stepwise `antv_infographic` generation defaults to the `sequence-roadmap-vertical-pill-badge` template, with an ordered fallback chain (`sequence-timeline-done-list` → `list-row-horizontal-icon-arrow`) and an explicit-user-choice override. The change is **chatflow steering text only** — the tool description and the ANSWER FORMAT — VISUALS guidance in `dify/AGIAssistant/AGI_Assistant.yml` gain the rule; the sidecar's declarative pass-through, the rendering page, and the tool schema are untouched (spec FR-005).

## Technical Context

**Language/Version**: Dify chatflow DSL (YAML prompt text); Python 3.12 venv for deploy/verify

**Primary Dependencies**: `@antv/infographic@0.2.20` (CDN, pinned — template IDs verified in-bundle 2026-11-18); `agentic_rag_mcp.deploy` CLI (chatflow publish); sidecar `antv/infographic.py` (unchanged)

**Storage**: N/A (prompt text inside the chatflow DSL)

**Testing**: live chat replay (Dify `/v1/chat-messages` streaming probe) + rendered-page check (the page embeds the syntax — `curl <page-url>` and grep the template ID in the embedded JSON) + `python -m agentic_rag_mcp.deploy verify` battery re-run

**Target Platform**: the live Dify chatflow (published via `deploy chatflow`)

**Project Type**: chatflow steering directive (additive over spec 012)

**Performance Goals**: none new — prompt-token delta is ~60 tokens on the agent node

**Constraints**: never touch tool schemas (Constitution I); template IDs are the pinned v0.2.20 registry names; YAML topic plain-scalar rules apply to the prompt text (no bare colon-space; doubled apostrophes)

**Scale/Scope**: one system-prompt edit in two places in the DSL + publish + verification probes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Contract Preservation** — PASS: prompt-text only; tool schemas and response shapes unchanged; no client-facing contract touched.
- **II. Tests-First** — PASS: the plan's verification probes (default render, chain order, explicit override, battery green) are written as quickstart scenarios before implementation; the existing antv battery covers regression.
- **III. Minimal Dependencies** — PASS: zero new dependencies; engine and sidecar reused as-is.
- **IV. Honest Answers** — PASS: the no-fit case requires an honest limitation statement (FR-003); the fallback chain is honest about why a template is skipped.
- **V. Spec-Driven Replacement** — PASS: nothing superseded; additive over spec 012 (documented in the spec's Assumptions).
- **Quality Gates** — full pytest suite green before done; live-verified (not assumed) template renders.

Post-Phase-1 re-check: unchanged — the design adds no code, so no gate moves.

## Project Structure

### Documentation (this feature)

```text
specs/044-step-by-step-infographic-default/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── spec.md
```

### Source Code (repository root)

```text
dify/AGIAssistant/AGI_Assistant.yml   # EDIT — two steering surfaces (lines ~345, ~349)
~/.config/agentic-rag-mcp/config.toml # read-only (deploy credentials)
```

No other file changes. `src/agentic_rag_mcp/antv/infographic.py`, the MCP tool registry, and the chat-UI are untouched.

## Files to Change & Shape

1. `dify/AGIAssistant/AGI_Assistant.yml` — the agent node's system prompt, two surfaces:
   - **Tool description bullet** (`- antv_infographic: declarative infographics (276 templates, 8 families …)`): append the stepwise default — *"step-by-step/process content defaults to the template sequence-roadmap-vertical-pill-badge; fall back to sequence-timeline-done-list, then list-row-horizontal-icon-arrow, only on shape mismatch or render failure; an explicit user-named template always wins"*.
   - **ANSWER FORMAT — VISUALS** section: add one bullet restating the default-chain rule for stepwise summary cards (the proactive-infographic path), so both the on-demand and the proactive generation paths see it.
   - YAML safety: the prompt text lives in double-quoted scalars with `\n` continuations — no bare `: ` inside plain scalars, apostrophes doubled where single-quoted.
2. Publish: `python -m agentic_rag_mcp.deploy chatflow` (venv python) — then confirm the served DSL in Postgres carries the new text (the known hand-edit-revert gotcha: the published DSL is rebuilt from the repo YAML, so edit here, never in the console).
3. Verification probes (no repo files): see `quickstart.md`.

## Phases

- **Phase 0 — Research**: pin the steering edit surfaces, the template-ID verification evidence, and the rendered-page verification mechanism (`research.md`).
- **Phase 1 — Design**: entities and the steering-rule shape (`data-model.md`), validation guide (`quickstart.md`). No contracts/ artifact — the feature changes no external interface; the tool schema and page URL contract are unchanged (noted here as the decision record).

## Testing Strategy

- **Live default probe**: replay a stepwise infographic request via the Dify chat API; fetch the returned page URL; assert the embedded syntax carries `sequence-roadmap-vertical-pill-badge` and the page renders content.
- **Explicit-override probe**: the same request naming `sequence-timeline-done-list` explicitly; assert the named template wins.
- **Chain probe**: a done-list-shaped stepwise ask (or a forced render failure) exercises the ordered fallback; assert order and honest no-fit refusal at the end.
- **Regression**: `python -m agentic_rag_mcp.deploy verify` — the antv-infographic and chart-in-deck scenarios stay green; non-stepwise infographic requests keep today's template freedom (spot-probe one hierarchy ask).
- The full pytest suite green before the feature is called done (no new unit tests needed — prompt text has no unit surface; the probes above are the runnable checks, and SC-001's 10/10 cadence is a battery-loop metric).
