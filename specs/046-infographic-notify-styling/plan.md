# Implementation Plan: Infographic notify line — pin emoji and blue text

**Branch**: `046-infographic-notify-styling` | **Date**: 2026-11-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/046-infographic-notify-styling/spec.md`

**Owner additions to this plan** (standing, 2026-11-19): a **test plan with unit tests and end-to-end test cases**, and explicit **error handling** — both are first-class sections below.

## Summary

Style the infographic notify line in chat answers as a visible call-out: a **📌 pin emoji + blue label** ("Open the step-by-step infographic"), applied at render time by the chat UI's markdown link component — the exact visual family as the existing follow-up line (blue + 💡) and the exact wiring pattern as the existing deck-link branch (`parseDeckLink` → `DeckActions` inside `components/markdown.tsx`'s `a:` override). Detection keys on the infographic page-URL family (`/infographics/`), so wording changes can't un-style the line; the assistant's canonical label wording is pinned in the chat steering (both apps).

## Technical Context

**Language/Version**: TypeScript / React 19 (Next.js 16 App Router); Dify chatflow DSL (YAML prompt text); Python 3.12 venv for deploy

**Primary Dependencies**: react-markdown (GFM + breaks) with the existing `components` override in `components/markdown.tsx`; the existing blue tokens `text-blue-600 dark:text-blue-400` (the follow-up line's tokens, `app/page.tsx:204`); the sidecar's infographic URL family `http://localhost:28080/infographics/{id}/`

**Storage**: N/A (render-time styling + prompt wording)

**Testing**: three layers —
1. **Unit** (red-first, vitest): `ai-chat-landing/lib/infographic-link.test.ts` pins the pure predicate `isInfographicLink(href)` (true for absolute/relative `/infographics/` URLs; false for deck links, source links, non-HTTP, empty) and `infographicDisplayLabel(text)` (passes the label through; strips a leading 📌 if the assistant ever emits one itself — the double-emoji guard, error mode E5). Mirrors the `lib/deck-url.ts` + `deck-url.test.ts` precedent.
2. **E2E** (new CDP script `ai-chat-landing/scripts/infographic-link-check.mjs`): a live chat ask on `:3000` that yields an infographic link → assert in the DOM: the `a[href*="/infographics/"]` carries the 📌 in its text, its computed color is blue (rgb of blue-600), `target="_blank"` + href intact; regression asserts in the same run: deck links still render the action bar, a plain source link is unstyled, the follow-up line keeps 💡+blue.
3. **Regression gates**: `pnpm test` (vitest, currently 175 tests), `pnpm typecheck`, `pnpm lint` — and the standing rule from the project AGENTS: NEVER `pnpm build` while `pnpm dev` runs.

**Target Platform**: the Chat UI (`:3000`) rendering pipeline; the published chatflow for the label wording

**Project Type**: chat-UI renderer rule + chatflow steering wording (additive)

**Performance Goals**: none — a per-link string check in an existing override

**Constraints**: no raw-HTML injection in answers (renderer-side only, no new sanitization surface); detection by URL substring, not label text (FR-004); both Dify apps get the wording (published by explicit app-id — the same-name `find_app` hazard is known)

**Scale/Scope**: one lib file + test, a 4-line branch in the markdown `a:` override, a steering wording edit ×2 surfaces, one CDP script

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Contract Preservation** — PASS: the `a:` override branch is additive (deck branch untouched; plain-link fallback untouched); no API/schema change; the assistant's markdown link remains a link.
- **II. Tests-First** — PASS (strengthened per owner): the pure helper pins are written RED before the renderer branch; the CDP script is the acceptance gate.
- **III. Minimal Dependencies** — PASS: zero new packages (react-markdown already renders the links).
- **IV. Honest Answers** — PASS: styling changes no answer content; the link still goes where it always went.
- **V. Spec-Driven Replacement** — PASS: nothing superseded; additive over the follow-up/deck renderer patterns.
- **Quality Gates** — vitest green with the new pins, typecheck + lint clean, CDP check green live.

Post-Phase-1 re-check: unchanged — a renderer branch + prompt wording; no gate moves.

## Error Handling (owner-requested section)

