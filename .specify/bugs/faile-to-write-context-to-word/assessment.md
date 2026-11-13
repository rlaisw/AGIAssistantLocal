# Bug Assessment: doc_write_v2 writes the FILE but Word shows empty — "did not write context to Word"

- **Slug**: faile-to-write-context-to-word
- **Created**: 2026-11-13T01:54:18Z
- **Source**: pasted text (the agent's trace + final answer, conversation `24b0f6f6…`)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim, summarized)

> "did not write context to Word" — after the agent reported *"Done — I wrote 'abc hello 123' in Word and verified the document text. It replaced the existing document at C:\OfficeMCP\abc_hello_123.docx."* — the user looked at Word and saw **no content**.

## Symptom

The agent's report was **accurate** (the file exists, contains the text, verified in code), but the user's screen showed a Word window with **no document open** — so from the user's perspective nothing was "written to Word". Expected: "open Microsoft Word, then type abc hello 123" = Word open WITH the text visible.

## Reproduction (evidence, conversation `24b0f6f6…`, 01:51 UTC)

| Time | Row | Fact |
|------|-----|-------|
| 01:51:20 | skill-search | ✓ found `word_launch_and_type_text` (the refreshed, now-reusable skill) |
| 01:51:22 | skill-get | ✓ workflow retrieved (points at doc_write_v2) |
| 01:51:28 | **doc-write-v2: executed, 3.2 s** | `status: ok, path: C:\OfficeMCP\abc_hello_123.docx, size: 13443, existed: True, text_ok: True` — **the write happened and was verified** |
| 01:51:30 | skill-feedback | ✓ |

The routing worked end-to-end (skill → precedence → doc_write_v2, 3.2 s tool time — the fast path taken at last). **But two defects make it look broken:**

1. **The v2 template closes the document after save** (the lock-free fix from the office-v2 build): Word stays visible but EMPTY. The user asked for text *in Word*; the deliverable on screen is nothing. The file is correct — the UX is wrong.
2. **`conversation_id` was empty on the doc-write-v2 row** — the schema defaults it to `""` so the agent omitted it (my grep by conversation initially missed the row — the same observability gap class as the launch lane's). The description says "required" but the schema doesn't enforce it.

## Suspected Code Paths

- `src/agentic_rag_mcp/office_lanes/proxy.py` `_WRITE_TEMPLATE` — `doc.Close()` after SaveAs+verify: lock-free but screen-empty.
- `src/agentic_rag_mcp/server.py` `doc_write_v2`/`doc_read_v2` — `conversation_id: str = ""` default (not enforced); other lane tools declare it required without a default.

## Root Cause Hypothesis

An expectation mismatch I created in the lock-free fix: the v2's deliverable is the FILE (write → verify → close → lock-free repeats), but the user's request shape is "open Word and type X" — they expect the *visible* Word document to hold the text. Both are fixable together: keep the document open after verification, and make repeat-writes lock-free by closing any already-open doc with the same path *before* SaveAs (instead of closing after). Confidence: **high** — the audit row proves the write+verify succeeded; the only missing thing was on-screen.

## Proposed Remediation

**Preferred** (two small fixes):
1. **Keep the document open after save+verify**: change `_WRITE_TEMPLATE` to (a) before `SaveAs2`, close any open document whose `FullName` equals the target path (lock-free repeats, the original bug), (b) after verify, **leave the new document open and visible** — Word shows the text, matching the user's ask. The read template keeps its read-only Close (unchanged).
2. **Enforce `conversation_id`**: drop the `""` default in `doc_write_v2`/`doc_read_v2` schemas (match the other lane tools — the framework then requires it structurally, and the audit carries the conversation).

**Alternatives**: keep close-after-save and rely on the answer text naming the file path — rejected: the user's complaint shows the visible document IS the expectation for this lane.

**Files likely to change**:
- `src/agentic_rag_mcp/office_lanes/proxy.py` (template)
- `src/agentic_rag_mcp/server.py` (schema defaults)
- `tests/unit/test_office_v2.py` (pins: the template keeps the doc open + pre-closes path collisions; the tools require conversation_id)

**Tests to add or update**:
- Template pin: "close any open doc with the same path BEFORE SaveAs" present; "doc.Close()" (the post-save close) absent
- Live re-test: write twice to the same name (lock-free ✓) and confirm Word visibly shows the text after the second write
- Tool pin: doc_write_v2 without conversation_id is rejected by the framework (required param)

## Risks & Considerations

- Leaving docs open re-introduces Word-window clutter across turns — acceptable: it mirrors the pre-v2 office-lane behavior ("Word still open and active") that users saw before.
- The pre-close must only close documents whose FullName matches the target path — never touch other open documents (user's own work).
- The empty-cid rows already written stay as-is (append-only audit).

## Open Questions

- None blocking.