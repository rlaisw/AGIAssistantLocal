# Data Model — 046-infographic-notify-styling

No new storage entities: a render-time rule plus a pure helper. The persisted artifacts are the helper file, its test, the renderer branch, the CDP script, and the steering wording.

## Infographic notify line (the styled entity)

| Field | Value | Notes |
|---|---|---|
| what it is | the markdown link in an answer whose target is an infographic page (`/infographics/` URL family) | detection by URL substring — FR-004; label wording irrelevant |
| rendered form | `📌 Open the step-by-step infographic` in blue (`text-blue-600 dark:text-blue-400`), underlined, `target="_blank" rel="noopener noreferrer"` | the follow-up line's tokens; deck-link attributes; emoji owned by the renderer |
| behavior | identical link semantics — click/keyboard open the page (FR-002) | styling adds zero behavior change |
| scope | infographic-page links only; deck links keep `DeckActions`; plain/source links keep today's rendering; the follow-up line keeps 💡+blue (FR-003) | |

## Pure helper (`ai-chat-landing/lib/infographic-link.ts`)

| Export | Contract | Validation rules |
|---|---|---|
| `isInfographicLink(href: string \| undefined): boolean` | true iff `href` contains `/infographics/` | false for empty/undefined, deck URLs (`/exports/…pptx`, `/decks/…`), external sites, non-HTTP junk; true for absolute and relative infographic URLs (error modes E1/E3/E6) |
| `infographicDisplayLabel(text: string): string` | the link's display text, with at most one leading 📌 + surrounding whitespace stripped | plain labels unchanged; a model-emitted leading 📌 is stripped once (E5); 📌 mid-text is data, untouched |

## Renderer branch (`ai-chat-landing/components/markdown.tsx` `a:` override)

Order of branches: deck check (existing) → infographic check (new) → plain link (existing). The infographic branch composes the helper's two exports: predicate decides, sanitizer cleans the label, the branch prepends the renderer's own 📌.

## Steering wording (both Dify apps)

`[open the infographic](URL)` → `[Open the step-by-step infographic](URL)` in the VISUALS guidance of both strategy prompts; app 2 patched only where the old wording exists in its older prompts (E8 — detection does not depend on it).

## Unchanged entities (explicitly)

The follow-up split (`lib/follow-up.ts` + its rendering at `app/page.tsx:196-205`), the deck action bar (`parseDeckLink`, `DeckActions`), the PDF-export pipeline (E4 — blue is screen-only; the emoji never enters exported text), and every tool schema.
