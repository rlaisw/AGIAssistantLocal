# Bug Assessment: still a little slow — protocol rounds + an Excel numeric bug

- **Slug**: still-little-bit-slow
- **Created**: 2026-11-13T02:58:22Z
- **Source**: pasted text (both agent traces, conversations `e2d16b81…` PowerPoint and `452e4e43…` Excel)
- **Verdict**: valid (two distinct causes)
- **Severity**: medium

## Report (verbatim, summarized)

> "still little-bit-slow" — PowerPoint and Excel turns still feel slow even though the v2 tools measure 0.6–3.4 s.

## Symptom

The **tools** are fast, but the **turns** are not: the PowerPoint turn spanned 28 s of wall time for 1.8 s of tool work, and the Excel turn **failed** on its fast path entirely (verification rejected the numeric value) — degrading the experience and risking a slow-lane fallback.

## Reproduction (measured)

**PowerPoint turn** (`e2d16b81…`, 02:50:58 → 02:51:26 = **28 s wall**):

| Step | Time | Tool cost |
|------|------|-----------|
| skill_search | 02:50:58 | 1.1 s (+ a kimi round) |
| **ppt_write_v2** | 02:51:10 | **1.8 s** ✓ |
| skill_save ×3 (2 rejections, then ok) | 02:51:18–26 | 0 s each (+ 3 kimi rounds) |

**Excel turn** (`452e4e43…`, 02:52:10 → 02:52:16): skill_search + skill_get → **xls_write_v2 ERROR**: *"verification failed — a cell did not read back the literal value"* — the write happened but the verify rejected it. **Root cause (probed live)**: the template compares `str(Cells.Value)` to the literal, but Excel **coerces numeric strings to float** (`"12345"` → `.Value` = `12345.0` → `"12345.0" ≠ "12345"`), while `.Text` returns `"12345"` — the displayed literal. Every numeric cell write fails verification.

## Suspected Code Paths

- `src/agentic_rag_mcp/office_lanes/proxy.py` `_XLS_WRITE_TEMPLATE` — the per-cell verify uses `str(.Value)`; must compare `.Text` (the displayed literal) for literal-write semantics.
- `dify/AGIAssistant/AGI_Assistant.yml` skill-loop rule — mandates search-before and save-after for ALL operational tasks, including the v2 deterministic engine ops; the PowerPoint turn paid 5 protocol rounds (2 search/save + 3 save-retries) around a 1.8 s tool call. The save-retry thrash also recurs (the agent still hand-builds the record instead of copying the example).

## Root Cause Hypothesis

Two causes: (1) a real bug — the Excel template's verification is numeric-hostile (float coercion), making every numeric cell write error out; (2) an architectural round-trip — the skill-loop protocol (search before, save + retries after) adds 3–5 LLM rounds to turns whose tool work is already sub-2-second and fully deterministic; the v2 paths ARE the deterministic flow the skill loop exists to approximate. Plus kimi's heavy deliberation (visible in both traces) is the per-turn floor. Confidence: **high** — every number is from the audit, the float probe is live.

## Proposed Remediation

**Preferred** — two parts:
1. **Fix the numeric verify** (bug): in `_XLS_WRITE_TEMPLATE`, write and verify via `.Text` semantics — `str(Cells(row, col).Text)` vs the literal (the displayed literal is what "type X" means), with `.Value` retained only for the size/existence checks. Pin: numeric strings ("12345", "3.14") pass; formulas still rejected at the tool boundary.
2. **Exempt the v2 deterministic paths from the skill loop** (DSL rule edit): doc/xls/ppt `_write_v2` and `doc_read_v2` are deterministic ENGINE operations, not agent workflows — skip `skill_search` before and skip `skill_save` after them. This removes 3–5 rounds per v2 turn (the measured 28 s PowerPoint turn becomes ≈ the tool + classifier + answer ≈ 10–15 s).

**Alternatives**: keep the loop but cache its result per conversation (complexity, no gain); the lighter-steering-model option for the Hermes lane node remains the owner's separate lever for the deliberation floor.

**Files likely to change**:
- `src/agentic_rag_mcp/office_lanes/proxy.py` (the verify lines)
- `dify/AGIAssistant/AGI_Assistant.yml` (the skill-loop exemption rule; publish)
- `tests/unit/test_office_v2.py` (pins: `.Text` compare in the template; numeric literals pass)

**Tests to add or update**:
- Template pin: `.Text` present in the verify, `str(wb.ActiveSheet.Cells(row, col).Value) != str(val)` absent
- Live: a numeric xls_write_v2 ("12345" in C1) succeeds end-to-end

## Risks & Considerations

- Exempting v2 from skill_save means the store won't accumulate engine-op "skills" — correct by design (they're routing records for the OLD agent workflows; the v2 tools need no learning). The exemption must be scoped ONLY to the v2 tool names — hermes_office_task keeps the full loop.
- The `.Text` comparison changes verify semantics slightly for formatted cells (e.g. dates) — acceptable for the literal-write surface the tool declares.

## Open Questions

- None blocking. (The kimi deliberation floor is a model choice, noted not proposed.)