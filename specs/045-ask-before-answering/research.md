# Research — 045-ask-before-answering

## R1. Where does the rule live?

- **Decision**: the chatflow's agent system prompt, in both Agentic-Strategy nodes (`dify/AGIAssistant/AGI_Assistant.yml`), appended as a rule block — the same two-surface placement as spec 044's infographic default.
- **Rationale**: the rule governs conversation behavior across all lanes; only the steering text can do that without code. Both nodes carry the prompt (044 established the anchor strings appear exactly twice).
- **Alternatives considered**: per-lane prompt edits (the rule is cross-lane, so central is right); a dedicated clarification node in the DSL graph (rejected: adds graph complexity and a latency hop for a judgment the agent can make inline).

## R2. What is the unit-testable surface for a prompt-text feature?

- **Decision**: red-first pytest pins on the DSL content itself — `tests/unit/test_ask_before_answering.py` parses `dify/AGIAssistant/AGI_Assistant.yml` and asserts the five load-bearing text fragments exist in BOTH strategy-node system prompts.
- **Rationale**: the steering text is the deliverable, so its presence in the source of truth is exactly what a unit test can and should pin — this catches console-side reverts, careless hand edits, and merge drift. Precedent: `tests/unit/test_intent_router_rules.py` already pins DSL content; spec 043 pinned the no-attachment byte-identical body the same way. "Which reply the LLM gives" is behavior, not structure — that belongs to E2E.
- **Alternatives considered**: testing the *served* Postgres DSL from pytest (rejected: couples unit tests to a live database — that's the quickstart/served-DSL gate); mocking an LLM to score phrasings (rejected: unfalsifiable theater).

## R3. Which E2E harness — one-off probes or a deploy-battery scenario?

- **Decision**: both, split by purpose. The full 10/10 acceptance batteries (SC-001/SC-002) and the multi-turn/gate/secrets probes run once as acceptance (quickstart guide, chat-API probe pattern proven in spec 044). A compact `ask-first` scenario (1 underspecified + 1 complete + 1 gate-coexistence probe) is added to `deploy/battery.py` so every future `deploy verify` re-checks the rule.
- **Rationale**: 10/10 batteries are too slow for every verify run, but a smoke subset is cheap (3 chat turns) and matches the repo's pattern — every behavioral rule (stop-generation, honest-errors, office-routing) has a battery scenario; a steering rule this central should too.
- **Alternatives considered**: battery-only (loses the statistical acceptance the SCs demand); probes-only (the rule would silently rot after future DSL edits — exactly what the battery exists to prevent).

## R4. How is the rule worded?

- **Decision**: the owner's sentence verbatim as the headline — "Before answering the user's question, ask for any critical missing information." — followed by four supporting clauses: (1) the critical definition (info that materially changes the answer, or gates a safe/meaningful action), (2) no over-asking (complete questions answer directly — do not interrogate), (3) no re-asking what the conversation already established, (4) secrets are never requested as missing information — point to the configured location. Plus one precedence sentence: lane-gate ask-backs (launch ambiguity, Office unsaved-changes, email confirmation) remain authoritative where they apply.
- **Rationale**: the owner's wording is the directive; the clauses pin the semantics the spec's FRs demand and the two probe batteries measure. Keeping the headline verbatim makes the intent auditable against the spec.
- **Alternatives considered**: paraphrasing the headline (rejected — the owner's sentence IS the spec input); omitting the precedence sentence (rejected — FR-005 needs the rule to explicitly yield to lane gates).

## R5. Error-handling matrix (owner-requested)

- **Decision**: the seven modes of plan.md's Error Handling table (E1–E7): partial ask-back reply → single targeted re-ask then stop; lane-gate precedence (probe counts it as pass); publish failure → old behavior stays live and probes require the served-DSL gate first; honesty-node non-interference (ask-backs carry no action claim — probe-verified); over-asking regression guarded by SC-002; secrets exclusion probe; stack-down probes abort on the health gate, never silently pass.
- **Rationale**: the owner asked for error handling explicitly; every mode maps to either steering text (E1/E6), probe design (E2/E4/E7), or process (E3/E5) — all verifiable, none speculative.
- **Alternatives considered**: treating errors as out of scope for a "prompt change" (rejected: the battery and probes need defined verdicts for these paths or they'd count failures as passes).
