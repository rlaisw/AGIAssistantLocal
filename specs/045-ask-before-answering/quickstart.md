# Quickstart — 045-ask-before-answering

The runnable test plan. Prerequisites: stack up (`./startup.sh` all green), project venv (`.venv/bin/python`), the chatflow published with the new steering (implement order: unit tests red → DSL edit → publish → this guide).

## V0 — Unit pins (red → green)

```bash
.venv/bin/python -m pytest tests/unit/test_ask_before_answering.py -v
```
**Expected**: all pins green after the DSL edit (they were written and failed before it). Any red pin = the steering text drifted — fix the YAML, not the test.

## V1 — Ask-first acceptance battery (SC-001, 10/10)

Send 10 differently-phrased underspecified asks through the chat-API probe (the spec-044 pattern). Battery set: "back up my files" · "email John about the meeting" · "clean up my disk" · "what's the error in my log?" · "move my photos to the cloud" · "set a reminder for the team call" · "fix my printer" · "share the report with the team" · "which one should I buy?" · "help me set up the new server".
**Expected**: every first response asks a targeted question for the missing critical piece and performs no action/answer on an assumption. 10/10; a miss = investigate steering wording, republish, rerun — never silently retry.

## V2 — No-over-asking battery (SC-002, 10/10)

Send 10 complete, self-sufficient questions: "what is the capital of France" · "what does HTTP 418 mean" · "summarize the steps to back up a phone" · "back up C:\temp\reports to C:\temp\backup" · "open notepad" · "what's my current IP address" · "create a PowerPoint named test1 with a title slide saying Q4 review" · "how many CPU cores does the KB say the servers have" · "explain the difference between SSD and HDD" · "list the files in C:\temp".
**Expected**: every answer is direct, with zero clarifying questions. 10/10; an interrogation-style follow-up is a violation of FR-003, not acceptable "caution".

## V3 — Multi-turn coherence (SC-004, 3/3 threads)

For three V1 asks: after the ask-back, reply with the missing piece ("C:\temp\reports, to C:\temp\backup").
**Expected**: the next response answers or acts immediately — no re-ask of anything already answered or already in the conversation.

## V4 — Gates and secrets (FR-005, E2, E6)

1. Send a launch-ambiguity prompt ("open the app").
2. Send a request whose "missing info" would be a credential ("connect to the API — you need the key").
**Expected**: (1) the launch gate's own ask-back appears (which app?), with no double-ask; (2) the chat never asks for the key in conversation — it points to the configured location.

## V5 — E2E regression battery (SC-003)

```bash
.venv/bin/python -m agentic_rag_mcp.deploy verify
```
**Expected**: green including the new `ask-first` scenario; the existing lane scenarios (hermes-launch-app ask-backs, hermes-office-task, office-routing) unchanged — 0 double-asks, 0 regressions.

## Error-handling probes (from the plan's matrix)

- **E1 — partial reply**: reply to an ask-back with half the missing info. **Expected**: one targeted re-ask for only the still-missing piece; if still insufficient, the chat states exactly what it needs and stops asking (no loop).
- **E3 — publish gate**: before any probe session, confirm the served DSL carries the new rule (Postgres check, plan.md "Files to Change" §4). **Expected**: probes never run against a stale draft.
- **E4 — honesty-node non-interference**: after an ask-back, confirm the reply relays verbatim (an ask-back has no action claim, so the honesty_check replaces nothing).

## Full-suite gate

```bash
.venv/bin/python -m pytest tests/ -q
```
**Expected**: green, zero new failures (the 5 known live-stack-dependent pre-existing failures aside — compare against the pre-change baseline, not against zero).
