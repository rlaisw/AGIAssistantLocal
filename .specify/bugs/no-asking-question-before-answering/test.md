# Bug Verification: Ask-first rule not firing — coverage gap across answering lanes

- **Slug**: no-asking-question-before-answering
- **Tested**: 2026-11-19
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The bug's mechanism no longer reproduces: underspecified asks routed to either previously-uncovered lane (Hermes Local Agent, PPT-Master) now get targeted ask-backs, the widened unit pin enforces the rule on all five answering prompts, and complete requests still act/answer directly — no over-asking regression, no test regressions.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix, Hermes lane) | chat ask "move the folder" | pass | asks for source + destination ("Once you give me those, I'll pass the full task to the local file agent and report its verdict honestly") |
| Reproduction (post-fix, PPT lane) | chat asks "build a presentation for my team" and "make a deck about it" (the latter from the fix pass) | pass | asks for topic/content ("Send the topic or paste the content and I'll have a native, editable .pptx ready") |
| Over-asking regression | chat ask "open calculator" (fully specified) | pass | launches directly, no clarifying question |
| New / updated tests | `pytest tests/unit/test_ask_before_answering.py tests/contract/test_deploy_cli.py` | pass | 16/16 — five-node pin contract + the battery registry pin |
| Regression suite | `pytest tests/unit` | pass | **723 passed** — full unit suite green after the fix |
| Lint / type-check | skipped | skipped | no separate lint/typecheck gate configured for these files; the suite + YAML parse checks cover the changed surfaces |

## Output Excerpts

```
move the folder → asks-first: True | … (the destination folder/path) Once you give me those, I'll pass the full task to the local file agent and report its verdict honestly.
build a presentation for my team → asks-first: True | … Send the topic or paste the content and I'll have a native, editable .pptx ready.
open calculator → direct action, no clarifying: True
16 passed in 1.12s
723 passed, 46 warnings in 43.93s
```

## Residual Risks

- The **owner's original question** was never supplied (the assessment's two clarifications stay open by owner choice) — the fix was validated on the equivalent mechanism (underspecified ask on a previously-uncovered lane), not on the original phrasing. If that question was complete, it hit FR-003's designed direct-answer path, which is unchanged and correct.
- The rule's "critical" judgment remains model-side: a sufficiently-specified-but-ambiguous ask may still be answered with a stated assumption rather than a question — that is the spec's documented low-stakes-default edge case, not a defect.
- Lane routing between sibling agent nodes remains the known-unreliable classifier; with the rule now on every answering node, routing flips no longer change ask-first behavior, but the parked deterministic pre-router remains the deeper fix.

## Recommendation

Close the bug — verified end-to-end on the mechanism: both previously-uncovered lanes ask first, the five-node pin contract locks it against regression, and the full unit suite (723) plus the battery registry pin stay green. Commit the change set (DSL edit, widened pin, lifecycle docs) on your word.
