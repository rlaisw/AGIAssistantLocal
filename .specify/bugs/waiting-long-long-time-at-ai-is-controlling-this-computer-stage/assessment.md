# Bug Assessment: minutes-long wait at the "AI is controlling this computer" stage — the documented desktop latency floor, now with completion evidence

- **Slug**: `waiting-long-long-time-at-ai-is-controlling-this-computer-stage`
- **Created**: 2026-11-09T04:35+00:00
- **Source**: pasted text ("waiting long long time at AI is controlling this computer stage") + live reconstruction of the three recent turns
- **Verdict**: valid — the wait is real; but the root cause is the **documented desktop latency floor** (three prior lifecycles) plus the control notice's by-design per-action re-arming; no new mechanism found
- **Severity**: low — the turns **complete** with honest, screenshot-verified results (the 04:24 turn read the weather card: 26°C Sunny); the cost is minutes of perceived dead time with no chat feedback

## Report (verbatim or summarized)

> "waiting long long time at AI is controlling this computer stage"

## Symptom

During a combined "open Chrome + type the search" turn, the WindowsMCP control notice cycles repeatedly (re-arming on every gated action, each clearing ~3 s per spec 032) while the chat bubble shows nothing — the tool call is opaque, so no chunks stream until it returns. The user waits 2–5 minutes watching the desktop work with zero chat feedback. Expected: faster turns, or at least visible progress in the chat.

## Reproduction (reconstructed from the three recent turns, 2026-11-09 UTC)

1. 04:04:40 (38 s) — the split "open chrome" step after the split guidance: fast, clean
2. 04:18:56 (128 s) — combined request: completed — profile picker handled, query typed and confirmed on screen
3. 04:24:02 (**274 s**) — the same combined request again: completed — typed, submitted, and **read the weather card: 26°C Sunny, Hong Kong Observatory** — with the agent's honest note "the desktop-control gateway was flaky this session, so it verified the steps via screenshots instead"
4. Gateway log in the 274 s window: **no warnings, no tool errors** (inbound 12:24:07 → response ready 12:28:32) — the time is work, not failure; WindowsMCP state captures now take 0.00–0.10 s (the 20–26 s UIA stalls have not recurred)

## Suspected Code Paths

- The **documented latency floor**: serialized LLM iterations × many gated desktop actions × consent idle-waits (the user is at the machine, so gated actions wait for idle) — measured in three prior lifecycles (a-little-bit-slow, completed-message-wait, desktop-followup-timeout-600s); the structural fix (deterministic sidecar executor) is the standing follow-up
- The **control notice re-arming** — by design (WindowsMCP control policy: every gated action shows the notice); spec 032 already made each notice clear ~3 s after the action
- **No mid-tool streaming** — architectural: Dify's MCP tool calls are opaque; no chunks can reach the bubble while the tool runs. Not fixable at the prompt level.

## Root Cause Hypothesis

**High confidence, no new mechanism.** The wait is the desktop latency floor doing exactly what the prior lifecycles measured: an agent turn of ~10+ serialized LLM iterations, each with one or more gated desktop actions (notice re-arms each time, clears ~3 s), consent idle-waits while the user is active, plus Chrome's own startup and the profile picker. The turn is honest and correct — 274 s is within the 540 s envelope, and the result was verified on screen. The desktop-notice "stage" is simply the only visible activity signal the user gets while the opaque tool call runs.

## Proposed Remediation

**Preferred**: no new fix in this cycle — this is the known floor with completion evidence. Two levers already exist and both were visible in this session: (1) the **split-request guidance** (published 04:03) — the 38 s split step demonstrates it works; (2) the **deterministic sidecar executor** (the standing structural follow-up from three prior lifecycles) — the only change that makes the combined turns fast; it is spec-sized work for the owner to schedule.

**Alternatives**:
- Mid-turn progress streaming into the chat — architecturally blocked (opaque MCP tool calls); a WindowsMCP→UI progress channel would be new infrastructure, not a bug fix
- Suppress the notice between actions — rejected: it is the safety indicator, and spec 032 (3-second clear) is the owner-approved balance

**Files likely to change**:
- None in this cycle (no defect found at our layer)

**Tests to add or update**:
- None — the three turns above are the evidence: 38 s (split), 128 s, 274 s (combined), all completing with honest verified results

## Risks & Considerations

- The perceived-slowness class will recur on every heavy combined desktop turn until the deterministic executor exists; the split guidance and the honest relay (with the ~300 s explanation, published 04:03) are the interim mitigation
- The "flaky gateway" note in the 274 s turn was the agent's caution about screenshot-vs-control verification, not a logged failure — screenshot verification is by design an acceptable fallback and it worked (the temperature was read correctly)
- Consent idle-waits are user-safety behavior — not to be tuned down for speed

## Open Questions

- [NEEDS CLARIFICATION: none blocking — if the owner wants the combined turns fast, the next step is scheduling the deterministic-executor spec, not another bug hunt]
