# Bug Assessment: honesty check dead-ends legitimate requests — kimi's no-emit flake plus an over-broad regex matching tool names in reasoning text

- **Slug**: `the-local-agent-was-not-called-for-this-request`
- **Created**: 2026-11-09T09:15+00:00
- **Source**: pasted text (the user's chat transcript: two requests, each answered with the honesty-check block notice, repeatedly)
- **Verdict**: valid — two real defects at our layer (an over-broad honesty regex that fires on tool names **mentioned in reasoning text**, and a dead-end block message), triggered by an underlying model defect (kimi-k3 intending a tool call, narrating the intent, but emitting no call). The same conversation proves the lane itself works: the two asks before these failed for real.
- **Severity**: medium — user-visible dead-end loop on legitimate requests; the regex over-match will misfire increasingly as tools get discussed in honest drafts; no data risk (nothing ran — the guard still prevents false "done"s).

## Report (verbatim or summarized)

> "show my system locale setting" → **Honesty check: the local agent was NOT called for this request, so nothing was done on your computer. The drafted reply described actions that never ran and was blocked by the honesty check. Please send the request again.**
>
> "check my hard disk disk spaces" → the same notice, three times in a row (user re-sent per the message's advice and hit the same wall each time).

## Symptom

A user asks for a system-state lookup (locale, disk space); the relay intends to call `hermes_run_command` (its stored reasoning says so), says "I'll check that for you", but **emits no tool call**; the honesty check then replaces the answer with its block notice, and re-sending repeats the loop. Expected: either the command runs, or the user gets an honest, actionable answer (the gate's ask-back with the allowlist — `systeminfo` even *contains* the locale lines).

## Reproduction (forensically reconstructed, conversation `e4a98f05`, 2026-11-09)

1. 09:02:48 "show my Windows current IP address" → **real** `ipconfig` (audit `executed run-command` 09:04:21) ✓
2. 09:05:05 "what is my computer name" → **real** `hostname` → `A301-11120` (audit `executed` 09:07:02, 113.6 s) ✓
3. 09:07:13 "show my system locale setting" → agent node: 3 iteration items, `tool_responses: []`, reasoning ends *"Let me call hermes_run_command with task … and conversation_id …"* → **no call emitted**; the honesty check matched and replaced the draft. No audit row (sidecar never contacted).
4. 09:08:01 "check my hard disk disk spaces" → same shape; reasoning even notes *"the previous turn was blocked by an honesty check because no tool was called. I must call the tool in this turn."* → still **no call emitted**; blocked again. User re-sent (per their pasted transcript) — the loop repeats.

## Suspected Code Paths

- `dify/AGIAssistant/AGI_Assistant.yml` — the `honesty_check` code node's `claims` regex: the bare tool-name alternation `hermes_(launch_app|office_task|file_task|cancel_turn|run_command)` matches the tool name **anywhere in the text**, and the `answer` input includes kimi-k3's thinking preamble (which legitimately says "Let me call hermes_run_command…"). The regex was built for *claimed completions*; it fires on *mentioned intentions*.
- The `hermes_agent` instruction — the anti-fabrication law drives the model to *say* it will call the tool, but nothing enforces *emitting* the call in the same response.
- `src/agentic_rag_mcp/hermes_run_gate.py` — the intent map has no "system locale" phrase, even though `systeminfo` output contains the System Locale / Input Locale lines (a user need one ask away from being served); disk space is genuinely uncovered (any amendment is spec territory, not this bug).
- kimi-k3's function-calling (upstream, not ours): intermittent no-emit — the same single-generation failure family as the fabrication bug, manifesting as narrated-intent-without-call instead of narrated-completion.

## Root Cause Hypothesis

**High confidence, two layers.** (1) The honesty check's `claims` pattern includes the bare tool names, and it tests the full agent text — thinking preamble included — so any draft whose *reasoning* mentions a tool (which the anti-fabrication law actively encourages) with no call that turn gets replaced, honest or not. (2) The underlying trigger is kimi-k3's no-emit flake: the model decides to call, narrates "I'll check that for you", and ends the generation without the tool-call structure — the identical conversation succeeded twice (ip, hostname) before failing twice, so it is intermittent model behavior, not a routing or schema problem (the successful calls prove the required-parameter contract works). The block message's advice ("please send the request again") cannot fix a model flake, producing the user's loop.

## Proposed Remediation

**Preferred** — three small pieces, one publish cycle:

1. **Honesty-check precision** (code node JS): strip the thinking preamble before testing — kimi-k3 separates thought from answer with a `\n---\n` line, so evaluate only the visible answer (the text after the last separator); and drop the bare tool-name alternation from `claims` (the recorded fabrications all matched via the completion patterns — "local agent completed", "the agent sent/typed/…", "confirmed by a snapshot", "LAUNCH: SUCCESS" — which stay). Honest drafts that merely discuss tools stop being false-accused; the three recorded fabrications still block (verify with the node harness).
2. **Actionable block message**: when the check does fire, tell the user what works, not just "send again" — e.g. "nothing was done on your computer; try asking for a specific allowed command: 'show system info' (its output includes the system locale), 'list running processes', 'ping <host>'." A blocked user gets a path that works instead of a loop.
3. **Prompt hardening + one intent-mapped need**: a DSL bullet — "When you decide to call a tool, emit the actual tool call in the SAME response; never end a turn with only 'I'll check …' text" — plus a gate synonym mapping "system locale" → `systeminfo` (the output contains it), so the exact reported ask succeeds next time. Disk space stays honestly ask-back (uncovered; a future spec amendment could add a read-only volume command).

**Alternatives**:
- Auto-retry the agent node on no-call turns — Dify's agent loop has no such primitive (iterations advance only on tool calls); rejected as unsupported topology surgery.
- Block the "I'll check…" dangling drafts too (widen the regex to intent phrasing) — rejected: it re-creates the false-positive surface and censors legitimate ask-backs; the original design rule stands (replace only on *claimed action*).

**Files likely to change**:
- `dify/AGIAssistant/AGI_Assistant.yml` (honesty_check code + hermes_agent instruction bullet)
- `src/agentic_rag_mcp/hermes_run_gate.py` (locale→systeminfo phrase)
- `tests/unit/test_hermes_run_gate.py` (locale mapping case)
- `/tmp`-style node harness re-validation against the five recorded drafts (3 fabrications block; the 2 honest no-emit drafts pass through after the fix)

**Tests to add or update**:
- Gate: `"show my system locale setting"` → ok `systeminfo`.
- Honesty harness: the three recorded fabricated drafts still BLOCK; the two 09:07/09:08 drafts (tool name only in reasoning, visible text "I'll check that for you.") no longer match after the fix.

## Risks & Considerations

- Stripping the thinking preamble is keying on kimi-k3's `\n---\n` output shape; if the model changes format, the strip falls back to testing the full text (safe direction: over-block, not under-block). Code comment should note the fallback.
- Dropping the tool-name alternation slightly narrows the fabrication net; the remaining patterns are the ones that caught every recorded fabrication, and the structural half (no call ⇒ nothing claims action) is unchanged.
- The no-emit flake itself is upstream model behavior — this fix stops the guard from compounding it into a user-visible dead-end, but occasional "I'll check…" dangling answers may still occur (honest, no false claims; the actionable message path covers the user).
- `systeminfo` is a ~10 s, verbose output — the relay targets the locale lines per the existing "target the slice" rule.
- The publish cycle must re-verify the honesty regex change against the Postgres graph (established method).

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the one policy choice is whether a no-call draft saying only "I'll check that for you." should pass through (default: yes, per the replace-only-on-claimed-action design rule) or be replaced with the actionable notice; the default keeps the guard precise.]
