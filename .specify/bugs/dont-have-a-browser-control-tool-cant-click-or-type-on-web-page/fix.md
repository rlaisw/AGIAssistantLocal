# Bug Fix: router pinned to kimi (per-node split) — LIVE-VERIFIED; the specific phrasing still needs the deterministic pre-router

- **Slug**: dont-have-a-browser-control-tool-cant-click-or-type-on-web-page
- **Fixed**: 2026-11-13T07:18:09Z
- **Assessment**: ./assessment.md
- **Status**: partial (two real fixes live; the killer phrasing needs one structural step more)

## Summary

The per-node model split is live and verified in the SERVED graph (router = kimi-k3, answers = your flash selection) — a structural improvement that makes routing robust for every phrasing class we fixed earlier. And a subtle revert bug was found and closed: my exclusion publish had overwritten the router pin in the artifact (the chatflow publish of a stale artifact reverted the apply cycle's model patch), so the kimi pin never actually served until re-applied. BUT the live replay of the killer phrasing ("search create a new api key in current chrome session") under the verified kimi router STILL routes to General — even with the explicit topic rules and the general-class exclusion published. The question-classifier is structurally unreliable for this phrasing; the deterministic pre-classification code node is the remaining fix.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/deploy/model_apply.py` | per-node split | `ROUTER_MODEL = kimi-k3` on `intent_router`; `ANSWER_NODE_IDS = (agentic_strategy,)` takes the UI selection; desktop pins unchanged |
| `tests/unit/test_deploy_model_apply.py` | 2 pins rewritten + 1 added | split contract; router pin survives ANY selection |
| `dify/AGIAssistant/AGI_Assistant.yml` | general-class explicit exclusion (both instances) | "BUT NEVER a request to DO something inside the user's browser/current chrome session … even when they contain 'search'" |
| applied live | apply-model cycle re-run | **served graph verified from Postgres**: router kimi-k3, answer flash |

## Local Verification

- 639 unit green, ruff clean.
- The routing battery: PAIR1-A (open chrome go to openrouter) → **browser lane** ✓ (audit 07:21:45); PAIR2 (Excel-with-filename) → **office lane** ✓; PAIR3 (genuine question) → **General** ✓.
- **The honest finding**: PAIR1-B ("search create a new api key in current chrome session") under the VERIFIED kimi router → **still General** (zero Hermes-lane rows after the replay). Topic anchoring — strong model, explicit rules, exclusion — has now failed for this phrasing three different ways.

## Deviations from Assessment

1. **The flash-model hypothesis was falsified**: the assessment's preferred fix assumed the flash router was the bottleneck. After the artifact-revert bug was fixed and kimi was verified serving, the phrasing STILL misroutes — so the root cause is the classifier structure, not just the model. The split remains valuable (verified battery: 3/4 pairs correct) and is the foundation the pre-router builds on.
2. **An unrecorded revert bug discovered**: editing the DSL artifact directly and publishing (the exclusion edit) silently reverted the apply-model cycle's router pin, because `deploy chatflow` publishes whatever the artifact holds. The apply cycle was re-run after; the lesson (topic edits and model pins must land in the same cycle, or the topic edit must re-apply the model patch) is recorded here.

## Follow-ups

- **The remaining fix — the deterministic pre-classification code node** (the assessment's structural alternative): a regex gate before the intent_router that forces the hermes class for high-confidence local/browser-action patterns ("search … in current chrome session", "in my browser …", "click X on <site>") — any model then confirms rather than guesses. Real DSL surgery (new node + edge rewire); the patterns are the three phrasings that empirically failed.
- Interim mitigation for daily use: imperative open-form phrasings route correctly today ("open chrome go to openrouter" ✓) — lead with the verb.
