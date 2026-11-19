# Bug Assessment: Ask-first rule does not fire — question answered without asking

- **Slug**: no-asking-question-before-answering
- **Created**: 2026-11-19
- **Source**: pasted text ("no asking question before answer my question")
- **Verdict**: likely valid, needs reproduction
- **Severity**: medium

## Report (verbatim or summarized)

The owner reports: **"no asking question before answer my question"** — the chat answered their question directly without asking for missing critical information, contrary to the ask-before-answering rule shipped earlier the same day (spec 045, commit `c60a792`: "Before answering the user's question, ask for any critical missing information.", live-verified 10/10 on its acceptance battery).

## Symptom

A question the owner expected to trigger a clarifying ask-back was instead answered directly. Expected: per spec 045, when critical information is missing, the first response asks a targeted question before answering; complete questions answer directly (FR-003).

## Reproduction

1. The owner asked a question in the chat (the exact question is not in the report). [NEEDS CLARIFICATION: what was the question?]
2. The chat answered without asking for the missing information.
3. [NEEDS CLARIFICATION: which lane/node answered — visible from the conversation in the Chat UI, or reproducible by re-sending the same question]

## Suspected Code Paths

- `dify/AGIAssistant/AGI_Assistant.yml` — **node coverage gap, verified**: the ASK FIRST rule block exists ONLY in the two `Agentic Strategy` / `Agentic Strategy (Local)` prompts (8,675 chars each). The other answering nodes **do not carry it** (live scan 2026-11-19):
  - `Hermes Local Agent` — 19,563-char prompt, **no ASK FIRST rule** — this lane answers file/launch/office/diagnostic questions and, for underspecified local asks, its only ask-backs are its own gate behaviors (target ambiguity, unsaved changes), not the general missing-information rule
  - `PPT-Master` / `PPT-Master (Local)` — 5,963 chars each, **no ASK FIRST rule**
- `tests/unit/test_ask_before_answering.py:23` — the pin walker matches only titles starting with "Agentic Strategy", so the pin set enforces the rule on exactly those two nodes and is silent about the others — the test cannot catch this gap
- `dify/AGIAssistant/AGI_Assistant.yml` `intent_router` — lane selection between sibling agent nodes is the known-unreliable question-classifier path (documented in AGENTS.md); an underspecified local ask can land on either the strategy node (asks, per the battery evidence) or the Hermes Local Agent node (no rule), making the behavior intermittent

## Root Cause Hypothesis

**Medium-high confidence, two ranked causes (the reproduction will disambiguate):**
1. **Node coverage gap** — the question routed to an answering node whose prompt never received the rule (most plausibly the Hermes Local Agent lane). The rule works where it is placed (the 10/10 battery proved that), but the fleet has five answering prompts and only two carry the rule.
2. **Judgment call** — the question was sufficiently complete that FR-003's direct-answer behavior applied; in that case answering without asking is the specified behavior, not a bug. The spec's "critical" gate is doing its job.

The spec-045 implementation placed the rule only in the strategy prompts (the 044 pattern's two anchor surfaces), which the assessment must treat as the design's blind spot rather than the router's fault.

## Proposed Remediation

**Preferred**: extend the same ASK FIRST rule block to the **Hermes Local Agent** prompt (the lane that answers task/action questions) — and to the two PPT-Master prompts if deck requests can be underspecified ("make a deck about it") — via the established DSL edit + `deploy chatflow` publish. Widen the unit pin walker in `tests/unit/test_ask_before_answering.py` from "titles starting with Agentic Strategy" to **all five answering prompts** (strategy ×2, Hermes Local Agent, PPT-Master ×2) so the contract covers every node that can answer a question. Re-run the V1 ask-first battery including phrasings that route to the Hermes lane.

**Alternatives**:
- Wait for the reproduction, and fix only the node the failing question actually hit — smallest diff, but leaves the same gap one routing flip away.
- Add the rule to the router-level (a shared prompt fragment) — the DSL has no shared-fragment mechanism between these node prompts; per-node text is the established pattern.

**Files likely to change**:
- `dify/AGIAssistant/AGI_Assistant.yml` (Hermes Local Agent prompt + PPT-Master prompts)
- `tests/unit/test_ask_before_answering.py` (walker + expected prompt set)
- `src/agentic_rag_mcp/deploy/battery.py` (optionally extend the `ask-first` scenario with a Hermes-lane probe)

**Tests to add or update**:
- The unit pin's node set becomes all five answering prompts (red if any lacks the rule)
- A V1 battery phrasing that reliably routes to the Hermes Local Agent lane and still yields an ask-back

## Risks & Considerations

- The Hermes Local Agent prompt is gate-heavy (never-lists, two-phase confirms, anti-fabrication); the added rule must be worded to yield to those gates exactly as in the strategy prompts (lane-gate precedence sentence included).
- Over-asking regression risk is unchanged: the same no-over-asking clause ships with the rule.
- PPT-Master asks are usually self-contained deck requests; forcing the rule there may add noise — judge from the reproduction whether PPT needs it or whether Hermes-only is the honest scope.

## Open Questions

- [NEEDS CLARIFICATION: the exact question the owner asked, and (if visible) which lane answered it — this decides between cause 1 (extend the rule) and cause 2 (not a bug: FR-003 applied)]
- [NEEDS CLARIFICATION: was the question a knowledge question or an actionable task?]
