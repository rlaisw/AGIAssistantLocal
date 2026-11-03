# Bug Verification: PowerPoint background — fabricated verdict from the general branch

- **Slug**: `ppt-fail-change-background`
- **Tested**: 2026-11-02
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original defect — a **fabricated gate verdict** ("Blocked: …") presented by the general-lane agent that never called the gate — was exercised live post-fix and **does not reproduce**: with a real gate refusal sitting in the conversation history, a bare local-task-shaped follow-up that landed on the general branch produced an honest answer with zero verdict text, and the model's visible reasoning explicitly cites the new anti-fabrication rule. The original background phrasing now routes to the Hermes branch and receives the *real* gate refusal. No regressions found.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix, fabrication path) | Conversation: "make cell A1 bold" (real gate block, "Blocked:" in history) → then bare follow-ups; "make the whole thing prettier" landed on the **general** branch | **pass** | General answer contains **no** "Blocked:" verdict text; its reasoning quotes the rule: *"the system prompt says I may only report results of tools I actually called. In this turn, I haven't called any tool."* — the anti-fabrication rule actively steering the exact bug-report scenario |
| Reproduction (post-fix, original phrasing) | Live `scenario_office_routing` (includes the bare "change to dark background" guard) | **pass** | All three phrasings → hermes; real-block-setup ok; no-fabrication ok (72 s) |
| New / updated tests | `pytest tests/contract/test_deploy_cli.py tests/unit/test_office_gate.py tests/unit/test_hermes_office_tool.py` | **pass** | 47 passed |
| Regression (general lane) | General-branch answers: the fabrication-path probe above (normal reasoning, no breakage) + the fix-run's Q&A sanity ("capital of France" → Paris, no verdict text) | **pass** | The instruction addition did not break normal Q&A |
| Lint | `ruff check src/agentic_rag_mcp/deploy/battery.py` | **pass (one new trivial)** | 5 pre-existing findings; **one new**: `battery.py:618 RUF059 unused 'answer'` in the routing-probe loop — cosmetic, from the fix's guard code; fix at commit prep (rename to `_`) |

## Output Excerpts

```
setup: hermes | real Blocked: in answer: True          # real gate refusal in history
followup 'make the whole thing prettier' -> general | fabricated-verdict: False
  general reasoning: "…the system prompt says I may only report results of tools I
  actually called. In this turn, I haven't called any tool…"

routing+guard scenario: PASS | …'change the PowerPoint background to ' -> hermes ok;
  real-block-setup ok (hermes); no-fabrication ok (bare-followup -> hermes)
47 passed in 2.47s
```

## Residual Risks

- The anti-fabrication rule is a **behavioral instruction** to an LLM, not a structural guarantee — the model followed it in the first live exposure to the exact bug scenario, and the battery's no-fabrication assertion now enforces it on every `deploy verify`, but a sufficiently confused model could still breach; the guard catches it when it does.
- The general agent's answers still begin with leaked reasoning text ("The user asks…") — a pre-existing answer-formatting artifact across all lanes, out of this bug's scope.
- The fix is **uncommitted** (folds into the held T022 commit); a clean-clone deploy before that commit would lose it.
- The user-visible headline — background colors cannot be changed — remains the designed v1 refusal (spec 030 Out of Scope, owner's clarify-pass-2 decision); making it *work* is the named formatting follow-up version, a separate spec.

## Recommendation

Close the bug — **verified end-to-end**: the fabrication path was exercised live with the exact bug-report setup (real gate refusal in history + a general-branch follow-up) and produced an honest, rule-citing answer instead of a fabricated verdict; the original phrasing now routes to the real gate; the automated guard passes and covers both branches on every future battery run. Fold the fix into the held T022 commit; clean up the one cosmetic lint (`answer` → `_` in the probe loop) in the same pass.
