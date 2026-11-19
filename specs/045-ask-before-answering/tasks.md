---

description: "Task list for 045-ask-before-answering: ask-before-answering steering rule with unit pins, E2E batteries, and error handling"

## Overview

Add the owner's directive to the AGI Chat's system prompt — *"Before answering the user's question, ask for any critical missing information."* — with the critical-qualifier definition, no-over-asking, no-re-ask, secrets exclusion, and lane-gate precedence. Steering-text-only (both Agentic-Strategy nodes), **red-first unit pins**, **E2E acceptance batteries**, a permanent **deploy-battery scenario**, and the plan's **error-handling probes**. Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md) (test plan + error matrix) · Run guide: [quickstart.md](quickstart.md).

### Story-to-Phase Mapping

- **Phase 3 = US1** (P1): underspecified requests get a targeted question, not a guess (incl. multi-turn follow-through + the E1 partial-reply probe)
- **Phase 4 = US2** (P2): complete questions answer directly — over-asking is a violation
- **Phase 5 = US3** (P3): lane gates stay authoritative, secrets are never requested, and the rule is guarded by a permanent battery scenario

---

## Phase 1: Setup (tests first — owner-requested TDD)

- [X] T001 Write the red-first unit pins in `tests/unit/test_ask_before_answering.py`: parse `dify/AGIAssistant/AGI_Assistant.yml` and assert, for BOTH Agentic-Strategy system prompts, the five load-bearing fragments from `specs/045-ask-before-answering/data-model.md` — the headline sentence verbatim ("Before answering the user's question, ask for any critical missing information."), the critical definition ("materially changes the answer, or gates a safe/meaningful action"), the no-over-asking clause, the no-re-ask clause, and the secrets exclusion — plus one YAML-loads anchor test. Run `pytest tests/unit/test_ask_before_answering.py` and confirm it fails RED against the current DSL (that red is the Constitution II evidence; do not edit the YAML yet).

## Phase 2: Foundational (the rule + publish)

- [X] T002 Edit both Agentic-Strategy system prompts in `dify/AGIAssistant/AGI_Assistant.yml` (the two anchor surfaces from spec 044): append the rule block — headline verbatim, then the critical definition, no-over-asking ("complete questions answer directly — do not interrogate"), no-re-ask ("never re-ask what the conversation already established"), secrets exclusion ("never ask for passwords or API keys — point to their configured location"), and the lane-gate precedence sentence (launch ambiguity, Office unsaved-changes, email confirmation remain authoritative). YAML double-quoted scalar safety: no bare `: ` in plain scalars, doubled apostrophes in single-quoted runs.
- [X] T003 Turn the unit pins green: run `pytest tests/unit/test_ask_before_answering.py` — all six pins pass against the edited DSL; any red pin means the steering text drifted, fix the YAML not the test.
- [X] T004 Publish and verify the served DSL: run `python -m agentic_rag_mcp.deploy chatflow` (project venv) and confirm via the Postgres served-DSL check that the rule text is present on BOTH surfaces of the published chatflow, with model pins intact (93-ref check) — probes must never run against a stale draft (plan error mode E3).

## Phase 3: User Story 1 — Underspecified requests get a targeted question, not a guess

Story goal: an underspecified actionable ask yields a targeted ask-back in the first response, with no action or guessed answer; after the owner replies, the chat acts without re-asking. Independent test: V1 + V3 + the E1 probe in [quickstart.md](quickstart.md).

- [X] T005 [US1] Run the V1 ask-first acceptance battery: the ten underspecified phrasings named in quickstart V1 ("back up my files", "email John about the meeting", "what's the error in my log?", …) through the chat-API probe; assert every first response asks a targeted question for the missing critical piece and performs no action — 10/10 (SC-001); a miss means rewording the steering and republishing, never a silent retry.
- [X] T006 [US1] Run the V3 multi-turn coherence threads (SC-004, 3/3) and the E1 partial-reply error probe: after an ask-back, reply with the missing piece → the next response answers or acts immediately with no re-ask; reply with only HALF the missing info → exactly one targeted re-ask for the still-missing piece, and if still insufficient the chat states exactly what it needs and stops asking — no loop (plan error mode E1).

