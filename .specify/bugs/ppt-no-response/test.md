# Bug Verification: PPT generation fails — empty answers, no deck (fresh re-validation)

- **Slug**: `ppt-no-response`
- **Tested**: 2026-11-03
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

Fresh re-validation against today's stack (post specs 028–030, three routing fixes, a dozen DSL republishes, model swaps): the original symptom — the 59 ms `len(None)` node crash with empty answer bubbles — **does not reproduce**. The crash shape (null variable selectors) is absent from both the repo DSL and the **published live app**, the normalization that prevents it runs inside every `model_apply` cycle, the fix's regression tests pass, and a fresh deck generated end-to-end today with its links serving 200. This report supersedes the 2026-10-29 verification from the old workspace (preserved in git history).

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix, fresh) | Live `scenario_chat_journey` — full deck generation through the deployed chatflow | **pass** | Fresh deck `deploy_automation_20261103_052933` generated in 218 s; preview + export links serve **200**; zero node failures — no 59 ms crash anywhere |
| Crash-shape scan (repo DSL) | `yaml.safe_load` + recursive scan for `{"type":"variable","value":null}` and bare-null `allowed_tools`/`context`/`files` | **pass** | **NONE** found in the working-tree DSL |
| Crash-shape scan (published app) | `export_app` of the live app (194e1edf) + regex scan | **pass** | **0** null-selector occurrences — the live runtime shape is clean |
| Normalization guard | `strip_null_variable_params` exists + is called inside `patch_dsl` | **pass** | Every `model_apply` cycle re-normalizes, so a regression would be self-healing on the next publish |
| New / updated tests (the fix's) | `pytest tests/unit/test_deploy_model_apply.py` (+ office gate + deploy_cli contract) | **pass** | 41 passed — incl. the two shape-pinning regressions (null selectors → absent; bare nulls → absent; real selectors preserved) |
| Lint | ruff on changed files (established practice since the Oct 29 verification noted none was configured) | **pass** | clean on the gate file; ruff is now available in the venv |

## Output Excerpts

```
repo DSL null-selector hits: NONE
published app null-selector hits: 0
strip_null_variable_params exists: True / called in patch_dsl: True
41 passed in 0.64s
deck roundtrip (chat-journey): PASS | 218s |
  link=http://localhost:28080/decks/deploy_automation_20261103/deploy_automation_20261103_052933/ serves=200
```

## Residual Risks

- The **local deck path** (PPT-Master Local on qwen3-8b-nothink) remains live-untested (carried from the Oct 29 report — the cloud path is proven twice now).
- A **manual Dify console edit** outside a `model_apply` cycle could still reintroduce null variable selectors until the next publish normalizes them (carried; the in-cycle normalization is the mitigation).
- Cloud turns remain independently vulnerable to transient OpenRouter failures (403 region-gating, endpoint slowness — both observed since; documented in DEPLOY.md troubleshooting).

## Recommendation

Close the bug — **verified fresh, twice over**: the symptom is gone on today's stack, the crash shape is absent from both the artifact and the live runtime, the self-healing normalization is confirmed active in every apply cycle, the regression tests pin the shape, and a brand-new deck round-trips end-to-end. Nothing remains for this bug except the two carried follow-ups (local deck path; console-edit caveat), both environmental.
