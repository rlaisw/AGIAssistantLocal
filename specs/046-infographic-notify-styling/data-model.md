# Data Model — 046-infographic-notify-styling

No new storage entities. The feature is a renderer rule plus a small pure helper. The persisted artifacts are the helper, its test, the renderer branch, and the CDP script.

## Infographic notification link

| Field | Contract | Validation |
|---|---|---|
| Detection | `href` contains `/infographics/` | Absolute and relative URLs match; deck, source, empty, and undefined URLs do not (E1/E6) |
| Presentation | Renderer-owned 📌 + `text-blue-600 dark:text-blue-400` | Exactly one pin; computed color equals the follow-up token pair |
| Label | Existing wording is preserved | No assistant or Dify wording change; plain string labels may have one leading pin stripped (E3) |
| Behavior | `target="_blank"`, `rel="noopener noreferrer"`, original `href` | Clicking opens the same infographic page |
| Rich children | React-node labels pass through unchanged | Never `String(children)`; no `[object Object]` (E2) |
| Scope | Only this link type | `img:`, deck action bar, plain links, follow-up line, Dify prompts/templates unchanged |

## Pure helper — `ai-chat-landing/lib/infographic-link.ts`

| Export | Contract |
|---|---|
| `isInfographicLink(href: string \| undefined): boolean` | True iff the href contains `/infographics/` |
| `infographicDisplayLabel(text: string): string` | Removes at most one leading 📌 and surrounding whitespace; leaves other content intact, including 📌 mid-text |

## Renderer branch order

1. Existing deck-link handling.
2. New infographic-link handling (this feature).
3. Existing plain-link fallback.

## Unchanged entities

- The `img:` markdown branch and all image-loading behavior.
- Deck action bar and `parseDeckLink`.
- Follow-up split and its 💡 + blue rendering.
- Stored answer text and the PDF-export path; the renderer-owned 📌 is not persisted (E8).
- Every Dify prompt, app, tool schema, and infographic template.