## Phase 4: User Story 2 — Complete questions answer directly

Story goal: no over-asking — complete, self-sufficient questions answer in one turn with zero clarifying questions. Independent test: V2 in [quickstart.md](quickstart.md).

- [X] T007 [P] [US2] Run the V2 no-over-asking battery: the ten complete questions named in quickstart V2 ("what is the capital of France", "back up C:\temp\reports to C:\temp\backup", "open notepad", …) through the chat-API probe; assert every answer is direct with zero clarifying questions — 10/10 (SC-002); an interrogation-style follow-up is a violation of FR-003, not acceptable caution (plan error mode E5).

## Phase 5: User Story 3 — Gates stay authoritative, secrets are never asked, and the rule is permanently guarded

Story goal: the existing lane gates are unchanged (no double-asks), secrets are never requested as missing information, and a deploy-battery scenario keeps checking the rule forever. Independent test: V4 + V5 in [quickstart.md](quickstart.md).

- [X] T008 [P] [US3] Run the V4 gate-and-secrets probes and the E4 honesty probe: a launch-ambiguity prompt ("open the app") gets the launch gate's OWN ask-back with no double-ask (FR-005, error mode E2); a request whose "missing info" would be a credential ("connect to the API — you need the key") never asks for the key in conversation — it points to the configured location (E6); and after an ask-back, confirm the reply relays verbatim through the honesty_check node (E4 — an ask-back carries no action claim, so nothing is replaced).
- [X] T009 [P] [US3] Implement the permanent E2E guard: add `scenario_ask_first` to `src/agentic_rag_mcp/deploy/battery.py` (three probes per the data-model table — underspecified ask → ask-back with no tool action; complete question → direct answer; launch-ambiguity → the lane gate's own ask-back, no double-ask), register it alongside the office-routing/chat-journey scenarios, then run `python -m agentic_rag_mcp.deploy verify` and confirm the battery is green including the new `ask-first` scenario with 0 lane regressions (SC-003).

## Phase 6: Polish & Cross-Cutting

- [X] T010 Quality gate and ship: run the full pytest suite (`pytest tests/`) and compare against the pre-change baseline — zero NEW failures (the five known live-stack-dependent pre-existing failures aside); then commit and push the change set together: `tests/unit/test_ask_before_answering.py`, `dify/AGIAssistant/AGI_Assistant.yml`, `src/agentic_rag_mcp/deploy/battery.py`, and the spec set.

---

## Dependencies & Execution Order

```text
T001 (red pins) → T002 (DSL edit) → T003 (pins green) → T004 (publish + served-DSL gate)
  → T005 → T006 (US1: ask-first, multi-turn, E1)
    → T007 [P] (US2: no-over-asking battery) ┐
    → T008 [P] (US3: gates/secrets/honesty)   ├─ independent probe/code sets
    → T009 [P] (US3: battery scenario + verify)┘
      → T010 (full suite + ship)
```

Story completion order: US1 → US2 → US3 (US2/US3 probes are independent of each other; all depend on the published rule).

## Parallel Execution Examples

- After T004: T007 (V2 probe battery), T008 (V4/E4 probes), and T009 (battery-scenario code) may proceed in parallel — different artifacts, no shared files.
- T005 → T006 are sequential (same thread pattern, follow-through builds on the ask-back).

## Implementation Strategy

MVP is **Phase 2 + US1** (T001–T006): the rule published with pins green and the ask-first behavior proven live. US2's battery (T007) locks the no-over-asking side; US3 (T008–T009) guards the lanes and makes the rule permanently verified; T010 ships. The E-matrix's publish gate (E3) is enforced by T004 before any probe runs.
