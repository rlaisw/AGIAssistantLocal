# Bug Assessment: "the launch request failed while communicating with the local agent" — the documented ~300 s chat ceiling hit on a natural weather search; the recovery hint can be made actionable

- **Slug**: `the-launch-request-failed-while-communicating-with-the-local-agent-on-your-pc`
- **Created**: 2026-11-09T04:05+00:00
- **Source**: pasted text (the agent's honest relay of a launch transport failure on "help to open chrome browser, type hong kong temperature today at search bar…")
- **Verdict**: valid — a **recurrence of the documented known limit** (`the-local-agent-hit-a-transport-error`, closed 2026-11-09 after every configurable knob was raised): the turn's tool call ran **306 s wall (cut at exactly 299.2 s of stream time: POST 03:53:28.946 → Terminating 03:58:28.161)** — the Dify plugin-daemon's hardcoded ~300 s invocation ceiling. The failure is honest end-to-end; what's improvable is the **recovery hint's actionability**.
- **Severity**: low — the failure mode is truthful (accurate relay, no retry, no fabrication, no silent kill); the UX cost is one wasted multi-minute turn and a generic re-ask instead of a concrete fix.

## Report (verbatim or summarized)

> "Sorry — the launch request failed while communicating with the local agent on your PC (the connection dropped before Chrome could be started, so nothing was opened or typed). To recover, please just ask again…"

The agent relayed the transport error per the no-retry rule (correct), gave an honest re-ask hint, and even added a truthful capability note ("even once it works, I can't read the temperature result back from the browser").

## Symptom

A natural one-message request — "open Chrome, type hong kong temperature today at the search bar" — runs longer than the chat's ~300 s tool window and ends in the honest transport-error relay instead of a result. Expected: either the result or a recovery hint that actually prevents a repeat (the same request will fail the same way every time).

## Reproduction (measured, 2026-11-09 UTC)

1. 03:53:24 — the request ("help to open chrome browser , type hong kong temperature today at search bar…"); the agent passed the full task + conversation_id (the cycle-2 wiring visible and working)
2. The tool stream lived **exactly 299.2 s** (sidecar: POST 03:53:28.946 → Terminating 03:58:28.161) — the signature of the Dify plugin-daemon ceiling, not a blip
3. 03:58:30 — the honest relay; turn `normal`, no retry (correct), re-ask hint given
4. Identical requests completed in the past only when their tool work fit under ~300 s (the Nov 8 weather turn ran ~400 s wall but its tool calls fit); this one's desktop work (Chrome cold-ish start + gated typing + slow 20–26 s UIA captures across iterations) does not

## Suspected Code Paths

- The known limit: the Dify plugin-daemon's compiled ~300 s tool-invocation ceiling — **not re-openable by configuration** (five knobs raised and verified live in the closed lifecycle; the constant survives all of them)
- `dify/AGIAssistant/AGI_Assistant.yml` (`hermes_agent` node prompt) — the transport-error bullet: "Relay the failure to the user honestly… and let the user re-ask" — the relay is correct but **the hint never says WHY it will fail again or how to avoid it** (split the request). This is the one lever still in our control.
- The desktop latency floor (WindowsMCP UIA captures) — the reason this task class exceeds the window; the deterministic-executor follow-up remains the structural fix, out of scope here.

## Root Cause Hypothesis

**High confidence, no new mechanism.** This is the documented ceiling behaving exactly as the closed lifecycle predicted: a launch+typing followup whose gateway work exceeds ~300 s is cut mid-stream; the sidecar (whose own envelope is 540 s) never sees the cut — the Dify-side plugin client does, and the agent relays it honestly. The single actionable gap: the recovery guidance tells the user to "ask again", but re-asking the same combined request guarantees a repeat; the known working posture (split: "open chrome", then "type hong kong temperature today") is never surfaced to the user at the moment it's needed.

## Proposed Remediation

**Preferred**: one prompt-bullet amendment (published via the export→patch→publish console path, same as every prior prompt cycle): extend the transport-error rule with the split guidance — *"When you relay this transport failure, also tell the user why it recurs and how to avoid it: the chat's tool window is roughly 300 seconds, and multi-step desktop tasks that exceed it will always cut; suggest splitting — first 'open <app>', then the typing/search followup as a separate message — which also matches each tool's one-attempt-per-turn contract."* No code changes; the agent already relays honestly, it just needs the concrete remedy to hand the user.

**Alternatives**:
- Detect the ~300 s cut shape in the sidecar and rewrite the error text — not possible: the sidecar never sees the Dify-side cut (its own call continues to 540 s)
- The deterministic executor (the structural fix for the latency floor) — the standing follow-up; still the endgame, unchanged by this cycle

**Files likely to change**:
- Live Dify workflow (`hermes_agent` node prompt) + `dify/AGIAssistant/AGI_Assistant.yml` (synced)

**Tests to add or update**:
- Live-graph assertion after publish (the same `graph::text LIKE` check used in every prior prompt cycle)
- Behavioral: the next >300 s desktop turn's relay should contain the split suggestion (natural sample)

## Risks & Considerations

- Prompt-only change; no tool, count, or model changes; publish via the pinned cycle (prompt-only, no model delta)
- The hint must not promise the split always works — heavy followups can still exceed the window individually (each split step must still fit ~300 s)
- The ceiling itself stays open upstream (the evidence file for the Dify plugin-daemon issue is ready to file — the PAT's write scope blocked posting from here)

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the mechanism is fully understood; the amendment is one sentence in an existing rule the agent already obeys]
