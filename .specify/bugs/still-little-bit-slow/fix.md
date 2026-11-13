# Bug Fix: numeric Excel verify (.Text) + v2 skill-loop exemption

- **Slug**: still-little-bit-slow
- **Fixed**: 2026-11-13T02:59:58Z
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The Excel template now verifies the **displayed literal** (`.Text`) instead of `str(.Value)` — fixing every numeric cell write that Excel's float coercion falsely failed ("12345" → `12345.0` ≠ "12345"). And the v2 deterministic engine ops are **exempt from the skill loop** (no `skill_search` before, no `skill_save` after), removing 3–5 LLM protocol rounds from turns whose tool work is sub-2-second.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `office_lanes/proxy.py` `_XLS_WRITE_TEMPLATE` | verify via `.Text` | the displayed literal is what "type X" means; live probe: `.Value`=12345.0 (float), `.Text`="12345" |
| `dify/AGIAssistant/AGI_Assistant.yml` | **V2 FAST-PATH EXEMPTION** rule, published | office v2 tools (doc/xls/ppt_write_v2, doc_read_v2) + browser v2 tools (navigate/read/click) skip the loop entirely; every other operational task keeps the full loop |
| `tests/unit/test_office_v2.py` | +1 pin | `.Text` compare present; `.Value` compare absent |

## Local Verification

- 621 unit green, ruff clean, sidecar rebuilt (47 tools), chatflow published
- **Live numeric re-test** (the exact failing case from the bug): `xls_write_v2({"C1": "12345", "D4": "3.14"})` → **ok, created a new workbook, fronted True, 0.5 s**

## Deviations from Assessment

One scope expansion, logged: the exemption also covers the **browser v2 tools** (browser_navigate_v2/read/click) — same rationale (deterministic single-hop engine ops, the search-and-report path already skips the loop for the same reason), same line of the rule, no code change beyond the DSL sentence.

## Follow-ups

- Watch the next real PowerPoint/Excel simple write: expected ≈ classifier + one v2 call + answer (no skill rows in the audit trail) ≈ 10–15 s.
- The skill store keeps its existing records (name-stability unaffected); new engine-op "skills" simply stop being recorded.
