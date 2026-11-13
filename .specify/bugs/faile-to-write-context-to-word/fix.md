# Bug Fix: doc_write_v2 keeps the document VISIBLE + cid enforced

- **Slug**: faile-to-write-context-to-word
- **Fixed**: 2026-11-13T01:56:10Z
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The write template now closes ONLY a same-path open document before SaveAs (lock-free repeats) and **leaves the new document open and visible** after verification — "open Word and type X" now means the text is on screen, not just in the file. `conversation_id` is structurally required on both v2 tools (the framework rejects calls without it).

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/office_lanes/proxy.py` | `_WRITE_TEMPLATE` | pre-close: `os.path.normcase(doc.FullName) == normcase(path)` for documents at the SAME path only (never the user's other work) → write → SaveAs → verify → **stay open**; honest `open_docs` count in the payload |
| `src/agentic_rag_mcp/server.py` | `doc_write_v2(text, conversation_id, name="", …)` / `doc_read_v2(name, conversation_id, …)` | conversation_id now required (no default) — required param moved before defaulted ones (the first attempt had `name=""` before it: SyntaxError, sidecar crash-looped once, caught and fixed) |
| `tests/unit/test_office_v2.py` | +1 pin, 1 rewritten | template keeps the doc open + same-path pre-close pins (`FullName`/`normcase`/`open_docs`); the post-save `doc.Close()` must NOT return |

## Local Verification

- **617 unit tests green**, ruff clean, sidecar rebuilt (45 tools).
- **Live double-write** (the exact scenario from the bug): write 1 → ok, 3.2 s, `open_docs: 1`; **write 2 same path** → ok, **0.6 s**, `existed: True`, `text_ok: True`, `open_docs: 1` (the pre-close worked — no Word lock); probe: Word holds **one open document containing "visible test two REPEAT"** — visible on screen ✓
- **cid enforcement**: without conversation_id → framework rejection `conversation_id: Field required [type=missing]` ✓; with it → ok and the audit row carries the cid (0.4 s) ✓

## Deviations from Assessment

One implementation stumble: making conversation_id required initially placed it after a defaulted parameter (Python SyntaxError) — the sidecar crash-looped once on rebuild; fixed by reordering before redeploying (caught by the health-wait gate + the local build check, no user impact).

## Follow-ups

- The live test left a `cid test final` document open in Word — harmless; Word window state is user-owned.
- The office lane's narrated path (`hermes_office_task`) still leaves its docs open as before — unchanged, consistent.