| # | Failure mode | Handling | Where verified |
|---|---|---|---|
| E1 | The link is not an infographic page (deck, source, external) | The predicate returns false → the existing plain-link/deck rendering path, byte-for-byte unchanged | unit false-cases + CDP regression asserts |
| E2 | The link renders during streaming (before the answer completes) | The same `a:` override serves streamed markdown — styling applies live; no split/detection depends on answer completion (unlike the follow-up's paragraph logic) | CDP: assert the styled line appears mid-stream and persists |
| E3 | Relative vs absolute href forms | Substring detection (`/infographics/`) matches both; malformed/empty href falls through to plain rendering | unit cases (absolute, relative, empty, non-HTTP) |
| E4 | PDF export of the conversation | The export pipeline renders the answer's markdown text: the link text survives, blue is screen-only, the renderer-added emoji does not enter the exported text — the line reads correctly, matching the spec's assumption | manual export spot-check in the E2E run |
| E5 | The assistant emits its own 📌 in the label someday (double emoji) | `infographicDisplayLabel` strips one leading 📌 + whitespace before the renderer adds its own | unit pin for the sanitizer |
| E6 | Old conversations with the previous label wording ("open the infographic") | URL-based detection styles them regardless of wording | unit predicate + spec US3 scenario |
| E7 | Chat UI fallback/demo mode (Dify down → canned replies) | Canned replies contain no infographic links → the branch never fires; no crash path | existing fallback covered by the suite's router tests |
| E8 | The steering wording edit misses an app | Detection does not depend on wording — an un-edited app still styles correctly; the wording edit is cosmetic consistency | served-DSL check + CDP against a link from either app |

## Project Structure

### Documentation (this feature)

```text
specs/046-infographic-notify-styling/
├── plan.md            # This file (incl. test plan + error handling)
├── research.md        # Phase 0 decisions
├── data-model.md      # Phase 1 entities
├── quickstart.md      # Phase 1 validation guide (the runnable test plan)
└── spec.md
```

### Source Code (repository root)

```text
ai-chat-landing/lib/infographic-link.ts        # NEW — pure predicate + label sanitizer
ai-chat-landing/lib/infographic-link.test.ts   # NEW — red-first unit pins
ai-chat-landing/components/markdown.tsx       # EDIT — a:/ override gains the infographic branch
ai-chat-landing/scripts/infographic-link-check.mjs  # NEW — CDP E2E acceptance script
dify/AGIAssistant/AGI_Assistant.yml           # EDIT — canonical label wording ("Open the step-by-step infographic")
```

## Files to Change & Shape

1. `ai-chat-landing/lib/infographic-link.ts` (NEW, written first with its test — red): `isInfographicLink(href: string | undefined): boolean` — true iff the href contains `/infographics/`; `infographicDisplayLabel(text: string): string` — strips one leading 📌 + surrounding whitespace.
2. `ai-chat-landing/lib/infographic-link.test.ts` (NEW): predicate true/false matrix (absolute `http://localhost:28080/infographics/x/`, relative `/infographics/x/`, query variants; false: deck `/exports/…pptx`, `/decks/…`, `https://support.apple.com/…`, empty, undefined) + sanitizer cases (plain label unchanged; leading-📌 stripped once; 📌 mid-text untouched).
3. `ai-chat-landing/components/markdown.tsx` — inside the existing `a:` override, after the deck branch: if `isInfographicLink(href)` render `<a href target="_blank" rel="noopener noreferrer" className="font-medium underline underline-offset-4 text-blue-600 dark:text-blue-400">{"📌 "}{children}</a>` — same target/rel guarantees, same tokens as the follow-up line.
4. `dify/AGIAssistant/AGI_Assistant.yml` — the VISUALS guidance in both strategy prompts: the link-label example becomes `[Open the step-by-step infographic](URL)` (no emoji in the emitted text — the renderer owns the 📌). Publish by explicit app-id (both apps); app2 gets the same wording patch if its older prompts carry the old label text.
5. `ai-chat-landing/scripts/infographic-link-check.mjs` (NEW): CDP on `:9240` against `:3000` — send a stepwise ask that yields an infographic ("Explain how to set up a Wi-Fi router, step by step, and also create an infographic summary of the steps"), wait for completion, then assert the styled line + the E1 regressions (deck bar, plain link, follow-up line) per the quickstart.

## Phases

- **Phase 0 — Research**: pin the five decisions (hook point, blue tokens, URL detection, emoji ownership, wording scope) → `research.md`.
- **Phase 1 — Design**: entities (`data-model.md`), runnable test guide (`quickstart.md`). No `contracts/` artifact — no external interface changes (renderer-internal; recorded decision, same as specs 044/045).

## Testing Strategy (the test plan, consolidated)

| Layer | What | Command | Gate |
|---|---|---|---|
| Unit (red-first) | predicate matrix + label sanitizer | `pnpm test` (vitest) | new pins green after the helper; red before it |
| Type/lint | wiring compiles clean | `pnpm typecheck && pnpm lint` | clean (lint pre-existing warning only) |
| E2E — SC-001/002 | live ask → styled line: 📌 present, computed color blue, link opens | `node scripts/infographic-link-check.mjs` (needs `pnpm dev` + CDP `:9240`) | all asserts green |
| E2E — SC-003 | neighbors unchanged: deck action bar, plain links, follow-up 💡+blue | same script's regression asserts | green |
| Suite regression | full vitest suite | `pnpm test` | 175+ green, 0 new failures |
