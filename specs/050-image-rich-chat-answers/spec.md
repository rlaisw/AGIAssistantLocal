# Feature Specification: Image-Rich Chat Answers

**Feature Branch**: `050-image-rich-chat-answers`

**Created**: 2026-11-25

**Status**: Draft

**Input**: User description: "add image-rich feature based on the chat conversation" — port the concept (not the number) of the image-rich answer work described in the owner's TRANSFER.md reference: visual answers must inline multiple relevant source images, never fabricate, cap the count, and stay honest on text-only topics.

## Clarifications

### Session 2026-11-25

- Q: Which spec number should this feature use? → A: `050`. The reference handoff is `specs/049-…` from another project; that number is not reused here.
- Q: What is the maximum number of inlined images per answer? → A: 10 (owner-supplied reference). Relevance stops earlier when extra images stop illustrating the answer.
- Q: Does this replace the existing non-binding image-format guidance on the live apps? → A: Yes — the current "try to include images" wording is replaced by the binding rules below in both apps.
- Q: Which conversation lanes carry the binding image policy? → A: The general lanes only — both the cloud-backed general lane and the local-model general lane; the file/desktop-automation lane and the deck-generation lane are unchanged.
- Q: Do generated-visual images count toward the 10-image cap? → A: Yes — one visible-image budget: source-page images and generated chart images share the 10 cap; approved captured desktop screenshots stay exempt.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Visual how-to answers are illustrated step by step (Priority: P1)

A user asks how to do something visual (pairing a device, setting up an app, a troubleshooting procedure). After any clarifying questions, the assistant answers with several images from the source pages it actually used, each placed under the step or paragraph it illustrates, in source order, with alt text.

**Why this priority**: This is the core gap — today the same prompt produced 0–1 visible images because the model could plan images in hidden reasoning and still finish with one, or because search snippets carry no images at all.

**Independent Test**: Ask a how-to question in a fresh conversation, answer any clarifying question, and count only the images visible in the rendered answer. Pass = at least 3 visible images, each with non-empty alt text, each next to the step it shows.

**Acceptance Scenarios**:

1. **Given** a visual how-to question with a reachable guide page, **When** the assistant answers, **Then** at least 3 relevant images are visible in the answer and each sits with the step it illustrates.
2. **Given** the source pages expose more than 10 relevant images, **When** the assistant answers, **Then** at most 10 images are visible and the answer stops at the cap rather than becoming a gallery.
3. **Given** an image the assistant wants to inline, **When** it composes the answer, **Then** the image URL came from a tool result in this conversation and the alt text describes the image (from the source, or from the surrounding text when the source had none).
4. **Given** an ask-first rule applies, **When** the first turn is only clarifying questions, **Then** zero images on that turn is expected, and the illustrated answer arrives on the follow-up turn.

---

### User Story 2 - Overview and comparison answers show a spread of examples (Priority: P2)

A user asks for examples, an overview, or a comparison of visible products/things. The assistant inlines a spread of relevant images across the answer instead of one token image, or a cluster of images dumped at the end.

**Why this priority**: Visual breadth is the point of overview answers; clustering and single images make the answer less useful than the text alone.

**Independent Test**: Ask for examples of a visually diverse category. Pass = at least 2 visible images, distributed with the text they illustrate, not all at the end.

**Acceptance Scenarios**:

1. **Given** an overview or example request, **When** the sources contain 2+ relevant images, **Then** at least 2 are visible and they are grouped with the concepts they illustrate.
2. **Given** a comparison of two or more items, **When** the assistant answers, **Then** each compared item shows its own image where the source provides one.

---

### User Story 3 - Honest behavior on text-only and image-less topics (Priority: P3)

A user asks a question that has no visual dimension, or a visual question whose sources carry no usable images. The answer stays text-only and says plainly when no source images were available; nothing is fabricated and each image's description is meaningful.

**Why this priority**: The constitution's honesty rule is non-negotiable, and unbounded "more images" invites invented URLs and decorative galleries.

**Independent Test**: Ask a text-only factual question in a fresh conversation. Pass = 0 images. Then ask a visual question whose sources carry no images. Pass = no fabricated images and an explicit statement that the sources had none.

**Acceptance Scenarios**:

1. **Given** a text-only question, **When** the assistant answers, **Then** the answer contains zero images.
2. **Given** a visual question whose sources carry no usable images, **When** the assistant answers, **Then** it says so plainly, keeps the answer text-only, and invents no image URL or description.
3. **Given** the user repeats an earlier visual question and the answer reuses earlier research, **When** the assistant answers, **Then** the images those sources provided are still inlined rather than dropped.
4. **Given** a generated visual whose output is an image, **When** the assistant answers, **Then** it is inlined as an image; **Given** a generated visual whose output is a page, **Then** it is given as a labeled link and never forced into image syntax.

### Edge Cases

