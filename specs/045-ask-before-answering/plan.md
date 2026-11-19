# Implementation Plan: Ask before answering — request critical missing information

**Branch**: `045-ask-before-answering` | **Date**: 2026-11-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/045-ask-before-answering/spec.md`

**Owner additions to this plan** (2026-11-19): a **test plan with unit tests and end-to-end test cases**, and explicit **error handling** — both are first-class sections below, not afterthoughts.

## Summary

Add the owner's directive to the AGI Chat's system prompt: *"Before answering the user's question, ask for any critical missing information."* — with the critical-qualifier definition (only info that materially changes the answer or gates a safe/meaningful action), a no-over-asking clause, a no-re-ask clause, secrets exclusion, and precedence for the existing lane gates. Steering-text-only (both Agentic-Strategy prompt surfaces, both nodes — the spec-044 pattern), **pinned by red-first unit tests on the DSL content, guarded by a new deploy-battery E2E scenario, and covered by an explicit error-handling matrix.**

## Technical Context

**Language/Version**: Dify chatflow DSL (YAML prompt text); Python 3.12 venv (tests + deploy)

**Primary Dependencies**: `agentic_rag_mcp.deploy` CLI (chatflow publish + battery harness); pytest (unit pins); the Dify chat API (E2E probes)

**Storage**: N/A (prompt text inside the chatflow DSL)

**Testing**: three layers —
1. **Unit** (`tests/unit/test_ask_before_answering.py`, pytest): pins the steering text inside `dify/AGIAssistant/AGI_Assistant.yml` for BOTH agent nodes — the directive sentence, the critical-qualifier definition, the no-over-asking clause, the no-re-ask clause, and the secrets exclusion. Red-first: written and failing before the DSL edit. Precedent: `tests/unit/test_intent_router_rules.py` pins DSL content the same way.
2. **E2E acceptance** (one-off probes, this feature's SC batteries): 10/10 underspecified asks → targeted ask-back, no action; 10/10 complete questions → direct answer, no clarifying question; 3 multi-turn coherence threads; gate-coexistence + secrets probes. Harness: the chat-API probe pattern proven in spec 044 (`/tmp/kilo/spec044_chat_probe.py` → formalized in the battery).
3. **E2E regression** (deploy battery): a new `ask-first` scenario in `src/agentic_rag_mcp/deploy/battery.py` (smoke subset: 1 underspecified ask, 1 complete ask, 1 gate-coexistence probe) so every `deploy verify` run re-checks the rule forever.

**Target Platform**: the live Dify chatflow (published via `deploy chatflow`)

**Project Type**: chatflow steering directive (additive)

**Performance Goals**: ~80 prompt-token delta on the agent nodes; no other surface

**Constraints**: no tool schema/code change (Constitution I); YAML double-quoted scalar safety; template IDs/rules of specs 043/044 untouched

**Scale/Scope**: DSL edit ×2 surfaces ×2 nodes; one new unit-test file; one new battery scenario

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Contract Preservation** — PASS: prompt text + tests only; tool schemas, response shapes, page contracts unchanged.
- **II. Tests-First** — PASS (strengthened per owner): unit pins are written RED before the DSL edit; E2E scenario registered in the battery; quickstart is the run guide.
- **III. Minimal Dependencies** — PASS: zero new dependencies (pytest and the battery harness exist).
- **IV. Honest Answers** — PASS: FR-002 *is* an anti-fabrication rule (ask, never invent); the ask-back must survive the honesty_check node (no action claims → safe by construction, verified by probe).
- **V. Spec-Driven Replacement** — PASS: nothing superseded; additive over the existing chat behavior.
- **Quality Gates** — full pytest suite green (unit pins included); battery green including the new scenario.

Post-Phase-1 re-check: unchanged — the design adds tests around prompt text, no gate moves.

## Error Handling (owner-requested section)

| # | Failure mode | Handling | Where verified |
|---|---|---|---|
| E1 | User's reply to an ask-back is itself ambiguous/partial | One targeted re-ask for **only the still-missing piece**; if still insufficient, state exactly what is needed and stop asking — never loop | quickstart E1 probe |
| E2 | A lane gate already asks back for this prompt (launch ambiguity, office confirmation) | The lane gate is authoritative (FR-005); the probe treats a lane-gate ask-back as a PASS — no double-ask, no weakening | battery `ask-first` coexistence probe |
| E3 | Chatflow publish fails mid-deploy | The previously published behavior stays live (deploy CLI surfaces the error); probes require the served-DSL check first — never probe a stale draft | quickstart step (served-DSL gate before probing) |
| E4 | Honesty/dispatch-leak nodes interfering with ask-backs | An ask-back contains no action claim, so the honesty_check replaces nothing; one probe confirms the ask-back relays verbatim | quickstart E4 probe |
| E5 | Over-asking regression (rule drifts toward interrogation) | SC-002's direct-answer battery is the guard; a violation = steering rewording + republish, never accepted as "cautious" | SC-002 (10/10) |
| E6 | Missing info is a secret/credential | The steering text forbids requesting secrets as missing information — the chat points to the configured location instead | quickstart secrets probe |
| E7 | Probe/stack down | Probes abort on the stack health gate (`./startup.sh` all-green prerequisite); a failed probe never silently passes | quickstart prerequisites |

## Project Structure

### Documentation (this feature)

```text
specs/045-ask-before-answering/
├── plan.md            # This file (incl. test plan + error handling)
├── research.md        # Phase 0 decisions
├── data-model.md      # Phase 1 entities
├── quickstart.md      # Phase 1 validation guide (the runnable test plan)
└── spec.md
```

### Source Code (repository root)

```text
dify/AGIAssistant/AGI_Assistant.yml        # EDIT — both strategy-node prompts (×2 surfaces each)
tests/unit/test_ask_before_answering.py    # NEW — red-first DSL content pins (unit tests)
src/agentic_rag_mcp/deploy/battery.py       # EDIT — new "ask-first" E2E scenario
```

## Files to Change & Shape

1. `tests/unit/test_ask_before_answering.py` (NEW, written first — red): parse `dify/AGIAssistant/AGI_Assistant.yml`; for each Agentic-Strategy system prompt assert: the directive sentence ("before answering… ask for any critical missing information"), the critical definition ("materially changes the answer, or gates a safe/meaningful action"), the no-over-asking clause ("questions that are complete answer directly — do not interrogate"), the no-re-ask clause ("never re-ask what the conversation already established"), and the secrets exclusion ("never ask for passwords or API keys — point to their configured location"). ~6 tests.
2. `dify/AGIAssistant/AGI_Assistant.yml`: append the rule block to both strategy-node system prompts — the owner's sentence verbatim as the headline, then the four supporting clauses. Same YAML scalar rules as 044.
3. `src/agentic_rag_mcp/deploy/battery.py`: new `scenario_ask_first` (registered alongside `office-routing`/`chat-journey`): sends 1 underspecified ask (expect ask-back + no tool action), 1 complete question (expect direct answer, no question), 1 launch-ambiguity probe (expect the lane gate's own ask-back, not a double-ask). Uses the chat-API probe helper (same pattern as `chat-journey`).
4. Publish + served-DSL verification (`deploy chatflow`, Postgres check), then the quickstart batteries.

## Phases

- **Phase 0 — Research**: the five decisions (placement, unit-pin surface, battery-vs-one-off E2E split, rule wording, error matrix) → `research.md`.
- **Phase 1 — Design**: entities (`data-model.md`), runnable test guide (`quickstart.md`). No contracts/ artifact — no external interface changes (same recorded decision as spec 044).

## Testing Strategy (the test plan, consolidated)

| Layer | What | Command | Gate |
|---|---|---|---|
| Unit (red-first) | DSL steering pins, both nodes | `pytest tests/unit/test_ask_before_answering.py` | all green after the edit; written red before it |
| E2E acceptance — SC-001 | 10 underspecified phrasings → ask-back, no action | quickstart V1 | 10/10 |
| E2E acceptance — SC-002 | 10 complete questions → direct answer | quickstart V2 | 10/10 |
| E2E acceptance — SC-004 | 3 multi-turn threads: ask → user answers → act, no re-ask | quickstart V3 | 3/3 |
| E2E acceptance — gates + secrets (FR-005/E6) | lane-gate ask-backs unchanged; no secrets requested | quickstart V4 | pass |
| E2E regression — SC-003 | `ask-first` scenario + full battery | `python -m agentic_rag_mcp.deploy verify` | green, 0 double-asks |
| Full suite | no new failures anywhere | `pytest tests/` | green |
