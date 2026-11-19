# Bug Assessment: "Fewer images" after the infographic emoji+blue styling

- **Slug**: restore-to-get-image-as-many-as-possible
- **Created**: 2026-11-19
- **Source**: pasted text ("after modify infographic emoji+blue-color, fewer image than before. restore to get image as many as possible")
- **Verdict**: likely valid, needs reproduction
- **Severity**: low

## Report (verbatim or summarized)

After the spec-046 change (infographic link renders as 📌 + blue), the owner reports seeing **fewer images than before** and asks to restore them "as many as possible".

## Symptom

The owner perceives fewer images/visuals in chat answers (or in the infographics) after the styling change. Expected: the same or more images as before.

## Reproduction

1. Ask a question in the chat that previously produced images (inline web images and/or an infographic).
2. Compare the rendered answer with the pre-change appearance.
3. [NEEDS CLARIFICATION: which conversation/answer is this? The Dify messages table lets me find the exact turn once identified.]

## Suspected Code Paths

- `ai-chat-landing/components/markdown.tsx:51` — the `a:` override gained the infographic branch (spec 046): the full diff since `2654179` is **18 added lines, zero removed** — the `img:` branch (lines 111-119) is untouched, deck-link and plain-link paths untouched. **No image-rendering code was changed by spec 046** (verified by `git diff 2654179..HEAD --stat`).
- `ai-chat-landing/lib/infographic-link.ts` — a pure URL predicate + label sanitizer; it cannot affect images.
- `dify/AGIAssistant/AGI_Assistant.yml` — only the label wording changed ("Open the step-by-step infographic"); no image guidance was edited by this feature.
- **Spec 044's stepwise default template** (`sequence-roadmap-vertical-pill-badge`) — a **text-only pill layout**. Older infographics used icon-rich templates (e.g. the third fallback `list-row-horizontal-icon-arrow`). If the owner's "fewer images" refers to the **infographic content** (icons/illustrations), this is the only change in the stack that reduces visual elements per infographic — it predates spec 046.

## Root Cause Hypothesis

**Two competing readings, evidence favors one over the other:**

1. **Image-rendering regression (unlikely)**: the renderer was changed by 18 added lines and no removals; the image branch is byte-identical. DB-wide image counts are **UP**, not down — 2026-11-19: **36 of 168 answers carry inline images**, versus 15/40 on 11-18 and 1/67 on 11-17. A renderer-level drop in images does not match this evidence.
2. **Infographic content got text-only (most plausible if the owner means the infographics)**: the spec-044 default template is a text-only pill roadmap; previous infographics may have carried icons/images. Restoring visual richness would mean choosing an icon-rich stepwise template (e.g. `list-row-horizontal-icon-arrow`, the third fallback in the chain the owner approved) rather than the pill default — a template-choice change, not a rendering bug.
3. **Per-conversation variance (possible)**: if the owner compares one specific old answer to a new one, model-side phrasing variance can produce fewer inline images in that pair without any systemic drop.

## Proposed Remediation

**Preferred**: identify the specific answer first (the Dify messages table makes any conversation auditable). Then:
- If the complaint is the **infographic content** (icons/images): change the stepwise default from the text-only pill to the icon-rich `list-row-horizontal-icon-arrow` template (or allow it when a stepwise ask "should be visual"), publish both apps, and verify the infographics carry images again — while keeping the 📌 + blue line from spec 046.
- If the complaint is a specific answer's missing inline images: show the evidence (that turn) and judge — likely no code change (variance), or an image-loading issue if the images are present in the markdown but broken in render (a different bug with the same symptom).

**Alternatives**:
- Do nothing until the conversation is identified (smallest diff; the DB evidence currently contradicts a systemic drop).

**Files likely to change**:
- (only if the template-choice reading is confirmed) `dify/AGIAssistant/AGI_Assistant.yml` — stepwise default wording, both apps; `scripts/infographic-link-check.mjs` would not need changes (the line styling is independent of template choice)

**Tests to add or update**:
- (template reading) a live probe: a stepwise ask produces an infographic whose page contains image/icon elements (CDP DOM check on the rendered infographic page, not just the link line)
- No unit pins needed for the renderer (no code changed there)

## Risks & Considerations

- Changing the stepwise default template reverses a choice the owner explicitly approved in spec 044 — the fix gate should confirm they now prefer image-rich visuals over the pill layout (their "restore" request suggests exactly that).
- The 📌 + blue notify line (spec 046) is independent of template choice and must stay.

## Open Questions

- [NEEDS CLARIFICATION: does "fewer images" mean fewer inline images in the ANSWER TEXT, or fewer icons/images inside the INFOGRAPHIC CONTENT?]
- [NEEDS CLARIFICATION: which conversation is this? The DB lets me find the exact turn and compare.]
