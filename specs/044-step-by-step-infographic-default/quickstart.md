# Quickstart — 044-step-by-step-infographic-default

Validation guide: prove the default-template policy works end-to-end. Prerequisites: the stack up (`./startup.sh` all green), the project venv (`.venv/bin/python`), Dify credentials in `~/.config/agentic-rag-mcp/config.toml`.

## V1 — the default renders (FR-001 / SC-001)

1. Send a stepwise infographic ask through the chat (the owner's usual chat, or a replay probe): "make a step-by-step infographic of how to back up a phone: 5 steps".
2. Open the returned page link (or `curl` it).
3. **Expected**: the page's embedded syntax carries `sequence-roadmap-vertical-pill-badge`, and the page renders the five steps (no error/fallback div). Repeat across step counts (3, 8, 15) — the default holds regardless of count.

## V2 — an explicit template request wins (FR-002 / clarify Option A)

1. Send the same ask, naming a template: "make a step-by-step infographic of that, using sequence-timeline-done-list".
2. **Expected**: the page syntax carries `sequence-timeline-done-list` — the user's named template, not the default.

## V3 — the fallback chain is ordered and honest (FR-002/FR-003 / SC-002)

1. Probe a shape mismatch: a "steps completed so far" done-list-style ask (done-checklist content rather than a forward roadmap).
2. **Expected**: the timeline-done-list template appears (fallback order honored); forcing an unsuitable case (e.g. a stepwise ask whose steps cannot fit any of the three) yields an honest limitation statement — never a misshapen render, never invented steps.

## V4 — nothing else regressed (FR-004/FR-005 / SC-003)

1. `python -m agentic_rag_mcp.deploy verify` (venv) — the battery, including the antv-infographic and chart-in-deck scenarios.
2. Spot-probe one non-stepwise ask ("make a comparison infographic of X vs Y").
3. **Expected**: battery green as before; the comparison ask is free to use any compare-family template — the policy never touches it.

## Deployment path (implementation, for reference)

Edit `dify/AGIAssistant/AGI_Assistant.yml` (two steering surfaces — see [plan.md](plan.md) "Files to Change") → `python -m agentic_rag_mcp.deploy chatflow` → confirm the served DSL in Postgres carries the new prompt text → run V1–V4.

## Notes

- The template assertion works without a browser: the served page embeds the syntax JSON in the HTML (`const syntax = {…}`), so `curl <page-url> | grep <template-id>` is the deterministic check; browser rendering checks stay in the CDP/visual path.
- SC-001's "10/10 consecutive stepwise asks" is measured by looping V1 (the same ask phrased ten ways); a single miss triggers investigation, not silent retry.
