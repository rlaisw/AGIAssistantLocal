# Quickstart — 046-infographic-notify-styling

The runnable test plan. Prerequisites: `pnpm dev` running on `:3000`, CDP Chrome on `:9240`, the stack up (`./startup.sh` all green), the chatflow published with the new label wording. Implementation order: unit pins red → helper green → renderer branch → steering wording + publish → V1–V4.

## V0 — Unit pins (red → green)

```bash
cd ai-chat-landing && pnpm test -- lib/infographic-link.test.ts
```
**Expected**: all pins green after the helper exists (they were written and failed before it). Any red pin = the helper contract drifted — fix the helper, not the test.

## V1 — The styled notify line, live (SC-001 / SC-002)

1. `node scripts/infographic-link-check.mjs`
2. The script sends a live stepwise ask that yields an infographic ("Explain how to set up a Wi-Fi router, step by step, and also create an infographic summary of the steps"), waits for the answer to finish.
3. **Expected asserts (all must pass)**:
   - the answer contains an `a[href*="/infographics/"]`
   - the link's text starts with 📌 and reads "Open the step-by-step infographic"
   - the link's **computed color is blue** (the blue-600 rgb), in light theme; the dark-theme token exists in the class list
   - the link keeps `target="_blank"` and its href opens the infographic page (200 via curl)
   - during streaming, the styled line appears live and persists unchanged after completion (E2)

## V2 — Neighbors unchanged (SC-003)

Same script, second phase — an answer containing a deck link, a plain source link, and a follow-up paragraph:
- the deck link still renders the ⬇ Download / 👁 Preview-Edit action bar, not the infographic styling
- the plain source link renders exactly as before (no emoji, no blue class)
- the trailing follow-up line keeps its 💡 + blue treatment

## V3 — Error-handling probes (from the plan's matrix)

- **E1/E3/E6**: an old conversation re-opened (or an answer whose link uses the previous "open the infographic" wording) — the line is still 📌+blue (URL-based detection); malformed/empty links render plain (covered by unit false-cases).
- **E4**: export the conversation via the header ⬇ PDF — the infographic line reads as its plain label text in the PDF (emoji and blue are screen-side); export succeeds.
- **E5**: (unit-only) a model-emitted leading 📌 is stripped once by the sanitizer — pinned in the unit matrix.

## V4 — Regression gates

```bash
cd ai-chat-landing && pnpm typecheck && pnpm lint && pnpm test
```
**Expected**: typecheck clean; lint with only the pre-existing warning; full vitest suite green (175+ tests, 0 new failures).

## Deployment path (implementation, for reference)

Helper + branch are client-side (hot-reload on `pnpm dev`; they ship with the next UI deploy). The steering wording: edit `dify/AGIAssistant/AGI_Assistant.yml` (both strategy prompts), publish app 1 by explicit app-id, patch app 2 where the old wording exists — see [plan.md](plan.md) "Files to Change" §4.

## Notes

- SC-001's "10/10 over a probe set" is measured by looping V1 with the infographic link at start/middle/end positions (three phrasings each) — the CDP script takes a `--loop` flag for the battery form.
- The color assertion uses `getComputedStyle` — visual truth, not class-name string matching.
