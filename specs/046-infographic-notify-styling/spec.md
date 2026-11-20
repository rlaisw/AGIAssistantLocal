# Feature Specification: Infographic notification link — 📌 and blue text

**Feature Branch**: `046-infographic-notify-styling`

**Created**: 2026-11-20

**Status**: Draft

**Input**: User description: "change infographic notification link (add emoji and text in blue-color)" with the explicit constraint: **ONLY** change the infographic message note; do not change code for displaying images on the AGI Chat UI.

## Clarifications

### Session 2026-11-20

- Q: What is in scope? → A: **Only the presentation of the notification link** whose target is an infographic page: add a leading 📌 and render its existing label in blue.
- Q: What is explicitly out of scope? → A: **Every other behavior and code path**: image rendering (`img:`), deck links/action bars, source links, the follow-up line, the assistant's label wording, infographic template selection, and Dify chatflow prompts. No Dify app or prompt changes are part of this feature.
- Q: How is the line detected? → A: By the link target's `/infographics/` URL family, not by the label text, so old and new label wordings receive the same styling.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The infographic notification link renders as a blue, pinned call-out (Priority: P1)

An answer contains a link to an infographic page. In the chat, that link displays a **📌 prefix and blue text**, making the infographic entry point visually distinct. The link's label text and destination remain unchanged.

**Why this priority**: This is the entire requested behavior, limited to one link's presentation.

**Independent Test**: a live answer with an infographic link; assert the pin is present and the link's computed color equals the blue used by the follow-up line.

**Acceptance Scenarios**:

1. **Given** an answer containing an infographic-page link, **When** rendered, **Then** the link displays 📌 before its existing label and its text is blue.
2. **Given** the styled link, **When** the owner clicks it, **Then** the same infographic page opens in a new tab.

---

### User Story 2 - Images and every other presentation path stay unchanged (Priority: P2)

Inline images, deck action bars, source links, ordinary external links, and the trailing follow-up line render exactly as before. No image-display code is changed, and the assistant's label wording is not changed by this feature.

**Why this priority**: The owner explicitly limited this change to the notification link only; preventing collateral changes is the main safety constraint.

**Independent Test**: an answer containing inline images, a deck link, a source link, and a follow-up paragraph; assert all those elements render as before.

**Acceptance Scenarios**:

1. **Given** an answer with inline images and other link types, **When** rendered, **Then** those elements display exactly as they did before this feature.
2. **Given** an answer ending in a follow-up paragraph, **When** rendered, **Then** the follow-up keeps its existing 💡 and blue styling without interference.

---

### User Story 3 - Styling is stable across wording, nesting, and history (Priority: P3)

The link is styled by URL, so both older "open the infographic" and newer label wordings receive the pin and blue color. Rich or nested markdown labels render without being converted to placeholder text, and multiple infographic links in one answer each receive the same treatment. Non-infographic links remain plain.

**Why this priority**: The presentation rule must not break existing conversations or labels with nested markdown.

**Independent Test**: old-wording and nested-label cases render correctly; a plain external link remains unstyled.

**Acceptance Scenarios**:

1. **Given** an older conversation using the previous label wording, **When** re-opened, **Then** its infographic link is still 📌 and blue.
2. **Given** a link label containing nested markdown nodes, **When** rendered, **Then** the label content renders intact (never as `[object Object]`).
3. **Given** a non-infographic external link, **When** rendered, **Then** it keeps its existing appearance.

---

### Edge Cases

- The infographic link appears mid-paragraph rather than on its own line: styling applies to the link element only, leaving surrounding text untouched.
- Multiple infographic links in one answer: each gets the same pin and blue styling.
- The link renders during streaming: it receives the same styling as the completed answer.
- Nested markdown label nodes are passed through as nodes, not coerced to strings.
- No Dify prompt or template change is needed or allowed for this feature.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Any markdown link whose target contains `/infographics/` MUST render with a leading 📌 and its existing label text in blue.
- **FR-002**: The link's `href`, new-tab behavior, and navigation semantics MUST remain unchanged, and its label wording MUST NOT be changed by this feature.
- **FR-003**: Image rendering, deck links/action bars, ordinary links, and the follow-up line MUST remain unchanged; no Dify prompt, template, or app changes are allowed.
- **FR-004**: Detection MUST use the link target's `/infographics/` URL family rather than label text, so historical and varied labels are styled consistently.
- **FR-005**: Non-infographic links MUST render exactly as before, and nested label nodes MUST pass through without string coercion.

### Key Entities

- **Infographic notification link**: the markdown link in an answer whose target is an infographic page — the only element changed by this feature.
- **Presentation rule**: renderer-owned 📌 prefix plus the existing follow-up blue text color, applied only to that link.
- **Unchanged neighbors**: images, deck links, source links, follow-up line, assistant label wording, and Dify prompts/templates.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A live answer containing an infographic link shows 📌 and a computed color equal to the follow-up line's blue — verified in at least 5 render checks.
- **SC-002**: Clicking the styled link opens the same infographic page in a new tab — 5/5 link checks.
- **SC-003**: Inline images, deck action bars, ordinary links, and the follow-up line show no visual or behavioral changes — 0 regressions.
- **SC-004**: The chat-UI test suite, typecheck, and lint remain green, with no new failures caused by this change.

## Assumptions

- The emoji is **📌** and blue means the same color tokens already used by the follow-up line (`text-blue-600 dark:text-blue-400`).
- The assistant's label text is not changed; only its presentation changes.
- This is a renderer-only change: no new Dify prompt, template, or API contract is introduced.
- Rich markdown labels are passed through as nodes; no string-based label conversion is used.
