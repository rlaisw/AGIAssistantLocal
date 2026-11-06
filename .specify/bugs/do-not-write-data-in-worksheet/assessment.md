# Bug Assessment: Excel task saved the data but left the app showing nothing — the user sees a blank Excel and concludes the write failed

- **Slug**: `do-not-write-data-in-worksheet`
- **Created**: 2026-11-06T05:20+00:00
- **Source**: pasted text ("do not write data in worksheet only open the new excel worksheet")
- **Verdict**: valid — the task's data half succeeded; the presentation half misled the user
- **Severity**: medium — no data loss (the file is correct), but the visible state contradicts the agent's success claim, which is precisely the trust-eroding failure mode this stack works to avoid; plus a coupled observability defect in the audit trail

## Report (verbatim or summarized)

> "do not write data in worksheet only open the new excel worksheet"

The user asked the chat: `create a excel file "c:\temp\test\excel-2026-11-06" type 98765 at cell A1`. The agent reported success ("Excel was left open showing the result"), but the user — looking at Excel — saw only a blank new worksheet with no data anywhere.

## Symptom

The Excel write task completed correctly on disk, but Excel was left running with **no workbook open at all**, so the user sees an empty Excel shell and reasonably concludes the data was never written. Expected: the app window visibly showing the saved workbook with the written data.

## Reproduction (all evidenced, 2026-11-06 UTC)

1. 05:05:42 — the chat request (`excel-2026-11-06`, 98765 at A1)
2. 05:07:32 — the batched script ran: probe → Excel via Dispatch → new workbook → A1 set → SaveAs → read-back verify — and the agent's answer claimed "Excel was left open showing the result"
3. **File on disk is CORRECT**: `C:\temp\test\excel-2026-11-06.xlsx`, active sheet Sheet1, **A1 = 98765** (verified independently with openpyxl)
4. **Direct COM probe of the live Excel** (via the direct channel): `ACTIVE_WB=None`, caption "Excel", `Visible=True` — **zero open workbooks**: Excel is an empty visible shell; nothing the user can look at contains the data
5. Secondary finding: the audit entry for the batched step is truncated mid-sentence in the audit file itself ("A1 set to literal va…") — `server.py:879/881` slices every audit outcome to 200 chars, which the STEP BATCHING texts (one block carrying all sub-operation details) now routinely exceed

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_client.py` — `OFFICE_INSTRUCTIONS`: the "leave the application open showing the result" rule says nothing about the **workbook** being open and active; the STEP BATCHING rule requires probe→operation→read-back in one script but not a final visible-state guarantee. Nothing forbids the script ending with the saved workbook closed (or an orphan blank book activated), and nothing requires the display claim to match the verified window state.
- `src/agentic_rag_mcp/server.py:879,881` — audit outcome slices (`line[:200]`) predate batching and now cut the long combined step texts mid-sentence (the Excel turn's audit loses the A1-write and verify details)

## Root Cause Hypothesis

**High confidence.** The batched script's final state was never specified: it created the workbook, wrote A1, SaveAs'd, verified the read-back from the workbook — and then ended in a state where the workbook was no longer open/active in the Excel window (closed, or the app was left at its empty start state). The agent's report then claimed "showing the result" based on the app being open, without verifying the window actually displays the data — a display-state honesty gap, not a data-integrity one. The 200-char audit slice is an independent, pre-existing cap that batching turned into a routine truncation.

## Proposed Remediation

**Preferred**: (1) Extend the STEP BATCHING rule with a mandatory final visible-state sub-step: the combined script must END with the saved/created document **open and active** in the application window (after SaveAs, keep the workbook; never end with the app showing no file), and the report's display claim must describe that verified state — if for any reason the document ends closed, the report must say so explicitly instead of claiming "showing the result". (2) Bump the audit outcome slice in `server.py` from 200 to 1000 characters so batched step texts survive whole.

**Alternatives**:
- Have the batched script re-open the saved file from disk at the end (Save → Close → Open) — guarantees the window shows exactly what is on disk; slightly more COM traffic but the most literal "showing the result"; can be folded into the instruction as the preferred final sub-step
- A UI-side hint telling the user where files land — redundant once the window state is correct

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_client.py` — visible-state requirement in the batching/display rules
- `src/agentic_rag_mcp/server.py` — audit slice 200 → 1000
- `tests/unit/test_hermes_office_tool.py` — guard for the visible-state rule

**Tests to add or update**:
- Guard test: instructions require the end state "saved document open and active" and forbid claiming "showing the result" without it
- A small unit test on the audit helper (or the STEP parse) asserting long outcomes are not truncated below 1000 chars

## Risks & Considerations

- Keeping every document open can pile up open workbooks across many tasks on a long-lived Excel session — the rule should say "the document from THIS task stays open; closing other pre-existing documents must never happen" (the unsaved-changes ask-back rule already guards user files)
- The re-open-from-disk variant doubles as a stronger verification (shows exactly the persisted bytes) at a small latency cost
- The audit slice bump increases log size modestly; batched texts are bounded by the report format anyway
- The user's current Excel (empty shell, PID 18956) can be closed or the file opened manually — nothing is wrong with the saved file

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the file is correct and the user can open it directly; the fix addresses future turns' visible state]
