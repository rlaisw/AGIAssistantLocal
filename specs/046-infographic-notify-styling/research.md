# Research — 046-infographic-notify-styling

## R1. Where does the styling hook in?

- **Decision**: the `a:` component override in `ai-chat-landing/components/markdown.tsx:51` — the react-markdown link renderer the whole answer pipeline already uses, where deck links already branch via `parseDeckLink` → `DeckActions`. The infographic check slots in as the next branch; non-matching links fall through to the existing plain rendering.
- **Rationale**: one override already owns link presentation; adding a branch there styles the line everywhere the answer renders (streamed and finished, new and historical conversations) with zero pipeline changes.
- **Alternatives considered**: a post-processing split like `lib/follow-up.ts` (rejected: the follow-up works on paragraphs at the app level; a link is a markdown AST node — the `a:` override is the natural, cheaper hook); rehype-raw + assistant-emitted inline HTML (rejected: opens a sanitization surface and pushes presentation into the model's hands).

## R2. Which blue, which emoji?

- **Decision**: the follow-up line's exact tokens — `text-blue-600 dark:text-blue-400` (`app/page.tsx:204`) — and the **📌** pin emoji, per the owner's example and screenshot.
- **Rationale**: the owner's ask is "consistent with the follow-up call-out"; reusing the tokens guarantees visual consistency in both themes with zero design decisions left to implementation.
- **Alternatives considered**: the primary accent token (rejected — the follow-up blue is the explicit reference); a different emoji (rejected — 📌 is the owner's example; it reads as "pinned/attached visual").

## R3. How is the infographic line detected?

- **Decision**: URL substring — `href` contains `/infographics/` (the sidecar's page family `http://localhost:28080/infographics/{id}/`), implemented as the pure predicate `isInfographicLink` in `ai-chat-landing/lib/infographic-link.ts` with a test file, mirroring the `lib/deck-url.ts` precedent.
- **Rationale**: FR-004 — target-based detection survives label rewording and styles old conversations (the old "open the infographic" wording). Absolute and relative forms both match; deck/source/external URLs do not.
- **Alternatives considered**: label-text matching (rejected — wording churn un-styles the line); hostname+path parsing (rejected — over-precise for a same-origin service; substring is honest and testable).

## R4. Who owns the emoji — the assistant or the renderer?

- **Decision**: the renderer. The `a:` branch prepends `📌 ` to the children; the assistant's steering guidance pins the label **text** ("Open the step-by-step infographic") with **no** emoji in the emitted markdown.
- **Rationale**: matches the follow-up precedent (renderer adds 💡 to the split block); keeps prompt text presentation-free; a leading-📌 sanitizer in the pure helper guards the E5 double-emoji case if the model ever disobeys.
- **Alternatives considered**: assistant-emitted 📌 + color via inline HTML (rejected — sanitization surface + double-emoji risk + markdown cannot color text anyway).

## R5. Where does the label wording change go?

- **Decision**: the VISUALS guidance in both strategy prompts of `dify/AGIAssistant/AGI_Assistant.yml` — the link example becomes `[Open the step-by-step infographic](URL)` — published to app 1 by explicit app-id, and patched into app 2's older prompts only where the old label text exists.
- **Rationale**: the canonical wording is what the owner wants the line to say; detection does not depend on it (R3), so this is consistency, not a dependency. Publishing by app-id avoids the known same-name `find_app` flip.
- **Alternatives considered**: leaving the old wording everywhere (rejected — the owner's example is the new wording); wording in all five prompts (rejected — Hermes/PPT prompts don't emit infographic links).
