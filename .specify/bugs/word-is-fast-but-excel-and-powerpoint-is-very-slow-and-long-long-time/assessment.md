# Bug Assessment: Excel and PowerPoint ride the slow lane while Word is fast

- **Slug**: word-is-fast-but-excel-and-powerpoint-is-very-slow-and-long-long-time
- **Created**: 2026-11-13T02:38:27Z
- **Source**: pasted text (owner's live experience)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim)

> "Word is fast but Excel and Powerpoint is very slow and long long time"

## Symptom

Simple Office write tasks take **0.7–5 s for Word** (the `doc_write_v2` fast path) but **143–156 s for Excel and PowerPoint** — the same class of task on the slow office lane.

## Reproduction (measured from the audit)

| Turn | Lane | Duration | The turn's own steps |
|------|------|----------|---------------------|
| Word write ("pqr_hellp_test_2.docx") | **doc_write_v2** | **5.0 s** | one deterministic call |
| Word write ("sdsdsad_3123…") | **doc_write_v2** | **0.7 s** | one deterministic call |
| Excel write (02:36:28) | hermes_office_task | **156.4 s** | STEP 1: *"gateway RunPython channel was stripped… switched to direct channel"* (the persistent **arg-strip**), STEP 2: write |
| PowerPoint write (02:38:40) | hermes_office_task | **143.9 s** | THREE steps — two of them pure arg-strip recovery (canaries), then the write |

The user's experience is exact: Excel/PPT turns pay the double-LLM office lane (75–156 s class) **plus the arg-strip probe/recovery tax** (2 of the PowerPoint turn's 3 steps were recovery), while Word escapes both via the v2 proxy.

## Suspected Code Paths

- `src/agentic_rag_mcp/office_lanes/proxy.py` — the v2 primitives exist **only for Word** (`_WRITE_TEMPLATE`/`_READ_TEMPLATE` use `Word.Application` COM); no Excel/PowerPoint templates.
- `src/agentic_rag_mcp/server.py` — `doc_write_v2`/`doc_read_v2` are Word-only tools; `xls_*`/`ppt_*` v2 equivalents don't exist.
- `dify/AGIAssistant/AGI_Assistant.yml` — the fast-path rule covers only "create a **Word** document" phrasings; "open Excel and write X" / "open PowerPoint and type X" fall through to `hermes_office_task`.

## Root Cause Hypothesis

The office v2 was scoped to Word first (the reported bug's shape), so Excel and PowerPoint simple writes still ride the full agent turn — and the persistent gateway arg-strip adds a 2-step recovery tax on top (both measured turns spent their first steps on canary probes). Same architectural class, same fix, two more apps. Confidence: **high** — all four audit rows above are from the last hour.

## Proposed Remediation

**Preferred — extend the office v2 to Excel and PowerPoint** (the proven Word pattern, whole):
1. **Templates** in `office_lanes/proxy.py`:
   - `_XLS_WRITE_TEMPLATE` — `Excel.Application` (visible): pre-close same-path workbook, `Workbooks.Add`, write a literal cell map (`{"A1": "x", "B2": "y"}`) from `data`, `SaveAs` to `C:\OfficeMCP\<name>.xlsx`, verify (read the cells back), leave open + **maximize + front** (the owner's Word request applies to all three apps).
   - `_PPT_WRITE_TEMPLATE` — `Powerpoint.Application` (visible): pre-close same-path presentation, `Presentations.Add`, one slide (title + optional body text) from `data`, `SaveAs` `.pptx`, verify, leave open + maximize + front.
2. **Tools** in `server.py`: `xls_write_v2(cells, name?, conversation_id)` and `ppt_write_v2(title, text?, name?, conversation_id)` — literal-only inputs, name sanitization (`.xlsx`/`.pptx`), honest existed/replaced, audit rows with cid, best-effort fronting.
3. **DSL routing**: "open Excel and write/type X (in cell Y)" → `xls_write_v2`; "open PowerPoint and type/make a slide with X" → `ppt_write_v2`; everything else (formulas, edits, multi-slide decks, existing-file surgery) stays on `hermes_office_task`.

**Alternatives**: accept the slow lane for Excel/PPT — the 143–156 s measurements are exactly the complaint.

**Files likely to change**:
- `src/agentic_rag_mcp/office_lanes/proxy.py` (two templates + write/read methods)
- `src/agentic_rag_mcp/server.py` (two tools)
- `dify/AGIAssistant/AGI_Assistant.yml` (routing; publish)
- `tests/unit/test_office_v2.py` (pins: cell-map parameterization, title/text, same-path pre-close, fronting, sanitization per extension)

**Tests to add or update**:
- Template pins: Excel/PowerPoint templates verify in code, pre-close same-path, keep the app visible, front+maximize
- Tool pins: cell map is literal-only; name sanitization (.xlsx/.pptx); cid required
- Live timing: one Excel write + one PowerPoint write through the deployed tools (target: seconds, matching Word's 0.7–5 s)

## Risks & Considerations

- PowerPoint COM is quirkiest (no hidden mode; `Visible=True` mandatory for some operations; SaveAs format enums 11/24 for pptx) — template must be live-probed before shipping (the Word template needed 3 probes: locks, envelope, fronting).
- Excel cell keys: validate `[A-Z]{1,3}[1-9][0-9]{0,6}` — no formulas, no `=`-prefixed values (literal text only; formulas would reintroduce code injection into a "data" surface).
- Keep `hermes_office_task` untouched for the complex class.

## Open Questions

- None blocking.