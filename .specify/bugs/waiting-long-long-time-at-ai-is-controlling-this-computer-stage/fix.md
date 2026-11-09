# Bug Fix: Minutes-long wait at the "AI is controlling this computer" stage — documented-limit closure (no code change)

- **Slug**: `waiting-long-long-time-at-ai-is-controlling-this-computer-stage`
- **Fixed**: 2026-11-09
- **Assessment**: ./assessment.md
- **Status**: applied — the assessment's preferred remediation was itself a no-code closure ("no new fix in this cycle"); it was adopted exactly as proposed: accept the documented desktop latency floor, keep the two live mitigations, defer the structural fix to a spec

## Summary

No code was changed, per the assessment's own preferred remediation. The 2–5 minute waits on combined desktop turns are the documented latency floor (serialized LLM iterations × gated actions × consent idle-waits) already measured across three prior lifecycles, and this session's turns all completed with honest, screenshot-verified results — 38 s (split), 128 s, and 274 s (combined; the last typed the search, submitted, and read the weather card: 26°C Sunny, Hong Kong Observatory) with zero gateway warnings in the window. The interim mitigations were re-verified live and stay as-is; the only lever that makes combined turns fast is the deterministic sidecar executor, which is spec-sized work for the owner to schedule.

## Changes

| File | Change | Notes |
|------|--------|-------|
| *(none)* | — | No defect found at our layer; the assessment's "Files likely to change: None" held |

## Diff Highlights (optional)

*(none — no diff)*

## Tests Added or Updated

- None — per the assessment, the three live turns (38 s / 128 s / 274 s, all completing with honest verified results) are the evidence; there is no new code to pin down.

## Local Verification

- Commands run: none — no changed paths means no suites to exercise this cycle; a documented-limit closure introduces no regression surface.
- Verified live mitigations in the synced DSL `dify/AGIAssistant/AGI_Assistant.yml` (line 1370, `hermes_agent` instruction): the transport-error bullet carries the ~300 s window explanation and the split guidance ("first 'open <app>', then the typing/search followup as a separate message") — published 04:03 and demonstrated by the 04:04 split turn completing in 38 s.
- Manual checks (carried from the assessment's reconstruction, re-confirmed): the 274 s window's gateway log shows no warnings and no tool errors (inbound 12:24:07 → response ready 12:28:32); WindowsMCP state captures run 0.00–0.10 s (the 20–26 s UIA stalls have not recurred).

## Deviations from Assessment

- None. The remediation was applied exactly as proposed, including its "no new fix in this cycle" scope.

## Follow-ups

- Schedule the **deterministic sidecar executor** spec — the standing structural follow-up now backed by four lifecycles (a-little-bit-slow-to-create-email, completed-message-wait-long-time, desktop-followup-timeout-600s, and this one); it is the only change that makes combined desktop turns fast (~10–20 s target, no LLM in the mechanical loop).
- The perceived-slowness class will recur on every heavy combined desktop turn until that spec lands; the split-request guidance plus the honest ~300 s relay remain the interim mitigation.
- Mid-turn progress streaming into the chat stays architecturally blocked (Dify MCP tool calls are opaque) — do not re-litigate it as a bug.
- Consent idle-waits are user-safety behavior — not to be tuned down for speed.
- Fold this closure into the next lifecycle commit alongside the test phase.
