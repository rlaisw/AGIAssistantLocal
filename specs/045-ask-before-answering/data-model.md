# Data Model — 045-ask-before-answering

No new storage entities: the feature is a steering rule plus its test scaffolding. The persisted artifacts are prompt text in the chatflow DSL, a unit-test file, and a battery scenario.

## Steering rule (the new "entity")

| Field | Value | Notes |
|---|---|---|
| headline | "Before answering the user's question, ask for any critical missing information." | owner's sentence, verbatim |
| critical_definition | info without which the answer/action materially changes, becomes unsafe, or is meaningless | the load-bearing qualifier; agent-judged, behavior-measured |
| first_response | targeted, minimal question (or minimal set) for exactly the missing pieces | before any answer or action; never invents the info (anti-fabrication) |
| no_over_asking | complete questions answer directly; systematic interrogation is a violation | pinned by the direct-answer battery (SC-002) |
| no_re_ask | info already in the conversation (earlier turns, attachments) is known | includes spec-043 attachment content |
| secrets_exclusion | never request passwords/API keys as missing info; point to the configured location | probe-verified |
| lane_gate_precedence | launch ambiguity, Office unsaved-changes, email confirmation stay authoritative | no double-ask; gate ask-backs count as valid in probes |
| binding_sites | both Agentic-Strategy system prompts in `dify/AGIAssistant/AGI_Assistant.yml` | ×2 surfaces per node, appended rule block |

## Unit-test pin set (new file `tests/unit/test_ask_before_answering.py`)

| Pin | Assertion | Why it exists |
|---|---|---|
| directive presence | headline sentence in both strategy prompts | the rule itself; catches console reverts / merge drift |
| critical definition | the qualifier clause in both prompts | prevents the rule degrading into always-ask |
| no-over-asking clause | present in both prompts | FR-003's textual anchor |
| no-re-ask clause | present in both prompts | FR-004's textual anchor |
| secrets exclusion | present in both prompts | E6's textual anchor |
| load order | YAML parses; the file's known anchors still resolve | guards against scalar-formatting accidents |

All pins are red before the DSL edit and green after it (tests-first, Constitution II).

## Battery scenario (new `scenario_ask_first` in `src/agentic_rag_mcp/deploy/battery.py`)

| Probe | Input class | Expected verdict |
|---|---|---|
| P1 | underspecified actionable ask ("back up my files") | ask-back in the answer; no tool action |
| P2 | complete question ("what is the capital of France") | direct answer; no clarifying question |
| P3 | launch-ambiguity phrasing (lane-gate territory) | the gate's own ask-back appears; no double-ask |

Registered alongside `office-routing` and `chat-journey`; runs on every `deploy verify`.

## Unchanged entities (explicitly)

Lane gates (launch ambiguity, Office unsaved-changes, email confirmation), the honesty_check and dispatch-leak nodes, the anti-fabrication law, specs 043/044 steering (attachments routing, infographic default), and every tool schema.
