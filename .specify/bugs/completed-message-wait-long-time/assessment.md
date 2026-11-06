# Bug Assessment: 3 s of COM work took 109 s wall-clock — per-task channel-detection tax + nested-LLM overhead

- **Slug**: `completed-message-wait-long-time`
- **Created**: 2026-11-06T07:10+00:00
- **Source**: pasted text ("file saved and closed office app. but the task completed message wait a long time" + the successful save/close transcript)
- **Verdict**: valid — same performance class as `a-little-bit-slow-to-create-email`, now with sharper data: the mechanical work is seconds and the wait is almost entirely nested-LLM overhead plus a per-task detection tax
- **Severity**: low — correct results, honest reporting, no errors; a UX-latency complaint on a working flow

## Report (verbatim or summarized)

> "file saved and closed ofice app. but the task completed message wait a long time"

The user asked "save the file and close excel app"; the file was saved (read-back verified), the workbook closed, Excel quit (WMI-verified 0 processes) — but the final completed answer took a long time to arrive.

## Symptom

A save-and-close request whose actual Office work takes ~3 seconds takes ~109 seconds wall-clock from send to answer. Expected: tens of seconds.

## Reproduction (measured, 2026-11-06 UTC)

1. 07:04:05 — the user's message; answer completed at 07:05:54 (**109 s**)
2. 07:05:52 — the tool's audit: STEP 1 **"Channel recovery OK — the gateway RunPython channel was in the stripped state… all execution steps were switched to the direct OfficeMCP channel"** → STEP 2 attach + save + close (the real work: seconds) → STEP 3 quit-verify (0 EXCEL.EXE)
3. So the ~109 s breaks down as: Dify agent hop + gateway agent loop (kimi-k3, several iterations) + **the channel-detection tax paid AGAIN in this task** — 2+ canaries over the stripped gateway + direct-SSE session setup + the LLM narrating the recovery — even though the immediately preceding tasks in the same conversation (07:02:10 create, 06:59:25, 06:55:49 save/close PPT) had each already discovered the strip
4. The STRIP MEMORY rule added yesterday dedupes detection **within** a task but not **across** tasks in the same conversation — every new task re-pays ~30–60 s of detection + recovery narration while the upstream strip (hermes-agent #148459) remains permanently active

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_client.py` — `OFFICE_INSTRUCTIONS` STRIP MEMORY: scoped per-task; the strip has been continuously active for over a day, so per-task detection is pure repeated cost on every turn
- The nested-LLM architecture (Dify hermes_agent node + the gateway agent loop) — the dominant remaining latency; already documented as the deterministic-executor follow-up in three prior lifecycles
- OfficeMCP direct channel setup — the SSE handshake per task is seconds, not the main cost, but re-avoidable

## Root Cause Hypothesis

**High confidence.** With batching done and stream cuts fixed, the remaining wait is (a) the per-task detection/recovery cycle (~30–60 s per turn while the strip persists — re-discovering the same permanently-stripped gateway every task and narrating the recovery through LLM hops), and (b) the irreducible nested-LLM loop time (Dify hop + several kimi-k3 iterations at ~15–30 s each carrying the now-large instruction set). The COM work itself is negligible.

## Proposed Remediation

**Preferred**: make the strip sticky at the conversation level. The sidecar tracks office conversation state (`office_state.py` — active documents, pending drafts); add a **channel-state entry**: when any task in a conversation finds the gateway channel stripped, record it with a timestamp; the task directive tells the agent "the gateway channel is known-stripped in this conversation (found at HH:MM) — skip gateway canaries entirely and go straight to the direct channel; only re-probe the gateway if the direct channel fails." This removes the detection tax from every follow-on task (the common case in a working session) without trusting a stale cache blindly — the direct channel is the operative path and its failure is the real backstop. Expected saving: 30–60 s per follow-on turn; the save+close class should land near 50–60 s wall-clock.

**Alternatives**:
- The deterministic executor (no LLM in the mechanical loop, ~10–20 s guaranteed) — the structural fix already recommended in three lifecycles; a spec-sized effort the owner should schedule; this assessment adds the strongest data point yet: **3 s of work paying 109 s**
- Reduce the instruction set size (consolidate the accumulated rules) — shaves per-hop tokens but risks regressing the honesty rules; defer

**Files likely to change**:
- `src/agentic_rag_mcp/office_state.py` — channel-state entry (stripped-at timestamp)
- `src/agentic_rag_mcp/server.py` — the office tool passes the known-stripped hint into the directive (where `directive_ctx` is built)
- `tests/unit/test_hermes_office_tool.py` — guards

**Tests to add or update**:
- Unit: a second task in a conversation whose state says "stripped" receives the skip-detection directive; a first task does not
- Guard: the instruction text mentions the sticky hint consumption

## Risks & Considerations

- If the gateway channel heals upstream (#148459 fixed), a stale sticky hint would send the agent to the direct channel unnecessarily — harmless (the direct channel works always) and self-correcting (the hint is per-conversation, TTL'd or cleared on direct-channel failure)
- The hint must never suppress detection when the direct channel is the one failing — the backstop ordering matters
- This does not remove the nested-LLM floor (~40–60 s); only the executor does — set expectations accordingly
- The upstream strip is now over a day old; permanent direct-channel operation is the de facto architecture — worth stating in DEPLOY.md

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the state-entry design is conventional; the executor spec timing is the owner's call]
