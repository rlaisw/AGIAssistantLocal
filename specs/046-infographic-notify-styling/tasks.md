---

description: "Task list for 046-infographic-notify-styling: 📌 and blue infographic notification link only"

## Overview

Restyle **only** the infographic notification link: renderer-owned 📌 and blue text, preserving its label and destination. The work is limited to a pure helper, its red-first unit pins, one branch in `components/markdown.tsx`, and a CDP acceptance script. **No image-display code, Dify prompt/template, or assistant label wording changes.** Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md) · Validation: [quickstart.md](quickstart.md).

### Story-to-Phase Mapping

- **Phase 3 = US1** (P1): the infographic link renders 📌 + blue and still opens correctly.
- **Phase 4 = US2** (P2): images, deck links, plain links, and the follow-up line remain unchanged.
- **Phase 5 = US3** (P3): old wording, nested labels, duplicate pins, multiple links, and stored text behave robustly.

---

## Phase 1: Setup (tests first)

- [X] T001 Write the red-first unit pins in `ai-chat-landing/lib/infographic-link.test.ts`: URL matrix (absolute/relative `/infographics/` URLs and query strings return true; deck URLs, source URLs, empty/undefined/malformed values return false) and `infographicDisplayLabel` cases (ordinary label unchanged, exactly one leading 📌 stripped, mid-text 📌 preserved). Run `pnpm test -- lib/infographic-link.test.ts` and confirm RED because the helper does not yet exist.

## Phase 2: Foundational

- [X] T002 Implement `ai-chat-landing/lib/infographic-link.ts` with the two pure exports from `data-model.md`: `isInfographicLink(href)` returns true iff the href contains `/infographics/`; `infographicDisplayLabel(text)` removes at most one leading 📌 plus surrounding whitespace. Re-run T001’s pins and confirm all green.
- [X] T003 Edit `ai-chat-landing/components/markdown.tsx`’s `a:` override: after the deck branch, if `isInfographicLink(href)`, render an `<a>` with the original `href`, `target="_blank"`, `rel="noopener noreferrer"`, `data-infographic-link`, and `font-medium underline underline-offset-4 text-blue-600 dark:text-blue-400`. Prefix one renderer-owned 📌, sanitize plain string labels with `infographicDisplayLabel`, and pass nested React-node children through unchanged (never `String(children)`). Run `pnpm typecheck && pnpm lint` and confirm no new errors.

## Phase 3: User Story 1 — The notification link is 📌 and blue

Story goal: an infographic link renders with the pin and blue text while keeping its label, destination, and new-tab behavior. Independent test: V1 in [quickstart.md](quickstart.md).

- [X] T004 [US1] Create `ai-chat-landing/scripts/infographic-link-check.mjs`: use CDP against `:3000` to request an exact markdown echo of an infographic link; assert `data-infographic-link` exists, the text begins with 📌, existing label wording is preserved, computed color equals a probe with `text-blue-600 dark:text-blue-400`, `target="_blank"`, and the original `/infographics/` href is intact. Also assert the styling appears during streaming and persists after completion (E5).
- [X] T005 [US1] Run `node scripts/infographic-link-check.mjs` with `pnpm dev` and CDP Chrome running. Confirm all V1 assertions pass live, then fetch the returned infographic `href` and confirm it serves successfully (SC-002).

## Phase 4: User Story 2 — Every other presentation path is unchanged

Story goal: inline images, deck action bars, plain external links, and the follow-up line retain their current behavior and appearance. Independent test: V2 in [quickstart.md](quickstart.md).

- [X] T006 [US2] Extend `scripts/infographic-link-check.mjs` with neighbor checks: a plain Apple support link has no 📌 and no infographic class; inline images and the deck action bar render normally; the follow-up line retains 💡 and the follow-up blue token. Run the script live and confirm zero neighbor regressions (SC-003).

## Phase 5: User Story 3 — Robustness across wording, nesting, and history

Story goal: URL-based styling works on old wording, multiple links, and nested labels, with no duplicate pins or altered stored answer text. Independent test: V3 in [quickstart.md](quickstart.md).

- [X] T007 [US3] Add and run the robustness probes in `scripts/infographic-link-check.mjs`: old “open the infographic” wording still styles (E4); nested label nodes render as content rather than `[object Object]` (E2); a model-emitted leading pin does not become `📌📌` (E3); multiple infographic links each receive exactly one renderer-owned pin (E7); empty/malformed links fall back normally (E1/E6); the Dify answer row for the probe contains no renderer-added 📌, proving stored/exported text is unchanged (E8).

## Phase 6: Polish & Cross-Cutting

- [X] T008 Run the complete gates: `pnpm test` (full vitest suite green), `pnpm typecheck`, and `pnpm lint` inside `ai-chat-landing/`. Then commit and push `ai-chat-landing/lib/infographic-link.ts`, `ai-chat-landing/lib/infographic-link.test.ts`, `ai-chat-landing/components/markdown.tsx`, `ai-chat-landing/scripts/infographic-link-check.mjs`, and the spec set together.

---

## Dependencies & Execution Order

```text
T001 (red pins) → T002 (helper green) → T003 (renderer branch)
  → T004 (CDP script) → T005 (live V1)
  → T006 (V2 neighbors) → T007 (V3 robustness) → T008 (gates + ship)
```

US1 → US2 → US3. The CDP script is created in US1 and extended, not duplicated, in US2 and US3.

## Parallel Execution Examples

- The pure helper and its unit tests (T001/T002) are independent of CDP environment setup; Chrome can be started while those are being completed.
- T006 and T007 use different answer probes, but for clear logs run them sequentially in the same operator session. No task is marked [P] because the small changes share one acceptance script.

## Implementation Strategy

MVP is **Phase 2 + US1** (T001–T005): helper with green pins, the renderer branch, and live proof of 📌 + blue with a working link. US2 prevents collateral presentation changes; US3 locks the edge cases and stored-text guarantee; T008 ships. No Dify or image-display edits are required at any step.