- Source images have no alt text: the assistant supplies a description derived from surrounding text; it never claims the source provided one.
- Source image URLs are dead or blocked: alt text still describes what the image was meant to show; the answer does not pretend the image displayed.
- The same image appears on several source pages: it appears once in the answer.
- Logos, avatars, tracking pixels, spacers and decorative banners: excluded from the candidate set.
- The assistant's hidden reasoning mentions image URLs: those never count toward the visible-image self-check and never consume the cap.
- Captured desktop screenshots produced by an approved automation flow: exempt from the cap and never eligible for removal.
- An answer streams in and is later exported to PDF: the visible images survive both rendering and export.
- A generated chart appears in an answer that already has 9 source images: the chart is the 10th inlined image, and further source images are dropped.
- The source page had 2 relevant images only: 2 is correct; the answer does not pad to reach a higher number.
- Both assistant applications serve the same conversation behavior: an answer must not differ in image policy between them.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Client-facing web-research results (`web_research`) MUST expose, per source page, a deduplicated ordered list of image references carrying the image URL, the alt text captured from the source (empty string when the source has none), and the section heading the image belongs to. Internal agent evidence paths (e.g. the reflexion `_web_evidence` scrape) are out of scope for this field.
- **FR-002**: Every research result MUST carry the image list — an empty list when the page yielded no usable images — and MUST NOT omit the field or return a null.
- **FR-003**: The image reference list MUST be a projection of the ordered page content the research tool already produces, so image position and page text cannot diverge.
- **FR-004**: The single-page fetch capability MUST keep exposing its existing absolute-URL image list with its current shape; adding alt text there is out of scope.
- **FR-005**: The answer policy MUST require that a visual question (how-to, troubleshooting, overview, example, appearance) be illustrated with source images, and MUST forbid answering a visual question from snippet-only search results that carry no images.
- **FR-006**: Inlined images MUST appear grouped with the text they illustrate, in source order; a trailing image dump MUST NOT be the primary presentation.
- **FR-007**: The answer MUST include as many relevant images as the sources support, and MUST inline at least 3 when the sources provided more than that and the topic is visual.
- **FR-008**: An answer MUST NOT inline more than 10 images in total — source-page images and generated visual images share that budget — and MUST stop earlier when further images no longer illustrate the answer; approved captured desktop screenshots are exempt.
- **FR-009**: Every inlined image URL MUST come from a tool result in the conversation; the assistant MUST NOT invent, guess, or template an image URL.
- **FR-010**: Every inlined image MUST have non-empty descriptive alt text, taken from the source when present, otherwise derived from the surrounding content, and the source's original alt MUST NOT be overwritten or fabricated server-side.
- **FR-011**: Image planning inside hidden reasoning MUST NOT count as illustrating the answer; only images visible in the final answer count toward the self-check and the cap.
- **FR-012**: Before finishing, the assistant MUST run a self-check on the visible images only: if the topic is visual and the visible count is 0, or is fewer than 3 when the sources had more, it MUST fetch further images and inline them, or state honestly that images could not be obtained.
- **FR-013**: Text-only topics MUST stay text-only; when a visual topic's sources carry no images, the answer MUST say so plainly and MUST NOT fabricate visuals.
- **FR-014**: When an answer reuses earlier research from the same conversation, its source images MUST be preserved and inlined again.
- **FR-015**: Generated visuals MUST be presented by output type: image-output visuals inlined as images, page-output visuals as labeled links, never forced into the wrong form.
- **FR-016**: Both general conversation lanes — the cloud-backed general lane and the local-model general lane — MUST carry the same binding answer policy, so neither can silently keep the old image behavior; the file/desktop-automation lane and the deck-generation lane MUST NOT receive it.
- **FR-017**: Where the answer passes through a deterministic finalization step, that step MUST enforce the 10-image cap over visible answer text only, counting neither hidden reasoning nor approved captured screenshots, and counting generated visual images inside the same 10.
- **FR-018**: Knowledge-base document answers and chat attachments MUST remain unchanged, with no image behavior added to them.
- **FR-019**: The existing chat rendering, image display, and PDF export paths MUST be sufficient; the feature MUST NOT require a new user-interface surface or a new runtime dependency.
- **FR-020**: All additions to research results MUST be additive; every existing field name, type, and meaning in the tool responses MUST remain unchanged.

### Key Entities

- **Source image reference**: One image from one source page — URL, source-captured alt text (possibly empty), section heading, and its position within the ordered page content.
- **Visible answer**: The user-visible answer text, distinct from hidden reasoning; only this text's images count toward the cap and the self-check.
- **Generated visual**: A produced visual artifact whose output form is either an image or a page, determining how it is presented in the answer.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the standard how-to verification prompt, at least 3 images are visible on each of 3 consecutive runs per app, 100% carry non-empty alt text, and none shows an empty source.
- **SC-002**: On the overview verification prompt, at least 2 images are visible and at least one appears before the final 30% of the answer text (not a trailing cluster).
- **SC-003**: On an explicit "as many as you can find" gallery prompt, the visible image count is between 1 and 10 inclusive — never 0, never more than 10.
- **SC-004**: On a text-only factual prompt, the visible image count is exactly 0.
- **SC-005**: Across the four verification prompts, 0 fabricated image URLs are found (every inlined URL traces to a tool result in that conversation).
- **SC-006**: 100% of inlined images in the verification runs have non-empty alt text.
- **SC-007**: Both assistant applications pass the same four-prompt verification identically after the change.
- **SC-008**: The full existing automated test suite stays green, and no existing tool-response field changes name, type, or meaning.

## Assumptions

- Source pages expose their images in the page content the research tool already extracts; when they do not, the answer goes text-only honestly.
- Alt text is frequently empty on third-party pages, so derivation from surrounding text is expected and preferable to omitting the description.
- The 10-image cap is a product decision; the deterministic enforcement is desirable only where a finalization step already exists, and the policy alone must suffice otherwise.
- The owner's two assistant applications are intentionally identical mirrors; publishing one without the other is treated as a defect.
- No server-side image captioning or vision model is added; descriptions come from source alt text and surrounding text.
- Expansion of image handling to knowledge-base documents or attachments is out of scope for this feature.
