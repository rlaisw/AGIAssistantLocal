# Research — 046-infographic-notify-styling

## R1. Where does the styling hook in?

- **Decision**: the `a:` component override in `ai-chat-landing/components/markdown.tsx:51`, which already owns every answer link and special-cases deck links.
- **Rationale**: one override covers completed answers, streaming output, and old conversations without changing any data pipeline. The infographic branch is additive after the deck branch and before the plain-link fallback.
- **Alternatives considered**: assistant-emitted inline HTML (rejected: unnecessary sanitization surface and markdown cannot provide a consistent color); a follow-up-style paragraph split (rejected: the target is a link node, not a paragraph block).

## R2. How is the infographic link detected?

- **Decision**: `href.includes("/infographics/")` in a pure `isInfographicLink` helper with unit pins.
- **Rationale**: FR-004 — detection by target is stable across label wording, old conversations, and absolute/relative URLs. It cannot accidentally style deck or source links.
- **Alternatives considered**: label-text matching (rejected: wording churn breaks styling); parsing host and path precisely (rejected: over-engineered for a same-origin service).

## R3. Who owns the emoji and blue color?

- **Decision**: the renderer. It prepends one 📌 and applies the follow-up line’s exact tokens, `text-blue-600 dark:text-blue-400`.
- **Rationale**: this exactly matches the owner’s sample and the existing 💡 treatment in both themes without changing assistant output. A one-leading-pin sanitizer prevents a doubled pin if the model emits one itself.
- **Alternatives considered**: assistant-emitted emoji (rejected: the renderer is the consistent owner of presentation, as with the follow-up 💡).

## R4. How are nested labels handled?

- **Decision**: only plain string labels pass through `infographicDisplayLabel`; nested React-node children render as-is. Never use `String(children)` for labels.
- **Rationale**: prevents the previously observed `📌 [object Object]` failure when a link label contains nested markdown. It also honors the spec’s requirement to preserve label wording.
- **Alternatives considered**: coercing every child to string (rejected: corrupts rich labels); walking the React tree to sanitize arbitrary nested pins (rejected: unnecessary complexity for this narrowly scoped change).

## R5. What is the verification strategy?

- **Decision**: red-first unit pins for the helper plus a deterministic CDP echo probe for the rendered link and its neighbors.
- **Rationale**: the pure helper is easy to pin without browser tests; the echo probe produces a real markdown link without relying on variable model content. Computed color is compared to a probe element carrying the follow-up token pair, which remains correct even when Chrome serializes colors as `lab()`.
- **Alternatives considered**: a long multi-question chat battery (rejected: slow and model-variable; the property under test is deterministic renderer behavior).
