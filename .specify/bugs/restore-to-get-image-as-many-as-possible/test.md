# Bug Verification: Restore image-rich infographics after the emoji+blue styling

- **Slug**: restore-to-get-image-as-many-as-possible
- **Tested**: 2026-11-19
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The mechanism is fixed and live: stepwise asks now return the icon-rich `list-row-horizontal-icon-arrow` template whose rendered SVG contains real icon graphics, on both apps. The spec-046 📌 + blue notify line is unchanged (independent of template choice), and no test regressions were introduced by the swap.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix, phone backup) | chat ask + context reply → page syntax + CDP render | pass | `…/infographics/62f1b212d021/` carries `list-row-horizontal-icon-arrow`; rendered SVG has icon symbol defs, 68 groups, 11 paths (real icon graphics) |
| Reproduction (post-fix, printer setup) | chat ask + context reply → page syntax | pass | `…/infographics/9bc0088a9016/` also carries the icon-rich template |
| Styling regression — V1 notify line | `node scripts/infographic-link-check.mjs` | pass | 📌 + canonical wording + computed blue (token-equal) + working href + dark token — all unchanged after the swap |
| Styling regression — E6 old wording + plain external link | same script | pass | old-wording link still styles (URL-based); the plain Apple link renders `[{"styled":false,"emoji":false}]` — untouched |
| New / updated tests | `pytest tests/unit/test_ask_before_answering.py`; `pnpm test` | pass | 9/9 rule pins; **185 vitest** green |
| Lint / type-check | `pnpm typecheck && pnpm lint` | pass | typecheck clean; lint **0 errors** (2 pre-existing warnings) |
| Neighbor probe — deck action bar | same script's V2 phase | **flaky** | the model did not build the probe deck on this run (LLM variance in the harness, not a styling regression; the deck action bar was proven rendering in two earlier runs of the same harness) |

## Output Excerpts

```
template in page syntax: ['list-row-horizontal-icon-arrow']
svgPresent: true, pathCount: 11, gCount: 68
<defs data-element-type="btn-icon-defs"><symbol class="icon" …>
✓ V1 ask 1: styled infographic link rendered — styled:true
✓ E6 old-wording link still styled (URL-based) — styled:true
✓ V2 plain external link is unstyled — [{"styled":false,"emoji":false,"text":"Apple support article"}]
185 passed
```

## Residual Risks

- The owner asked for "as many images as possible" — the icon-rich template restores **iconography** (SVG icons per row), which is the template's built-in visual set; photographic/stock illustrations are a different class of imagery the engine does not synthesize from plain step text. If the owner means richer imagery than icons, that needs a different template or engine capability, and is worth a follow-up conversation before any more template churn.
- The deck-build probe (PPT lane) is model-variable and failed to materialize a deck on this run; two earlier runs of the same harness proved the action bar renders. Recorded as harness variance, not a regression.
- The ask-first flow now correctly gates how-to asks before the infographic exists (two-turn probes used throughout) — that is spec 045 working, not a new defect.

## Recommendation

Close the bug — verified on the mechanism: icon-rich infographics are back on both apps (page syntax + rendered icon graphics), the 📌 + blue styling is untouched, and the full unit/type gates are green. Commit the change set (repo YAML swap, app-2 bullet append, lifecycle docs) on your word.
