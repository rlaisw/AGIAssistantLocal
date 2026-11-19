# Bug Fix: Restore image-rich infographics after the emoji+blue styling

- **Slug**: restore-to-get-image-as-many-as-possible
- **Fixed**: 2026-11-19
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Swapped the stepwise default infographic template from the text-only `sequence-roadmap-vertical-pill-badge` (spec 044's default) to the icon-rich **`list-row-horizontal-icon-arrow`** (the former third fallback), and added the chain bullet to the second app's older prompts, which had never carried spec 044's steering. A live stepwise ask now returns the icon-rich template whose rendered SVG contains real icon graphics — the 📌 + blue notify line (spec 046) is untouched.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | stepwise default chain swapped in both steering surfaces (tool bullet + VISUALS bullet, ×2 strategy prompts): primary `list-row-horizontal-icon-arrow` (icon-rich visuals, owner-requested 2026-11-19) → fallback `sequence-timeline-done-list` → third `sequence-roadmap-vertical-pill-badge`; the explicit-user-choice override and the honest no-fit rule are unchanged |
| `dify/AGIAssistant/AGI_Assistant.yml` (app 1, `194e1edf…`) | published | via explicit app-id (`update_workflow_draft` + `publish`) |
| app 2 (`7863fbe2…`) draft + publish | modified via console API | its older prompts had **no** spec-044 steering at all — the STEPWISE DEFAULT bullet with the new chain was **appended** to both strategy prompts, so the problem-bug app also defaults to icon-rich visuals |

## Diff Highlights (optional)

```diff
- defaults to the template sequence-roadmap-vertical-pill-badge; fall back to sequence-timeline-done-list, then list-row-horizontal-icon-arrow,
+ defaults to the template list-row-horizontal-icon-arrow (icon-rich visuals, per the 2026-11-19 owner request to restore as many images as possible); fall back to sequence-timeline-done-list, then sequence-roadmap-vertical-pill-badge,
```

## Tests Added or Updated

- No new unit tests — a prompt-text template change (the spec-044 steering has no unit surface; the spec-045/046 pins are unaffected and were re-run in this pass)
- Live verification is the evidence (below).

## Local Verification

- Commands: `pytest tests/unit/test_ask_before_answering.py` → **9/9 green** (the amended rule + END-REPLY fragment unaffected); `pnpm test` (chat UI) → **185 passed** (the spec-046 link pins unaffected).
- Publish: both apps by explicit app-id; served graphs verified to carry the new chain (app 1) and the appended bullet (app 2).
- Live probes (chat API):
  - `Explain how to back up a phone, step by step, and also create an infographic summary of the steps` → ask-back (correct ask-first behavior), then context reply → page `…/infographics/62f1b212d021/` whose embedded syntax carries **`list-row-horizontal-icon-arrow`** ✓
  - CDP render check of that page: SVG present with **icon symbol defs (`data-element-type="btn-icon-defs"`), 68 groups, 11 paths** — actual icon graphics rendered, versus the pill layout's text-only rows ✓ (the first probe's `imageElements: 0` was a false negative: icons are SVG symbols/paths, not `<image>` elements)
- The spec-046 styling (📌 + blue link line) was verified unchanged in the same session's prior runs and needs no template-dependent change.

## Deviations from Assessment

- The assessment scoped "publish both apps" without noting that **app 2's prompts predated spec 044 entirely** — the fix had to *append* the chain bullet there rather than swap text. Recorded here as a small, additive expansion consistent with the assessment's intent (the icon-rich default now applies on both surfaces).
- The owner explicitly reversed the spec-044 default at the fix gate ("Infographic content (Recommended)"), which the assessment's risk section required before changing it — that confirmation is on record in this session.

## Follow-ups

- Uncommitted: the repo YAML swap + this lifecycle set — commit on your word.
- The unit-pin contract for spec 045/046 is unchanged and green; a template-ID guard for the new default could be added if you want the choice pinned against future drift (the spec-044 pin family covers steering text, not template IDs).
- The five stale test pins remain parked as the separate test-debt item.
