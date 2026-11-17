# Feature Specification: Chat attachment upload + analysis

**Feature Branch**: `043-chat-attachment-upload`

**Created**: 2026-11-17

**Status**: Draft

**Input**: User description: "Add upload an attachment (pdf, MS Word, MS Excel, MS Powerpoint, TXT, CSV, JSON) functionality to AGI Chat UI for AGI Assistant app to analysis the attachment, The upload attachment icon (paperclip) square with orange color (see uploaded image.)"

## Clarifications

### Session 2026-11-17

- Q: How large may an uploaded attachment be before the app refuses it? → A: 20 MB cap — the refusal names it; the acceptance tests pin it.
- Q: (accepted with the same "recommended") attachment content privacy posture? → A: same as chat text — the file's content goes to the configured LLM provider exactly like message text; processing is in-memory only with no server-side persistence; no extra sensitive-file warning prompt.
- Q: (owner addition, 2026-11-17) should XML be supported? → A: Yes — XML joins the supported formats (extraction is plain-text reading, same class as TXT/CSV/JSON).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Attach a document and get an answer grounded in it (Priority: P1)

The owner clicks the paperclip (the orange square upload affordance already visible in the composer), picks a file — PDF, Word, Excel, PowerPoint, plain text, CSV, JSON, or XML — sees it attached in the composer, types a question (or sends as-is), and receives an answer that reflects the file's **actual content**: facts, figures, names, and structure that exist only inside the attachment. The attachment is clearly shown while composing and can be removed before sending.

**Why this priority**: This is the whole feature — attach → send → a trustworthy answer about the file. Everything else (format handling, errors) exists to make this one flow safe and complete.

### User Story 2 - Honest, recoverable errors (Priority: P2)

If the file cannot be used — a format outside the supported list (e.g., .exe, .zip, .png), a file over the size cap, or a file that cannot be read/corrupted — the UI says exactly why **before or at send time**, keeps the rest of the message intact, and never silently drops the attachment or sends a question as if no file were attached. The assistant never pretends to have read a file it could not read.

**Why this priority**: Trust is the product's core contract; a silent drop would be worse than refusing.

### Edge Cases

- No file selected: the text-only send flow behaves exactly as today (zero regressions).
- Attachment removed before sending: the message sends as plain text.
- Question sent with an attachment but no text: the assistant still analyzes the file and describes what it contains.
- Very large documents (many pages/rows): the analysis is bounded — the assistant states when it could not cover everything, rather than pretending to have read all of it.
- Scanned/image-only PDFs with no extractable text: an honest "no readable text in this file" response, not a guessed summary.
- Password-protected or corrupted files: the honest unreadable-file reason; the message can still be sent without the file.
- Multiple formats in sequence: each message carries its own attachment; one attachment per message at a time.
- Very long conversations remain stable with attachments in history.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The paperclip icon in the composer is an active control whose click opens the **native OS file picker** (on Windows: the File Explorer-style "Open" dialog, type-filtered to the supported formats) — the browser-standard interaction; no separate File Explorer window is launched (browsers cannot and should not open one from a page). The picker is restricted to PDF, Word (.doc/.docx), Excel (.xls/.xlsx), PowerPoint (.ppt/.pptx), TXT, CSV, JSON, and XML.
- **FR-002**: A selected file is visibly attached in the composer (name shown) and can be removed before sending; a new selection replaces the previous one (one attachment per message).
- **FR-003**: Sending with an attachment includes the file in the request; the assistant's answer is grounded in the file's genuine extracted content (the answer contains facts present only in the file).
- **FR-004**: Unsupported formats are refused with the supported-format list named; unsupported selections never reach the assistant.
- **FR-005**: Files over **20 MB** are refused with the cap named (confirmed 2026-11-17); the cap is a documented, visible limit pinned by acceptance tests.
- **FR-006**: Unreadable or unextractable files (corrupted, protected, image-only PDFs) produce an honest reason — either the same extraction failure, or the assistant stating it could not read the content — never a fabricated summary.
- **FR-007**: Text-only messages remain byte-for-byte the same behavior as today (no attachment → identical request shape and UX).
- **FR-008**: Large attachments are bounded in analysis: when the content exceeds what the assistant can cover, the answer says so explicitly instead of implying full coverage.

### Key Entities

- **Attachment**: one file per message — name, type (one of the supported set), size, and its extracted content; visible in the composer while composing, removable before send.
- **Analysis answer**: the assistant's reply, grounded in the attachment's extracted content, with the honest-coverage statement when content is too large.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- SC-001: Attach → send → grounded answer completes in under 30 s for a typical document (a few pages / a few hundred rows), with the answer naming at least one specific fact from the file.
- SC-002: All **eight** supported format families open and analyze successfully (one real file per family in acceptance testing).
- SC-003: Unsupported formats and oversized files are refused 100% of the time with the honest reason (no silent drops, no answer implying the file was read).
- SC-004: Text-only messages show zero regressions (existing chat tests stay green; identical request shape when no file is attached).
- SC-005: The abandoned/removed-attachment case never sends file data (removal is honored).

## Assumptions

- **Picker interaction (confirmed by the owner 2026-11-17)**: one click on the paperclip → the native OS file-open dialog (the File Explorer-style dialog on Windows) → select → attached in the composer. A web page cannot open a separate File Explorer window; the native browser picker is the standard, safe equivalent and is what this feature delivers.
- One attachment per message (start simple); multiple attachments can be a later deliberate extension.
- The size cap is **20 MB** (confirmed 2026-11-17) — a visible, documented limit in the same class as typical chat uploads; the refusal names it.
- **Privacy posture (confirmed 2026-11-17)**: the attachment's content goes to the configured LLM provider exactly like chat message text; extraction/processing is in-memory only with no server-side persistence; no extra sensitive-file warning prompt is shown.
- Analysis context is one-shot per message: the file's extracted content is consumed for that message; follow-up questions in the same conversation can reference the earlier analysis because the conversation history carries it.
- Extraction and where it happens (client, UI server, or backend) is a planning decision; the contract here is only "the answer is grounded in the genuine content".
- Image-only PDFs (scans) are treated as "no readable text" honestly; OCR is out of scope for this feature.