# Bug Assessment: Agent-side retry escapes the 540 s honest envelope — attempt + retry exceeds the daemon's 600 s window and the turn dies silently again

- **Slug**: `it-is-a-transport-failure-let-me-try-again-once-since-it-may-be-transient`
- **Created**: 2026-11-08T09:20+00:00
- **Source**: pasted text (the agent's reasoning quote "it's a transport failure. Let me try again once, since it may be transient.") + live investigation
- **Verdict**: valid — a new layer the 540 s envelope (`desktop-followup-timeout-600s`) does not cover
- **Severity**: medium — the silent-kill failure mode is back for a different reason: single attempts are honest, but a retried turn still dies mid-flight with no verdict and no audit

## Report (verbatim or summarized)

> "it's a transport failure. Let me try again once, since it may be transient."

The user re-sent "open windows control panel , display my network adapter" in the chat at 09:00:31. The Dify agent's first tool attempt hit a transport failure; the agent judged it transient and **retried within the same turn**; the cumulative time exceeded the plugin-daemon's ~600 s window and the workflow run was killed (`PluginDaemonInternalServerError: killed by timeout`, elapsed 603.3 s) — empty answer, **no audit entry** for the turn.

## Symptom

A launch-followup turn that includes an agent-side retry dies silently at the daemon's ~600 s window — no verdict, no audit — even though each individual tool attempt is honestly bounded at 540 s. Expected: the turn ends with an honest verdict from the first attempt's error, leaving re-asking to the user.

## Reproduction (evidenced, 2026-11-08 UTC)

1. 08:47–08:56 — the 540 s envelope **verified working on single attempts**: the identical request through the sidecar returned the honest verdict + audit entry at exactly 540 s (fix phase of `desktop-followup-timeout-600s`)
2. 09:00:31 — the user's chat turn (same request): workflow run `failed` at **603.3 s** (`PluginDaemonInternalServerError: killed by timeout`), message `status=error` with an **empty answer**; last audit entry is 08:58:57 (an earlier, unrelated launch) — **the turn left no verdict trail**
3. The pasted reasoning shows why: first attempt → transport failure → agent retried once → the retry's runtime stacked on the first attempt's runtime → the daemon's window expired mid-retry. The envelope bounds *each invocation* (540 s); the daemon bounds the *whole workflow run* (~600 s); any turn whose first attempt fails late + a full second attempt exceeds ~600 s total escapes the envelope
4. The first attempt's transport error itself is not persisted (the answer never materialized) — [NEEDS CLARIFICATION] on its exact text; the agent's "may be transient" judgment is the only surviving evidence

## Suspected Code Paths

- The Dify chatflow's `hermes_agent` node behavior: its agent loop treats tool transport errors as retryable and re-invokes within the same turn — the retry policy lives in Dify's agent machinery/prompt, not in the sidecar
- The chatflow's `hermes_agent` node prompt (DSL, `AGI_Assistant.yml`): currently silent on retry policy for transport errors — the agent defaults to one retry on its own judgment
- `src/agentic_rag_mcp/server.py` — the 540 s envelope (working as designed; this bug is the *cumulative* window, not the per-call budget)

## Root Cause Hypothesis

**High confidence on the mechanism, low on the first attempt's error.** The daemon's ~600 s window applies to the workflow run's tool time in aggregate; the honest envelope guarantees the *sidecar* finishes a single invocation at 540 s, but nothing prevents the Dify agent from spending the first attempt's error time (~fast or slow) plus a full second 540 s attempt inside the same run. When attempt 1 fails near the end of its budget (or even mid-way), the retry cannot complete inside the remaining window, and the daemon kills the run — resurrecting the silent-kill failure mode for retried turns. The first attempt's transport failure is unobserved (nothing persisted); candidates are a transient gateway/mirrored-network blip or the residual stream-cut class if the keep-alives missed a beat — unprovable from the empty answer.

## Proposed Remediation

**Preferred**: make the chat-side agent **relay transport failures instead of retrying them**. Add one bullet to the `hermes_agent` node prompt (the layer we already own from the typing-search fix): "If a tool call fails with a transport error (peer closed connection / incomplete read / timeout), do NOT retry the same tool in the same turn — relay the failure to the user honestly and let them re-ask; a retry inside the same turn exceeds the platform's tool-time window and the turn dies without any verdict." This keeps re-asking as the user's choice (matching the recovery guidance the tools already emit) and closes the cumulative-window escape. Apply via the export→patch→publish console path (the local-DSL hand-edit trap is known).

**Alternatives**:
- Halve the per-attempt budget (e.g., 270 s) so two attempts fit the window — rejected: cripples legitimate long single attempts to protect a retry behavior we don't want
- Suppress the transport error from reaching the agent (sidecar retries internally) — rejected: moves the retry into the sidecar where the same window math applies, and loses user visibility

**Files likely to change**:
- `dify/AGIAssistant/AGI_Assistant.yml` — `hermes_agent` node prompt: no-retry-on-transport-error bullet; republished via the console API
- No sidecar code changes (the 540 s envelope is correct as-is)

**Tests to add or update**:
- DSL graph assertion post-publish: the no-retry bullet exists in the live workflow (same `graph::text LIKE` check pattern used before)
- Live verification: re-ask the failing request twice if needed; observe that any transport-error turn returns an honest relayed verdict instead of a killed run

## Risks & Considerations

- Removing the agent's retry trades a small chance of recovery-by-retry for guaranteed honest failure — the tools' honest-error contract and the user's re-ask are the designed recovery path; a silent kill recovers nothing
- The first attempt's transport failure root cause stays unknown (nothing persisted); if such failures recur and are observable via a relayed verdict, they become diagnosable — the fix itself creates the observability
- The same retry behavior applies to the office/file lanes' tools in the chatflow — the no-retry bullet should cover all `hermes_*` tools, not just launch (one sentence in the same bullet)
- Publishing the chatflow touches the draft workflow — use the pinned apply cycle, prompt-only

## Open Questions

- [NEEDS CLARIFICATION: the first attempt's exact transport error text — unobservable from this turn (empty answer); the first *relayed* transport error after this fix will provide the evidence if the underlying blip recurs]
