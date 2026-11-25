# Image-Rich Chat Answers — Test Report

**Feature**: `050-image-rich-chat-answers`
**Date**: 2026-11-25
**Commits**: `9dff6c5` (implementation) → `da9650d` (how-to floor) → `9a0e473` (analyze remediations)

## Deterministic validation

- Full Python unit/contract suite: **1,473 passed, 2 failed** — both failures are pre-existing `tests/unit/test_intent_router_rules.py` cases (`test_browser_action_beats_search_rule`, `test_screenshot_step_capture_preserved`); their strings are absent from the checkpoint DSL (`6fd1616`), so they predate this feature.
- Spec-050 files alone: extraction alt pins (4), `flatten_images` (8), payload assembly (3), contract additions (4 incl. the 40-ref serialization case), prompt pins (5), finalizer JS executed via `node -e` (6) — all passed.
- DSL-adjacent regression set (`test_image_prompt_pins`, `test_image_cap_dsl`, `test_mcp_action_dsl`, `test_ask_before_answering`): **137 passed**.
- One superseded pin updated: spec 047's soft `DEFAULT: always try to include images` assertion now checks the binding wording.

## Deployment

- `deploy redeploy`: sidecar rebuilt (6 steps ok); payload `hits[].images` live in the container.
- `deploy verify`: green (health, tools surface, deck, completion page, honest errors, chat UI, stop, Hermes file/launch batteries).
- Chatflow published to **both** apps by explicit ID (`194e1edf…`, `7863fbe2…`); `workflows.graph::text` shows the CAP marker and the second-source sentence as `t` for both.

## Live acceptance (visible images unless noted)

| Case | Result |
|---|---|
| How-to (CDP, primary app) | 4–6 visible, all with alt, grouped with steps (grouping assertion added later and re-run green) |
| Overview (CDP) | 10 visible, spread check green |
| Gallery (CDP) | 10 visible (cap held) |
| Chart + images (CDP) | 10 visible total |
| Text-only (CDP) | 0 |
| How-to × 3 runs per app, reasoning stripped | primary 9 / 6 / 10; twin 5 / 6 / 9 — 6/6 ≥ 3, all alt, all ≤ 10 |
| Twin app, API | how-to 9, overview 9, text-only 0 |
| No-source-image topic | 0 images, explicit "no usable source images" statement |
| Same-conversation re-ask | 5 images before, 5 after |
| URL provenance | 15/15 inlined URLs returned HTTP 200 with `image/*` |

Caveat: API-level counts read the raw answer text, which can include hidden reasoning; the CDP runs are the visible-image source of truth.

## Artifact refreshes

- Graphify: library-level incremental runbook (watch CLI still refuses on the documented saved-semantic-node bug, not forced) → 11,713 nodes / 19,060 edges / 1,061 communities; spec-050 concepts queryable.
- cocoindex-code: 27,859 chunks / 1,100 files, 0 errors.
- codebase-memory: at HEAD, 16,295 nodes / 35,778 edges.

## Known limitations

- The two `test_intent_router_rules` failures remain (unrelated).
- The ≥3 image floor and the 10-cap are model-enforced (the finalizer only enforces the cap); repeated live runs are the evidence, not a static guarantee.
- `graphify update .` (watch CLI) may refuse again; use the runbook.
