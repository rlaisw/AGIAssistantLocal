# Bug Assessment: CPU% above 100% in windows-mcp process listings — an unnormalized multi-core aggregate, unexplained in the relay

- **Slug**: the-value-of-cpu-is-impossibel
- **Created**: 2026-11-14T12:58:00+00:00
- **Source**: pasted text (the chat's "top 5 by CPU" table: System Idle Process 1798.5%, vmmemWSL 145.7%, …)
- **Verdict**: valid — the reported confusion is real and reproduced live; the underlying values are internally consistent, but the "%"-labeled scale is misleading without a multi-core explanation
- **Severity**: low — semantics/presentation defect only; the data is genuine and audited, no functional or data risk; every CPU listing in the chat will confuse any reader who expects 0–100%

## Report (verbatim or summarized)

> "the value of cpu% is impossibel because greater than 100%"
>
> Result — top 5 by CPU:
> PID Name CPU% Memory
> 0 System Idle Process **1798.5%** 0.0 MB
> 8928 vmmemWSL **145.7%** 19802.8 MB
> 4 System 12.1% 16.3 MB
> 21440 Taskmgr.exe 7.0% 187.6 MB
> 5416 cyserver.exe 6.6% 493.5 MB

No URL was supplied with the report.

## Symptom

The chat's process listings show CPU% values far above 100% (System Idle Process at ~1800%), which reads as impossible to anyone expecting a per-core 0–100% scale. Expected: either values on a 0–100% scale, or the scale explained — the windows-mcp service computes CPU% as the **aggregate across all logical processors without normalizing** (this host has 20 logical CPUs, so ~2000% = all cores fully busy, and an idle machine's System Idle Process naturally shows ~1800%+).

## Reproduction

1. **Live reproduction (performed during assessment, 2026-11-14 ~12:55 UTC)**: `windows_mcp_process_list(sort_by="cpu", limit=5)` through the container → System Idle Process **1876.7%**, vmmemWSL 98.5% — the same class as the report.
2. Host fact: `NUMBER_OF_PROCESSORS` = **20** — 1876.7% ≈ 18.8 of 20 cores idle; the aggregate interpretation fits exactly.
3. The behavior has been present in every CPU-sorted listing all day (e.g., the 09:33 container-vantage probe showed vmmemWSL at 176.4%).
4. The relay (agent answer) presents the table verbatim with no scale explanation — the lane correctly relays genuine data; nothing explains the unit.

## Suspected Code Paths

- The windows-mcp host service's `Process` tool (`C:\Users\RLWC145\AppData\Roaming\uv\tools\windows-mcp\…\windows_mcp`) — computes the aggregate, un-normalized CPU% — upstream, out of this repo.
- `dify/AGIAssistant/AGI_Assistant.yml` — the Hermes-lane FAST PATH instruction and the two windows-mcp `tool_description`s added 2026-11-14: none mention the multi-core scale, so the agent relays the raw table without explanation.
- `src/agentic_rag_mcp/windows_mcp/client.py` — the lane relays the service output verbatim (by design, the anti-fabrication posture); it must not alter the data, so the fix belongs in the relay's explanation, not the data path.

## Root Cause Hypothesis

**High confidence.** The service's CPU% is the sum of per-core utilization across all logical processors, not a 0–100% normalized share — internally consistent and correct for that definition (verified against the host's 20 logical CPUs: System Idle ~1876% ≈ the idle cores), but the "%"-labeled column reads as impossible on a per-core scale, and neither the tool description nor the lane instruction tells the agent what the unit means, so the chat's answer inherits the confusion.

## Proposed Remediation

**Preferred** (relay-side explanation, data untouched): add the scale explanation where the agent reads it — one sentence in the FAST PATH lane instruction and in both windows-mcp `tool_description`s in `dify/AGIAssistant/AGI_Assistant.yml`: "CPU% aggregates across ALL logical processors — values above 100% are normal (a fully-busy core contributes 100%; this class of host has many cores, so System Idle Process often exceeds 1000% on an idle machine); when relaying a CPU listing, add that one-line explanation." The verbatim-relay contract is preserved — the agent relays the genuine table and appends the unit explanation.

**Alternatives**:
- Normalize in the lane (divide by the host's logical-processor count) — rejected: alters genuine data, hardcodes a host property into the sidecar, and hides what the service actually reports.
- Upstream fix in the windows-mcp service (offer both columns: normalized CPU% + core aggregate) — the ideal end state, but out of this repo; a note for the upstream owner.

**Files likely to change**:
- `dify/AGIAssistant/AGI_Assistant.yml` (the FAST PATH bullet + the two windows-mcp tool_description entries)
- `tests/unit/` (a string pin that the DSL carries the scale explanation)

**Tests to add or update**:
- Pin: the yml's fast-path section and tool descriptions contain the "above 100%" multi-core explanation text (house string-pin style).

## Risks & Considerations

- DSL-only change: requires `deploy chatflow` (publish), no sidecar rebuild, no tool-count change.
- The explanation must not soften the honesty posture: the table stays verbatim; the explanation is appended, clearly framed as what the unit means.
- Host-relative wording: keep the explanation generic ("many cores") rather than hardcoding 20 — the yml ships to machines that differ.

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the mechanism is verified live against the host's actual core count.]
