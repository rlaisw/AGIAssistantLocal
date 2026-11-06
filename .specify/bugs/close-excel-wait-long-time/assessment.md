# Bug Assessment: close-Excel took 3 minutes — Dify's ~120 s tool-call deadline cuts slow office turns' streams; the work completes anyway and gets redone

- **Slug**: `close-excel-wait-long-time`
- **Created**: 2026-11-06T05:45+00:00
- **Source**: pasted text (chat transcript of "save the file then close Excel" + "close Excel wait long time")
- **Verdict**: valid — measured end-to-end; the recovery behavior is correct, the latency and the stream cut are the defects
- **Severity**: medium — every office turn that runs ≥ ~120 s risks a user-visible transport error plus a full idempotent redo, doubling the wait; the lane's turns now routinely brush that line

## Report (verbatim or summarized)

> "close Excel wait long time"

The user asked to save and close Excel. Attempt 1 died with a transport error ("peer closed connection without sending complete message body (incomplete chunked read)"); the agent retried and the retry completed: file saved, workbook closed, Excel fully quit (0 EXCEL.EXE), file verified on disk. Total visible wait ≈ 3 minutes. The transcript footer also shows "Deepseek-v4.1-flash" — investigated below (cosmetic).

## Symptom

A save-and-close request takes ~3 minutes because (a) the first attempt's response stream is cut by a Dify-side tool-call deadline of ~120 s while the sidecar is still working, and (b) the agent's retry then re-executes the whole task idempotently — correct, but the user waits twice. Expected: one turn, ~1–2 minutes, no transport error.

## Reproduction (measured from Dify DB + audit, 2026-11-06 UTC)

1. 05:29:54 — the user's message; attempt 1 runs (attach → save → close → quit, 4 audited steps)
2. **05:32:03 — attempt 1's audit completes server-side: save OK, close OK, "Quit Excel OK … verified 8s later: no EXCEL.EXE"** — the work SUCCEEDED; but **129 s** had elapsed since the message, and the Dify plugin's response read was already dead ("incomplete chunked read") — the ~120 s tool-call deadline cut the stream before the sidecar's response arrived
3. 05:33:01 — the agent's retry: idempotent re-verification and redo (workbook already closed → dispatch, save (already-saved), close, quit again), all audited, 0 processes verified — done at 05:33:03
4. Contrast: the preceding Excel-create turn (05:28:33→05:29:39, ~66 s) finished under the deadline — no cut
5. Secondary finding: the chat footer says "Deepseek-v4.1-flash" while the **live published lane is kimi-k3** (verified in the Dify DB workflow graph; the DSL pin holds) — the UI's model badge fell back to its default (a `/api/models/current` read quirk), a cosmetic lie worth fixing

## Suspected Code Paths

- Dify agent-strategy / MCP-plugin tool-call deadline (~120 s, measured empirically): the langgenius/agent function_calling strategy or the MCP plugin client's read timeout — no env knob exists (`docker-plugin_daemon-1` / `docker-api-1` env have no tool-timeout settings; `MAX_TOOLS_NUM` is unrelated)
- `src/agentic_rag_mcp/hermes_client.py` — STEP BATCHING adherence is the other half: the close task ran 4 separate steps (129 s); a single batched script would have finished under the deadline
- `ai-chat-landing/app/api/models/current/route.ts` — the model-badge fallback that reports Deepseek when the DSL read fails while the lane is actually kimi-k3

## Root Cause Hypothesis

**High confidence on the mechanism, medium on the exact code location.** Dify imposes a ~120 s deadline on agent-node tool invocations; the office lane's modern turns (LLM hops + direct-channel overhead + Excel quit settle-times) now routinely take 60–150 s, so any turn crossing the line gets its stream cut mid-body even though the sidecar finishes the work honestly (the audit proves completion). The Dify agent then retries the task per its error handling — which is correct and idempotent, but doubles the user's wait. The 129 s duration itself traces to loose batching adherence (4 LLM hops for work that fits one script).

## Proposed Remediation

**Preferred**: two-sided. (1) **Raise the tool-call deadline** for the office lane — locate the ~120 s constant (langgenius/agent strategy code or the MCP plugin client) and raise it to ≥ 300 s, either by patching the plugin in place (the plugins live as local files under `plugin_daemon/cwd/…`) or by a Dify env if one exists after source inspection; this removes the cut for all legitimate slow turns. (2) **Tighten turn duration**: reinforce the STEP BATCHING rule for close/save tasks (close+save+quit is one script) so typical turns stay well under the deadline. Additionally (3) fix the `/api/models/current` fallback so the badge shows the pinned kimi-k3 instead of defaulting to Deepseek.

**Alternatives**:
- Reduce the sidecar's own work instead (deeper batching in the executor) — necessary but insufficient: legitimately slow operations (big files, Excel quit settle, Outlook restarts) will always sometimes exceed 120 s
- Split office tasks into sub-invocations under 120 s each — rejected: more LLM hops, more latency, and the cut risk just moves

**Files likely to change**:
- The langgenius/agent plugin's strategy timeout (local plugin files) or a Dify configuration — exact location to be pinned in the fix phase
- `src/agentic_rag_mcp/hermes_client.py` — close/save batching reinforcement (small)
- `ai-chat-landing/app/api/models/current/route.ts` — badge fallback fix (small)

**Tests to add or update**:
- Instruction guard for the close/save batching phrase
- (Badge route: a unit test if the route's fallback logic is testable — depends on the route's current shape)

## Risks & Considerations

- Patching the Dify plugin in place adds local drift (already a known pattern in this deployment: hermes-agent and OfficeMCP carry local patches) — record it in DEPLOY.md if done
- A higher deadline means genuinely-hung tool calls block the agent node longer — the sidecar's own 600 s Hermes budget remains the real backstop, so ≥ 300 s but < 600 s is the right window
- The idempotent retry that saved this turn must keep working — the close flow's already-closed handling (dispatch → save → close → quit on a closed workbook) was verified correct this turn
- The badge fix is cosmetic but user-facing: a wrong model label invites exactly the confusion seen yesterday (the fabrication bug's root was deepseek-in-the-lane)

## Open Questions

- [NEEDS CLARIFICATION: the exact Dify code location of the ~120 s deadline — strategy constant vs plugin client timeout; the fix phase must pin it before choosing the patch surface]
- The user's turn also coincided with a workflow version row created at 05:05:40 (a Dify draft-save or an unprompted publish — benign, but note who/what touched the console if it recurs)
