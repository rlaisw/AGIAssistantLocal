# Implementation Plan: Infographic notification link — 📌 and blue text

**Branch**: `046-infographic-notify-styling` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/046-infographic-notify-styling/spec.md`

**Owner additions to this plan** (2026-11-20): a **test plan with unit tests and end-to-end test cases**, and explicit **error handling** — both are first-class sections below.

## Summary

Restyle **only the infographic notification link**: add a renderer-owned **📌** and blue text while preserving its existing label and `href`. The change is confined to the `a:` override in `ai-chat-landing/components/markdown.tsx` and one pure URL/label helper with unit pins. **No image-display code, Dify prompts, template selection, or label wording is changed.**

## Technical Context

**Language/Version**: TypeScript / React 19 (Next.js 16 App Router)

**Primary Dependencies**: react-markdown with the existing `components` override in `components/markdown.tsx`; the existing follow-up tokens `text-blue-600 dark:text-blue-400`; the sidecar’s `/infographics/` URL family

**Storage**: N/A — render-time styling only

**Testing**:
1. **Unit (red-first, vitest)**: `lib/infographic-link.test.ts` pins URL detection and the leading-pin sanitizer.
2. **End-to-end (CDP)**: `scripts/infographic-link-check.mjs` uses a deterministic markdown echo to produce a real infographic link, then asserts the 📌, **computed blue color**, `target="_blank"`, and intact `href`. It separately checks a plain external link and inline image/deck/follow-up behavior for regressions.
3. **Regression gates**: `pnpm test`, `pnpm typecheck`, `pnpm lint` inside `ai-chat-landing/`. Never run `pnpm build` while `pnpm dev` is running.

**Target Platform**: the Chat UI on `:3000`

**Project Type**: chat-UI renderer rule (additive, presentation-only)

**Performance Goals**: none new — one URL substring check per link

**Constraints**: no `img:` changes, no Dify changes, no label-wording changes, no string coercion of React children, no new dependencies

**Scale/Scope**: one small helper + its test, one branch in `components/markdown.tsx`, one CDP acceptance script

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Contract Preservation** — PASS: additive renderer branch only; no MCP/API/schema changes and existing deck/plain-link fallbacks remain intact.
- **II. Tests-First** — PASS: pure helper pins are written and fail before implementation; the CDP acceptance check proves the behavior live.
- **III. Minimal Dependencies** — PASS: no new packages or services; existing react-markdown override is reused.
- **IV. Honest Answers** — PASS: no answer content, destination, or label wording changes; presentation only.
- **V. Spec-Driven Replacement** — PASS: nothing superseded; this is an additive presentation rule.
- **Quality Gates** — new unit pins green, full vitest green, typecheck and lint clean, CDP check green.

Post-Phase-1 re-check: unchanged — no additional behavior or dependencies.

## Error Handling (owner-requested section)

| ID | Failure mode | Handling | Verification |
|---|---|---|---|
| E1 | Link is not an infographic page | Return the existing plain/deck rendering unchanged | Unit false-cases plus CDP plain-link assert |
| E2 | Label contains nested markdown/React nodes | Pass node children through; only plain string labels are sanitized, never coerced with `String(children)` | Unit sanitizer case + CDP nested-label check |
| E3 | Model already includes 📌 in the label | Strip one leading pin before the renderer adds its own, preventing `📌📌` | Unit sanitizer pin |
| E4 | Old label wording (“open the infographic”) | URL-based detection still applies, independent of wording | CDP old-wording probe |
| E5 | Link appears while the answer streams | The same `a:` override is used during streaming, so the pin/blue styling appears and persists | CDP streaming-to-completion assertion |
| E6 | Empty, undefined, or malformed `href` | Predicate returns false; normal link rendering is preserved | Unit false-cases |
| E7 | Multiple infographic links in one answer | Each matching link gets exactly one renderer-owned pin | CDP multi-link assertion |
| E8 | PDF export or stored answer text | Renderer-owned emoji is not inserted into stored answer text; PDF/stored content is unchanged | Confirm no 📌 in Dify message answers and no stored-text mutation |

## Project Structure

### Documentation (this feature)

```text
specs/046-infographic-notify-styling/
├── plan.md            # This file, including test plan and error handling
├── research.md        # Phase 0 decisions
├── data-model.md      # Phase 1 entities
├── quickstart.md      # Phase 1 runnable validation guide
└── spec.md
```

### Source Code (repository root)

```text
ai-chat-landing/lib/infographic-link.ts        # NEW — pure URL predicate + leading-pin sanitizer
ai-chat-landing/lib/infographic-link.test.ts   # NEW — red-first unit pins
ai-chat-landing/components/markdown.tsx       # EDIT — a:/ override gains the infographic branch
ai-chat-landing/scripts/infographic-link-check.mjs  # NEW — CDP E2E acceptance script
```

No Dify file is changed.

## Files to Change & Shape

1. `ai-chat-landing/lib/infographic-link.test.ts` — write first and run red:
   - true: absolute/relative `/infographics/` URLs, including query strings.
   - false: deck URLs, source URLs, empty, undefined, non-infographic paths.
   - sanitizer: normal label unchanged, one leading 📌 removed, mid-text 📌 preserved.
2. `ai-chat-landing/lib/infographic-link.ts` — implement the two pure exports:
   - `isInfographicLink(href)` → `href.includes("/infographics/")`.
   - `infographicDisplayLabel(text)` → removes at most one leading 📌 with surrounding whitespace.
3. `ai-chat-landing/components/markdown.tsx` — after the deck branch in the `a:` override:
   - If the URL is an infographic link, render the same `<a>` semantics plus `data-infographic-link` and `text-blue-600 dark:text-blue-400`.
   - Render `📌` before the sanitized label.
   - Pass nested React-node children through unchanged.
4. `ai-chat-landing/scripts/infographic-link-check.mjs` — CDP against `:3000`:
   - Ask for an exact markdown echo of an infographic link; this avoids model-dependent long-answer tests.
   - Assert pin, canonical/existing label text, computed blue equal to a probe element with the follow-up token pair, `target="_blank"`, and intact `href`.
   - Assert plain external links are not pinned or blue-styled and image/deck/follow-up paths still behave normally.

## Phases

- **Phase 0 — Research**: record the hook point, URL detection, blue tokens, emoji ownership, nested-label handling, and test strategy in `research.md`.
- **Phase 1 — Design**: document the small entity/helper contract in `data-model.md` and the runnable validation guide in `quickstart.md`. No `contracts/` artifact: this feature changes no external interface.

## Testing Strategy (the test plan, consolidated)

| Layer | What | Command | Gate |
|---|---|---|---|
| Unit (red-first) | URL predicate matrix + pin sanitizer | `pnpm test -- lib/infographic-link.test.ts` | red before helper, green after |
| Type/lint | Renderer compiles and lints | `pnpm typecheck && pnpm lint` | clean except pre-existing warnings |
| E2E — SC-001/002 | 📌 present, computed blue equals follow-up token, link opens | `node scripts/infographic-link-check.mjs` | all checks green |
| E2E — SC-003 | Plain links, inline images, deck action bar, follow-up unchanged | same script’s regression asserts | green |
| Full suite | No new failures | `pnpm test` | 175+ green |
