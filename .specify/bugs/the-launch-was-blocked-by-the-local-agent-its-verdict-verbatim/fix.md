# Bug Fix: "MS Word" and the Microsoft family merge to ONE application

- **Slug**: the-launch-was-blocked-by-the-local-agent-its-verdict-verbatim
- **Fixed**: 2026-11-12T06:51:56Z
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`_COMPOUND_APPS` now merges the entire Microsoft family ("MS Word" → `word`, "Microsoft Excel" → `excel`, and 12 more), so the most natural phrasing for launching Office apps no longer parses as two applications; two REAL apps still honestly MULTI-block.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_launch_gate.py` | `_COMPOUND_APPS` +13 entries | ms/microsoft × word/excel/powerpoint/outlook/access/edge/teams + ms paint → mspaint |
| `tests/unit/test_hermes_launch_gate.py` | +10 pins | the verbatim bug prompt ("open MS Word, type Hello" → ok, target word, followup intact); 8 family phrasings parametrized; negative pin (chrome and firefox still MULTI) |

## Local Verification

- Gate sanity: "open MS Word, type Hello" → ok/`word`/followup "type Hello"; "open Microsoft Excel"→excel; "open MS PowerPoint"→powerpoint; "open ms edge"→edge; "open chrome and firefox" → blocked (MULTI) ✓
- `pytest tests/unit/test_hermes_launch_gate.py` → **57 passed**; full suite **593 passed**; ruff clean.
- Sidecar rebuilt (43 tools). **Live probe**: "open MS Word, type Hello" through the real tool — the gate ACCEPTED it (the old bug returned the MULTI block in <1 s) and the Hermes agent executed the launch+typing turn end-to-end (gateway: response ready, **121.7 s**).

## Deviations from Assessment

None. One observability note (not a deviation): when the MCP client disconnects mid-turn (my probe's curl dropped at 50 s), the sidecar writes no audit row for the cancelled call — the gateway still shows the completed turn. Minor follow-up, not part of this fix.

## Follow-ups

- Client-disconnect cancellation should still write an audit row (observed during verification; small observability gap).
- The saved skill `launch_app_and_type_text` can now replay with application="MS Word" without hitting the block.
- `/speckit.bug.test` optional — the unit pins + the live accepted-launch are the proof.
