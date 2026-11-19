# Feature Specification: Infographic notify line — pin emoji and blue text

**Feature Branch**: `046-infographic-notify-styling`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "enhance Infographic notify message appearance — add emoji and text in blue color. Example: 📌 Open the step-by-step infographic (see uploaded screenshot)" — intent confirmed in conversation (2026-11-19): the infographic link line in chat answers gets the same visual treatment the chat already gives the trailing follow-up line (blue text, leading emoji).

## Clarifications

### Session 2026-11-19

- Q: Where does the styling live and what triggers it? → A: **chat-UI rendering**, following the established follow-up-line pattern (detect the line in the rendered answer, style it). The assistant's link label wording is pinned in the chat steering so the notify line reads "Open the step-by-step infographic"; detection keys on the infographic page-URL pattern so styling is stable regardless of label phrasing.
- Q: Does this apply to other links? → A: **No** — only the infographic notify line. Deck links, source citations, images, and every other markdown link keep today's appearance.
- The emoji is **📌** and the color is the same blue the follow-up line already uses — visual consistency with the existing treatment (owner's example and screenshot).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The infographic notify line reads as a friendly, visible call-out (Priority: P1)

The owner asks a step-by-step question that ends with an infographic. In the finished answer, the line pointing to the infographic page renders as a clearly visible call-out — a **📌 pin emoji** followed by the label **"Open the step-by-step infographic"** in **blue** — instead of a plain link buried in the text.

**Why this priority**: This is the entire request — one line, visibly styled, consistent with the follow-up call-out the owner already likes.

**Independent Test**: a live chat answer containing the infographic link; a browser-level check asserts the rendered line shows the pin emoji and a blue computed color.

**Acceptance Scenarios**:

1. **Given** a finished answer that links an infographic page, **When** rendered, **Then** the notify line displays the 📌 prefix and its label text in blue, visually matching the follow-up line's treatment.
2. **Given** the same answer, **When** the owner clicks the styled line, **Then** the infographic page opens exactly as before.

---

### User Story 2 - Everything else keeps today's appearance (Priority: P2)

Deck links ("open the deck"), source citations, inline images, and all other markdown links in the answer render exactly as they do today — the new styling is surgical to the infographic line, and the existing follow-up line treatment (blue, 💡) continues to work unchanged.

**Why this priority**: A styling change that leaks to other links would visually regress the whole answer surface.

**Independent Test**: an answer containing a deck link, a source link, and a follow-up paragraph; assert deck/source links unchanged and the follow-up styling intact.

**Acceptance Scenarios**:

1. **Given** an answer with a deck link and a source link alongside the infographic line, **When** rendered, **Then** only the infographic line is styled — deck and source links keep their current look.
2. **Given** an answer that ends with a follow-up question, **When** rendered, **Then** the follow-up line keeps its blue-with-💡 treatment, unaffected by the new rule.

---

### User Story 3 - Graceful degradation (Priority: P3)

If a line does not match the infographic pattern (no matching link target), it renders exactly as before — no missing text, no broken markdown, no crash. Historical conversations with older label wordings ("open the infographic") still get the styling when their link targets an infographic page, because detection keys on the target, not just the words.

**Why this priority**: The renderer must never make an answer worse because the pattern did not match.

**Independent Test**: unit cases for matching and non-matching lines; a live answer with a plain (non-infographic) link renders unchanged.

**Acceptance Scenarios**:

1. **Given** an answer with links that are not infographic pages, **When** rendered, **Then** those lines are byte-for-byte visually identical to today.
2. **Given** an older conversation whose infographic link used the previous label wording, **When** re-opened, **Then** the line still receives the 📌 + blue styling (target-based detection).

---

### Edge Cases

- The infographic link appears mid-paragraph rather than on its own line — styling still applies to the link element itself (emoji + blue label); surrounding text is untouched.
- Multiple infographic links in one answer (rare) — each receives the same treatment.
- The label wording varies between answers — target-based detection keeps styling stable; the steering pins the canonical wording for new answers.
- The follow-up line and the infographic line both appear in one answer — both render with their own emoji + blue treatments without interfering.
- Exported PDF answers (the header ⬇ export) — the export pipeline renders the answer text; if the export drops the styling, the line still reads correctly (emoji is part of the rendered label; blue is a screen concern) — noted as an assumption, verified in testing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The infographic notify line — the markdown link whose target is an infographic page — MUST render with a leading 📌 pin emoji and its label text in blue, visually consistent with the existing follow-up line treatment.
- **FR-002**: The styled line MUST remain a fully functional link (mouse and keyboard) to the infographic page; styling changes nothing about navigation.
- **FR-003**: The styling MUST apply only to infographic-page links; every other link and inline element in answers keeps its current rendering, including the existing follow-up line treatment.
- **FR-004**: Detection MUST key on the link target (the infographic page-URL pattern), not on label text alone, so wording changes in the assistant's guidance do not silently un-style the line; the chat steering pins the canonical label wording "Open the step-by-step infographic" for new answers.
- **FR-005**: Lines that do not match the infographic pattern MUST render exactly as they do today — graceful degradation, no visual or structural change to non-matching content.

### Key Entities

- **Infographic notify line**: the markdown link in a finished answer whose target is an infographic page (the sidecar's infographic URL family) — the single element this feature styles.
- **The styling rule**: 📌 prefix + blue label text, applied at render time in the chat UI — the same visual family as the existing follow-up line (blue + 💡), implemented as a sibling rule.
- **Canonical label wording**: "Open the step-by-step infographic" — pinned in the chat steering so new answers carry the deterministic wording the owner specified.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A live answer containing an infographic link renders the notify line with the 📌 prefix and a blue computed text color (browser-level check, 10/10 over a probe set of answers with the link at start, middle, and end positions).
- **SC-002**: Clicking the styled line opens the infographic page — the link's behavior is unchanged (5/5 spot checks).
- **SC-003**: Answers containing deck links, source links, and follow-up lines render those elements identically to before the change — 0 visual regressions (side-by-side check + unit pins).
- **SC-004**: The full chat-UI test suite stays green with new unit pins for the styling rule (matching, non-matching, degraded cases).

## Assumptions

- The blue is the same blue already used by the follow-up line (visual consistency is the goal; exact hex follows the existing style tokens).
- The emoji is 📌 (pin), per the owner's example and screenshot.
- The styling is applied by the chat UI at render time (the established pattern for the follow-up line) — no raw HTML injection in assistant answers, so no new sanitization surface.
- The assistant-side label wording change lives in the chat steering text (both Dify apps, both relevant prompt surfaces) and is a wording-only edit; the URL-based detection makes it robustness, not a dependency.
- The PDF-export path is verified but expected to be unaffected structurally (the export renders the answer's text; emoji and link survive, blue is screen-only).
