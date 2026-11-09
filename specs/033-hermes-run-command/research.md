# Research: Hermes Run-Command Lane (spec 033)

Phase 0 output. Every decision below was evaluated against the live architecture verified in this session (the three sibling lanes in `server.py`/`hermes_client.py`, the 2026-11-09 fabrication + honesty-check work, the timing instrumentation, and the live WindowsMCP tool surface). No NEEDS CLARIFICATION items remain.

## D1. Request parsing: intent mapping, not literal-only

- **Decision**: The gate maps natural-language requests to at most one allowlisted command via a small, fixed synonym table plus literal command names — e.g. *"show my (current) IP address"* → `ipconfig`, *"what's running / running processes"* → `tasklist`, *"system info"* → `systeminfo`, *"host name"* → `hostname`, *"who am i"* → `whoami`, *"ping/reach <host>"* → `ping <host>`, *"dns lookup <host>"* → `nslookup <host>`, *"route/trace to <host>"* → `tracert <host>`. Unmapped requests get an ask-back that **offers the list**; the gate never guesses and never falls back to passing raw user text.
- **Rationale**: Story 1 is phrased in natural language; a literal-only parser would fail it on day one. The mapping is data (a constant table), testable as a matrix, and keeps every security decision in code.
- **Alternatives considered**: literal command matching only (rejected — fails the primary user story); letting the relay LLM choose the command from the allowlist (rejected — moves the security weight into a prompt, violating the spec's code-enforcement decision and Constitution IV's spirit).

## D2. Agent protocol: echo-and-attest, verified by the tool

- **Decision**: The directive to the agent is minimal and deterministic: run **exactly** the gated command, nothing else, and report `COMMAND: <exact command>` + the complete output in an `OUTPUT:` block + `TASK: COMPLETED`. The tool stamps `ok` only when (a) the attestation is present and (b) the echoed command matches the gated directive after normalization; a mismatch or missing marker is `error`, never a fabricated success.
- **Rationale**: Generalizes spec 029's FR-007 lesson (the `LAUNCH: SUCCESS` marker exists because the first probe stamped ok for a launch that never happened). The echo check additionally makes the agent layer structurally unable to claim a different command ran.
- **Alternatives considered**: trusting the agent's prose (rejected — same failure mode 029 hit live); running the command in the sidecar via WSL interop instead of the agent (rejected — a second execution pathway with different semantics; the agent pathway is the audited, consent-aware, single route).

## D3. Output relay: bounded verbatim, truncation named

- **Decision**: The tool envelope carries the real output up to ~4000 characters; longer output is truncated with the truncation named in the envelope itself. The relay targets the answering slice (e.g. IPv4 lines for an IP question) but never invents content.
- **Rationale**: Matches the existing `fetch_url` bound (4000 chars) already proven in chat; `tasklist`/`systeminfo` can exceed it; the user must always be able to tell the report was cut.
- **Alternatives considered**: unlimited relay (rejected — chat payloads and the ~300 s tool window); pre-filtering to "relevant" lines inside the tool (rejected — relevance is the relay's language job, and silent filtering hides truth).

## D4. Tool placement: fourth tool on the existing hermes_agent node

- **Decision**: `hermes_run_command` registers as a fourth MCP tool on the sidecar and joins the same `hermes_agent` chatflow node; the intent classifier's hermes class topic text gains diagnostics phrasing. No new classifier class, no new node.
- **Rationale**: The three existing lanes already share the node and the relay picks the tool per its instruction; a new class/node would duplicate routing for no gain. The MCP tool list flows to Dify via the established `sync-tools` path (27 → 28) and the publish cycle.
- **Alternatives considered**: a dedicated run-command agent node (rejected — duplicates the honesty-check wiring and node maintenance); routing through the launch tool's followup channel (rejected — spec 029 explicitly keeps launch shell-free).

## D5. Honesty coverage: extend the existing law + regex

- **Decision**: The DSL `hermes_agent` instruction's routing rules gain run-command bullets (which requests, refusal relay verbatim, one command per request) — the ANTI-FABRICATION LAW already speaks of `hermes_*` generically; the structural `honesty_check` node's `claims` regex gains `hermes_run_command` so an answer claiming a run without a tool call this turn is replaced.
- **Rationale**: The fabrication incident of 2026-11-09 (three fabricated "completed" answers with zero tool calls) is exactly one day old; the new lane must join both layers of the guard on day one.
- **Alternatives considered**: relying on the generic law alone (rejected — the regex is the structural layer that actually blocked the recorded fabrication).

## D6. Identity parameter: required in the tool schema

- **Decision**: `conversation_id` is a **required** parameter of `hermes_run_command` — the schema rejects calls without it. (Owner decision, clarify session 2026-11-09.)
- **Rationale**: Observed live this session: the launch lane's optional identity was omitted by the relay on a real turn, silently losing Stop-cancellability and the timing profile. Required-by-schema removes the relay's discretion; the office lane already uses this shape.
- **Alternatives considered**: optional + warning log (rejected — logging a degraded turn does not restore the Stop lever); optional + hardened prompt (rejected — the prompt already says "ALWAYS pass" and was still skipped once).

## Residual notes (no action needed for planning)

- The launch gate's refusal message gains one appended sentence pointing to the run-command lane (FR-008). Its pinning tests assert substrings, so an append is safe; the gate suite re-run is part of the task list.
- `ipconfig /all` and other flag forms stay refused (spec Assumptions) — a future spec amendment would add per-command safe-flag lists; nothing in this design blocks that.
- Timing parity is automatic: the stream path (`run_task_stream`) and `_await_with_keepalive` are shared with the other lanes; the audit entry rides the existing `write_attempt` (decision, `operation="run-command"`, duration_s, timing profile).
