# Bug Assessment: "search create a new api key in current chrome session" still lands on the General branch

- **Slug**: dont-have-a-browser-control-tool-cant-click-or-type-on-web-page
- **Created**: 2026-11-13T07:14:44Z
- **Source**: pasted text (the General branch's honest refusal: "I don't have a browser-control tool in this branch of the chat and I can't click or type on your OpenRouter page for you")
- **Verdict**: valid
- **Severity**: high

## Report (verbatim)

> "I don't have a browser-control tool in this branch and I can't click or type on your OpenRouter page for you" — the follow-up to a *successful* browser-lane turn ("open chrome go to openrouter" navigated at 07:10:02, audit row present) was answered by the **General knowledge branch**, which correctly said it lacks the tools — while the full control surface (six new spec-039 verbs, published) exists on the Hermes lane.

## Symptom

A browser-action request ("search create a new api key in current chrome session") — the EXACT phrasing the earlier routing fix added as the canonical example — still routes to `general`, stranding the workflow after a successful first step. Expected: the Hermes browser lane (navigate/read/click/select/type), completing the action with per-step screenshots.

## Reproduction

1. New chat: "open chrome go to openrouter" → **works** — `browser-navigate-v2` executed 07:10:02 (audit), the page loaded.
2. Same conversation: "search create a new api key in current chrome session" → **General branch answers** with the honest no-tools refusal; ZERO audit rows after 07:10:02 (the Hermes lane never saw it).
3. The routing rule that names this exact phrasing **is in the published artifact** (verified: `ACTION-IN-BROWSER BEATS SEARCH-FOR-INFORMATION` count 1 in the live DSL; the six 039 verbs are in the published graph, Postgres row count 23).

## Suspected Code Paths

- `dify/AGIAssistant/AGI_Assistant.yml` `intent_router` — the classifier now runs **`deepseek/deepseek-v4.1-flash`** (the owner's model switch applies to `intent_router` + `agentic_strategy`). The strengthened topic is present, but a flash-class classifier demonstrably misroutes phrasings that kimi handled: this morning's "open MS Word, type hello" class routed correctly through every misrouting fix until the flash models took the router — and note the pattern: **every routing fix so far has been topic anchoring for one phrasing at a time, on a router whose model keeps getting weaker**.
- The General branch's honest refusal is correct behavior for the wrong branch — not a defect; the fabrication risk it once had is now self-corrected.

## Root Cause Hypothesis

Topic-anchoring has hit its ceiling: the hermes_file topic now carries the canonical example verbatim and the published rule is present, yet the flash classifier still chooses `general` for "search … in current chrome session". The classifier's reliability, not the topic text, is the bottleneck — the same fix that worked under the previous model no longer holds under deepseek-v4.1-flash. Confidence: **high** — the rule is provably published, the audit shows the lane never fired, and the only variable that changed since the fix verified green is the router model.

## Proposed Remediation

**Preferred — pin the router to a strong model, keep flash on the answers** (the per-node split the infrastructure already supports):
1. `model_apply.py`: split the CHAT set — `intent_router` becomes its own `ROUTER_MODEL = "moonshotai/kimi-k3"` (the model the lane was tuned and verified on); `agentic_strategy` keeps the selected flash model (chat answers stay fast and cheap). The apply cycle writes kimi to the router regardless of the UI selection.
2. Re-verify with a phrasing battery (the verbatim OpenRouter pair, the Excel-with-filename pair, a genuine question that must STAY general) — a router battery, not single-prompt spot checks.
3. Revert path: the pin lives in the cycle constants — one line to flip back.

**Alternatives**: keep deepseek-flash and add still more topic examples (rejected: this is the third one-phrase fix for the same class; the phrasing space is unbounded); move routing to keyword/regex pre-classification in the DSL (a code-node router — deterministic but loses the model's flexibility for novel phrasings).

**Files likely to change**:
- `src/agentic_rag_mcp/deploy/model_apply.py` (the per-node split)
- `tests/unit/test_deploy_model_apply.py` (the split pin)
- `dify/AGIAssistant/AGI_Assistant.yml` (via the publish cycle)

**Tests to add or update**:
- The apply cycle writes kimi to intent_router and the selected model to agentic_strategy, in one cycle (pin)
- Live battery: the three-pair routing battery above (all three correct: 2 lane + 1 general)

## Risks & Considerations

- Router latency: kimi classifies a single sentence — milliseconds matter little vs. a misroute that costs a whole turn (and today, a stranded workflow).
- The 2026-11-05 pin guarded only the desktop LANE nodes (hermes_agent, ppt_master) — moving the router to kimi is consistent with that decision, not a reversal.
- The owner's UI model switch will keep applying to `agentic_strategy` (the answers) — the split preserves that behavior.

## Open Questions

- None blocking — the evidence trail (published rule + zero post-navigate audit rows) is unambiguous.