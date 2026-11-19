# Bug Fix: Ask-first rule not firing — rule extended to all five answering prompts

- **Slug**: no-asking-question-before-answering
- **Fixed**: 2026-11-19
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The ASK FIRST rule (spec 045) existed only in the two Agentic Strategy prompts; questions routed to the Hermes Local Agent or PPT-Master lanes were answered by prompts that never carried the rule — the coverage gap the assessment identified. The identical rule block now lives in **all five answering prompts**, the unit pin enforces that contract, and the widened behavior is live-verified in both previously-uncovered lanes with no over-asking regression.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | ASK FIRST rule block added to `Hermes Local Agent` (double-quoted scalar, `\n` escapes) and both `PPT-Master` prompts (single-quoted scalars, real newlines, apostrophes doubled — the two styles differ per node; the first attempt used the wrong style for PPT and was reverted) |
| `tests/unit/test_ask_before_answering.py` | modified | pin walker widened from "Agentic Strategy*" to the explicit five-node set (`ANSWERING_NODE_TITLES`); structure test expects 5 answering prompts; fragment tests unchanged (now enforce all five) |
| (published) | deploy | `python -m agentic_rag_mcp.deploy chatflow` — served DSL verified carrying the rule, model pins intact (95 refs) |

## Diff Highlights (optional)

```yaml
# Hermes Local Agent (double-quoted scalar)
"# Hermes Local Agent (specs 028 + 029)\n\nASK FIRST (spec 045):\n- Before answering the user's question, ask for any critical missing information.\n- Critical means information that materially changes the answer or the action, makes it unsafe, or leaves it meaningless — …"
# PPT-Master (single-quoted scalar; apostrophes doubled)
value: '# PPT-Master Agent Rulebook (quick-generate, v1)
  ASK FIRST (spec 045):
  - Before answering the user''s question, ask for any critical missing information. …'
```

## Tests Added or Updated

- `tests/unit/test_ask_before_answering.py::test_dsl_loads_and_answering_prompts_found` — expects exactly 5 answering prompts (strategy ×2, Hermes Local Agent, PPT-Master ×2); a sixth answering node without the rule will also fail it (the walker collects all five known titles)
- `…::test_rule_fragments_present_in_every_strategy_prompt[…]` — the five load-bearing fragments now enforced on **all five** prompts, so the exact gap this bug reported (a lane answering without the rule) can no longer regress silently

## Local Verification

- Commands: `pytest tests/unit/test_ask_before_answering.py` → **6/6 green** (the widened pin passes against the five-prompt state; pre-edit it failed red on the three uncovered prompts)
- `deploy chatflow` → published; served DSL: rule present, model pins intact
- Live probes (chat API):
  - `make a deck about it` (PPT-Master lane, previously uncovered) → **asks for topic/source** ✓
  - `copy the file` (file lane) → **asks for source + destination** ✓
  - `what is the capital of Germany` → answers directly (Berlin), no clarifying question ✓
  - `list the files in C:\temp` → answers directly with the listing, no clarifying question ✓ (no over-asking regression)

## Deviations from Assessment

- Applied without the reproduction (owner's explicit choice at the fix gate — "Apply the fix now"): the two `[NEEDS CLARIFICATION]` items in the assessment (the exact question, its lane) remain open; the fix is the assessment's preferred remediation regardless of which cause the original question hit. If the owner later supplies the question and it turns out to have been a complete question (FR-003 behavior), this fix changes nothing for it — the rule's critical gate still answers complete questions directly, as the regression probes show.
- Scope per the assessment's "Files likely to change": PPT-Master was included (the assessment left it conditional on the reproduction; the owner's choice to apply the full fix resolves that condition to include — the "make a deck about it" probe shows deck requests genuinely can be underspecified, and the no-over-asking clause guards the noise risk the assessment flagged).

## Follow-ups

- Uncommitted: the DSL edit + the widened pin + this lifecycle set — commit on the owner's word.
- The battery's `ask-first` scenario still probes via strategy-lane phrasings; a PPT-lane probe could be added later if deck ask-backs become a regression concern.
- The two open clarifications in `assessment.md` stay open as historical record; closing them is optional now that the fix is unconditional.
