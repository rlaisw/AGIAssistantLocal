---

description: "Task list for 046-infographic-notify-styling: 📌 + blue styling for the infographic notify line (unit pins, CDP E2E, error probes)"

## Overview

Style the infographic notify line in chat answers as a visible call-out — **📌 + "Open the step-by-step infographic" in blue** — via the chat UI's markdown link renderer (the deck-branch precedent), with URL-based detection, red-first unit pins, a CDP E2E script with computed-color assertions, and the plan's error-handling probes. Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md) (test plan + error matrix) · Run guide: [quickstart.md](quickstart.md).

### Story-to-Phase Mapping

- **Phase 3 = US1** (P1): the styled notify line renders live with a working link
- **Phase 4 = US2** (P2): deck links, plain links, and the follow-up line keep today's appearance
- **Phase 5 = US3** (P3): graceful degradation — old wordings still styled, non-matching lines untouched, PDF export unaffected

---

## Phase 1: Setup (tests first — owner-requested TDD)

- [X] T001 Write the red-first unit pins in `ai-chat-landing/lib/infographic-link.test.ts` per the data-model contracts: `isInfographicLink` matrix (true: absolute `http://localhost:28080/infographics/x/`, relative `/infographics/x/`, query-carrying variants; false: deck `/exports/…pptx`, `/decks/…`, external `https://support.apple.com/…`, empty, undefined) and `infographicDisplayLabel` (plain label unchanged; one leading 📌 + whitespace stripped; 📌 mid-text untouched). Run `pnpm test -- lib/infographic-link.test.ts` and confirm it fails RED — the helper does not exist yet (Constitution II evidence; do not create the helper in this task).

## Phase 2: Foundational

- [X] T002 Implement `ai-chat-landing/lib/infographic-link.ts`: `isInfographicLink(href: string | undefined): boolean` — true iff `href` contains `/infographics/`; `infographicDisplayLabel(text: string): string` — strips at most one leading 📌 with surrounding whitespace. Run the pins from T001 → green.
- [X] T003 Add the infographic branch to the `a:` override in `ai-chat-landing/components/markdown.tsx` (after the existing deck branch, before the plain-link fallthrough): when `isInfographicLink(href)`, render the link with `className="font-medium underline underline-offset-4 text-blue-600 dark:text-blue-400"`, the sanitizer applied to the label, and a renderer-owned `{"📌 "}` prefix — keeping `target="_blank" rel="noopener noreferrer"` and the href untouched. Verify: `pnpm typecheck && pnpm lint` clean (lint pre-existing warning only).
- [X] T004 [P] Pin the canonical label wording and publish: in `dify/AGIAssistant/AGI_Assistant.yml`, change the VISUALS link example in BOTH strategy prompts from `[open the infographic](URL)` to `[Open the step-by-step infographic](URL)` (no emoji in the emitted text — the renderer owns it; YAML double-quoted scalar rules); publish app 1 (`194e1edf…`) by explicit app-id via the console API (NOT `deploy chatflow` by-name — the same-name `find_app` hazard), patch app 2 (`7863fbe2…`) only where the old wording exists in its prompts, then verify both served graphs carry the new wording (E8: detection does not depend on this — it is consistency).

## Phase 3: User Story 1 — The styled notify line renders live

Story goal: a live answer with an infographic link shows 📌 + blue label, the link opens the page, and the styling appears during streaming and persists. Independent test: V1 in [quickstart.md](quickstart.md).

- [X] T005 [US1] Write `ai-chat-landing/scripts/infographic-link-check.mjs` (CDP on `:9240` against the `:3000` chat): send the stepwise ask "Explain how to set up a Wi-Fi router, step by step, and also create an infographic summary of the steps", wait for completion; assert the `a[href*="/infographics/"]` exists, its text starts with 📌 and reads "Open the step-by-step infographic", its **computed color is blue** (`getComputedStyle` — the blue-600 rgb), `target="_blank"` + href present; assert the styled line also appears mid-stream (E2) and persists; support `--loop N` for the SC-001 battery form (link at start/middle/end positions via three phrasings).
- [X] T006 [US1] Run V1 live: `node scripts/infographic-link-check.mjs` (with `pnpm dev` on `:3000`) — all asserts green; then SC-001's battery: `--loop 10` — 10/10 styled renders; SC-002: curl the styled href → 200 (the infographic page opens).

## Phase 4: User Story 2 — Everything else keeps today's appearance

Story goal: deck links, plain/source links, and the follow-up line render exactly as before. Independent test: V2 in [quickstart.md](quickstart.md).

- [X] T007 [US2] Extend the CDP script's second phase and run it live: an answer containing a deck link (⬇ Download / 👁 Preview-Edit action bar renders — NOT the infographic styling), a plain source link (unstyled, no emoji, no blue class), and a trailing follow-up paragraph (💡 + blue intact, unaffected by the new branch) — 0 neighbor regressions (SC-003).

## Phase 5: User Story 3 — Graceful degradation

Story goal: non-matching lines are untouched, old wordings still style, and the PDF export reads correctly. Independent test: V3 in [quickstart.md](quickstart.md) + the unit matrix.

- [X] T008 [US3] Run the V3 error probes: re-open an old conversation whose infographic link used the previous "open the infographic" wording — still 📌+blue (E6, URL-based detection); export the conversation via the header ⬇ PDF — export succeeds and the line reads as its plain label text (E4 — emoji and blue are screen-side); confirm the unit matrix's E1/E3 false-cases and the E5 sanitizer pin are green (from T002).

## Phase 6: Polish & Cross-Cutting

- [X] T009 Gates and ship: `pnpm typecheck && pnpm lint && pnpm test` — typecheck clean, lint pre-existing warning only, full vitest suite green (175+ tests, 0 new failures); then commit and push the change set together: `ai-chat-landing/lib/infographic-link.ts`, `ai-chat-landing/lib/infographic-link.test.ts`, `ai-chat-landing/components/markdown.tsx`, `ai-chat-landing/scripts/infographic-link-check.mjs`, `dify/AGIAssistant/AGI_Assistant.yml`, and the spec set.

---

## Dependencies & Execution Order

```text
T001 (red pins) → T002 (helper, pins green) → T003 (renderer branch)
T001 → T004 [P] (wording + publish both apps — different files, may run parallel with T002/T003)
T003 + T004 → T005 (CDP script) → T006 (V1 live + battery)
  → T007 (V2 neighbors) → T008 (V3 error probes) → T009 (gates + ship)
```

Story completion order: US1 → US2 → US3 (the CDP script builds once in US1 and is extended per story).

## Parallel Execution Examples

- T004 (DSL wording + publish) may run in parallel with T002–T003 (chat UI files) — no shared files.
- Within US1, the `--loop` battery instances are independent chat threads (run sequentially by one operator for clean logs).

## Implementation Strategy

MVP is **Phase 2 + US1** (T001–T006): the helper with green pins, the renderer branch, the wording published, and the styled line proven live with computed-color evidence. US2 locks the neighbors, US3 proves degradation honesty, T009 ships. The plan's error matrix maps: E1/E3/E5 → T001/T002 (unit), E2 → T005, E4/E6 → T008, E7 → the existing suite, E8 → T004's by-id publish.
