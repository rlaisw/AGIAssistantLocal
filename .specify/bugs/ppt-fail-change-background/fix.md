# Bug Fix: PowerPoint background refusal — anti-fabrication rule, background routing, and a battery guard

- **Slug**: `ppt-fail-change-background`
- **Fixed**: 2026-11-02
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The real defect — the general-lane agent **fabricating gate-verdict text** ("Blocked: …") for requests it had no tool for — is now forbidden by an explicit **anti-fabrication rule** added to both general agents' instructions (only report tools actually called; never present verdict blocks; redirect local-task requests honestly). The classifier now recognizes **background/theme changes** as Office tasks (app-named phrasing routes to Hermes and receives the *real* gate refusal), and the `office-routing` battery scenario gained a **fabrication guard** that builds a real gate refusal in conversation history, sends the bare context-less follow-up, and asserts no fake verdicts from a branch that never called the gate. The v1 formatting refusal itself (background colors out of scope) is unchanged by design — that is the owner's clarify-pass-2 decision, honored.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | **Anti-fabrication rule** appended to the instructions of BOTH general-agent twins — `agentic_strategy` (cloud, deepseek — the one that fabricated in the report) and `agentic_strategy_local` (qwen): only report tools actually called; never fabricate verdict blocks/status messages even if similar ones appear in history; redirect local-task requests; never describe uninspected files. *Deliberate within-contract extension: the assessment named "the general agent"; both twins share the identical instruction and exposure class.* |
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | **Classifier** (`intent_router` topic + instruction): background/theme phrasing added to the Office clause ("changing slide backgrounds or themes", e.g. 'change the PowerPoint background to dark') — app-named prompts now route to Hermes and get the real gate refusal |
| `src/agentic_rag_mcp/deploy/battery.py` | modified | `scenario_office_routing` extended: a third routing probe (app-named background change → hermes) plus the **fabrication guard** — real-gate-refusal setup in a conversation, then the bare *"change to dark background"* follow-up; if the general branch answers, it must NOT contain "Blocked:" verdict text (a hermes-branch answer is a real verdict and is fine) |

## Diff Highlights (optional)

```yaml
# general-agent instruction (both twins) — the Constitution IV rule
HONESTY — TOOL RESULTS (mandatory):
- You may ONLY report results of tools you actually called in this turn. NEVER
  fabricate tool results, verdict blocks, or status messages ('Blocked:',
  'TASK:', 'ok') — even if similar ones appear earlier in the conversation...
- If the user's request needs a capability you do not have (local files,
  launching programs, Office control), say plainly that this branch does not
  have that tool and ask them to resend it as a local task.
```

## Tests Added or Updated

- `scenario_office_routing` (battery) — now pins: (1) insert-row/add-column/app-named-background phrasings all route to Hermes; (2) a real gate refusal appears in history after a genuine block; (3) a bare context-less follow-up in that same conversation carries **no fabricated verdict text** from the general branch. Scenario count unchanged (15) — no registry test change needed.

## Local Verification

- Commands: DSL validation (yaml.safe_load + node assertions) → both twins carry the rule, classifier carries background phrasing; `pytest tests/contract/test_deploy_cli.py tests/unit/test_office_gate.py` → **34 passed**; `deploy chatflow` → published to the live app
- Live `scenario_office_routing` → **PASS (72 s)**: all three phrasings → hermes; real-block-setup ok; no-fabrication ok. Notably the bare *"change to dark background"* now also routes to **Hermes** (the classifier's background examples improved even bare-phrasing routing), so the fabrication path itself wasn't taken this run — the guard still asserts it for the general branch on any future regression
- General-lane sanity probe ("what is the capital of France?") → general branch answers normally (Paris ✓), no fabricated verdict text — the instruction addition did not break normal Q&A

## Deviations from Assessment

- The anti-fabrication rule was applied to **both** general-agent twins, not only the cloud one that fabricated. The assessment named "the general agent's instruction"; both nodes share the identical instruction and the same exposure class (the local qwen twin could fabricate identically), so covering both is the honest reading of the contract. Logged here for transparency.
- The `agentic_strategy_local` model remains `qwen3-8b-nothink` (untouched — the model-swap decision was explicitly out of this fix's scope, per the assessment).

## Follow-ups

- Fold this fix into the held T022 commit for spec 030 (same uncommitted files).
- Full 15-scenario `deploy verify` on the next deploy cycle (the general-agent instruction change touches every general-lane answer; the routing + sanity probes here cover the critical paths, the full battery is the belt-and-braces pass).
- If the owner wants background/theme changes to actually **work** (rather than be honestly refused), that is spec 030's named "formatting follow-up version" — a new spec, not this bug.
- If a fabricated verdict is ever observed again despite the rule, the next lever is moving `agentic_strategy` off `deepseek-v4.1-flash` (the owner's separate cost/behavior decision, recorded in the `office-routing-flake` fix report).
