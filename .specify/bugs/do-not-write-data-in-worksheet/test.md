# Bug Verification: VISIBLE-STATE REQUIREMENT — Excel and Word both end with the document open, active, and window-verified

- **Slug**: `do-not-write-data-in-worksheet`
- **Tested**: 2026-11-06T05:30+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original failure (file correct on disk, Excel left as an empty shell, user concludes nothing was written) no longer reproduces: the Excel fix-phase task ended with the saved workbook re-opened from disk and confirmed as the active workbook with its data (COM-probed), and the Word generalization task in this verification went further — its report explicitly verified "active document …, window visible True, Word remains open with the saved document active". The audit trail now holds the full batched step texts.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix), Excel — the original scenario | live task "create visible-state-verify.xlsx with 555777 in A1" (05:21:27, fix phase, stripped channel → direct channel) | **pass** | Batched script wrote, saved, **closed and re-opened the saved file from disk**, read back A1=555777; independent post-task COM probe: `ACTIVE_WB=visible-state-verify.xlsx … A1=555777` — the window shows the data |
| Reproduction (post-fix), Word — generalization | live task "create word-visible-verify.docx with 'visible state ok'" (this verification) | **pass** | Report verifies window state inline: "re-opened the saved file from disk … active document C:\temp\test\word-visible-verify.docx, window visible True. Word remains open with the saved document active" — `status ok, TASK: COMPLETED` |
| Audit completeness | inspect the turn's audit entries | **pass** | STEP texts (274 chars) stored whole — the 200-char truncation is gone |
| Original complaint's data | `excel-2026-11-06.xlsx` on disk | **pass** | A1=98765 confirmed correct (independent openpyxl read, assessment phase) |
| New / updated tests | `pytest tests/unit` | **pass** | 332 passed, incl. the visible-state guard |
| Lint | `ruff check src/agentic_rag_mcp/hermes_client.py` | **pass** | clean (server.py's 5 fixables pre-date this change) |

## Output Excerpts

```
Excel (fix phase): STEP 5: Verify OK — closed and re-opened the saved file
  from disk; A1 read back as 555777 → probe: ACTIVE_WB=visible-state-verify.xlsx
Word (this phase): "… re-opened the saved file from disk, and read it back
  through Word: read-back text 'visible state ok', content matches True,
  active document C:\temp\test\word-visible-verify.docx, window visible True.
  Word remains open with the saved document active." → TASK: COMPLETED
pytest tests/unit → 332 passed
```

## Residual Risks

- The rule is instruction-level: model adherence is high in both observed turns (both voluntarily chose the re-open-from-disk strong form), but as with the batching rule it remains probabilistic — the audit trail and the user's own eyes are the backstop
- Both live verifications ran through the direct channel (the gateway strip persists upstream, #148459) — orthogonal to this fix, but worth remembering that the direct path is now the lane's normal operating mode
- Re-opening from disk adds a small latency cost to every task — accepted in exchange for window state that provably matches the persisted bytes

## Recommendation

**Close the bug — verified end-to-end.** Both apps (Excel from the original complaint, Word as the generalization) now end tasks with the saved document open and active, the display claims are window-verified in the reports, and the audit trail is complete. The user-facing consequence of this bug class — a correct file the user believes was never written — is closed.
