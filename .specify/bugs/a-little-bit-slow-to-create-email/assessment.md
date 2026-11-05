# Bug Assessment: email compose takes 2–3 minutes — nested LLM agent loop latency, not the Office work

- **Slug**: `a-little-bit-slow-to-create-email`
- **Created**: 2026-11-05T09:58+00:00
- **Source**: pasted text ("a little bit slow it require 2-3 minutes to cretae an email" + the successful O365 compose transcript)
- **Verdict**: valid — a performance defect on a now-correct flow
- **Severity**: low — the lane works end-to-end; this is UX latency

## Report (verbatim or summarized)

> "a little bit slow it require 2-3 minutes to cretae an email"

The user's O365 email compose completed correctly (draft composed, verified, displayed, never sent — the transcript shows a clean `TASK: COMPLETED`), but the turn took 2–3 minutes.

## Symptom

A well-formed email compose that previously took seconds of mechanical work now takes 2–3 minutes wall-clock. Expected: tens of seconds for the Office operations; the minutes are spent in nested LLM agent loops and the mandated multi-step protocol.

## Reproduction (measured, 2026-11-05)

1. The user's O365 turn (audit 09:50:38): check-running-apps → strip detection (3 default echoes → **direct channel**, per the codified rule) → compose → verify → display — completed cleanly; the direct channel carried the work while the gateway channel was stripped
2. Instrumented sidecar probes the same morning: healthy-phase compose **84 s**, stripped-phase (via direct channel) **89 s** — tool-internal time; the user-visible 2–3 min adds the Dify-layer agent hop(s) and chat streaming
3. `OFFICE_INSTRUCTIONS` is now ~5,800 chars ≈ **1,445 tokens**, sent at **every iteration** of the gateway agent's loop; a standard compose runs ~5–7 LLM round trips (probe, canary/strip detection, compose, verify-readback, display/report) — at ~15–25 s per kimi-k3 hop with the grown context, that is the entire latency budget
4. The Office COM work itself is seconds (attach + CreateItem + Save + read-back)

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_client.py` — `OFFICE_INSTRUCTIONS`: the step protocol mandates one agent iteration per mechanical step (each an LLM round trip), and the accumulated rules (session-degradation, launch guard, attach-failure protocol, window dedup, direct channel) have grown the per-hop context
- The gateway agent loop (upstream hermes-agent) — LLM-per-step architecture: every STEP is one model call plus a tool call
- The Dify `hermes_agent` node — an additional LLM hop before the sidecar tool call

## Root Cause Hypothesis

**High confidence.** The latency is architectural: two nested LLM agent layers (Dify agent node → gateway agent), each multiplying per-hop model latency (~15–25 s) by the number of mandated steps (~5–7), with an instruction context that grew by ~50% during today's rule additions. The mechanical Office work is seconds. There is no hang, no retry storm, and no channel degradation cost in the observed turn (the direct channel switch itself added only ~3 canary echoes' worth of time).

## Proposed Remediation

**Preferred**: cut LLM hops by batching the mechanical steps. Add an instruction: for a **well-formed single-app task** (a compose, a save, a read), execute ONE combined RunPython script that performs the whole flow — probe (process/attach), the operation, and the read-back verification — in a single execution, and report the sub-results as one STEP block. That converts ~5–7 iterations into ~2 (detect-channel → combined-exec) and should roughly halve the tool-internal time (84 s → ~40 s, and the user-visible turn proportionally). Keep the mandated multi-STEP form only where user consent gates a step (email send-confirmation, restart Outlook) or where a step's failure must not block the honest report.

**Alternatives**:
- Instruction slimming (consolidate the rule text without losing semantics) — worthwhile but risky to regressions; every rule today exists because of a live incident; do it only as part of the batching change, not separately
- The deterministic sidecar executor (no gateway LLM loop for well-formed tasks, ~10–20 s) — the durable architectural fix and the natural next spec; too large for this bug's scope, note as follow-up

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_client.py` — the batching instruction
- `tests/unit/test_hermes_office_tool.py` — guard for the batching rule

**Tests to add or update**:
- Guard test: instructions contain the combined-execution rule and the consent-gate exceptions

## Risks & Considerations

- Batching reduces per-step audit granularity: the sidecar's STEP-parsed audit loses intermediate steps unless the combined script's output is reported in a parseable form — the rule should require the one STEP block to name every sub- operation and its outcome
- A single big script fails atomically: a mid-script failure loses the per-step honest report; the rule must require the script to catch and report sub-step failures verbatim
- The direct-channel detection must stay OUTSIDE the batch (it chooses the transport); only the Office-side steps batch
- Two LLM layers remain even after batching — the durable fix is the deterministic executor (follow-up)

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the measurements are sufficient for the fix; the follow-up executor spec will need owner prioritization]
