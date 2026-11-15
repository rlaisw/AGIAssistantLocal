# Bug Assessment: no PowerShell / windows-mcp tool on the chat branch — a designed deferral plus a first-turn routing friction

- **Slug**: does-not-have-a-powershell-windows-mcp-tool
- **Created**: 2026-11-14T09:50:00+00:00
- **Source**: pasted text ("This branch of the chat does not have a PowerShell / windows-mcp tool")
- **Verdict**: valid — the chat genuinely has no windows-mcp tool (a deliberate, documented Option-A deferral from spec 040), and the first attempt at the underlying task hit the read-only lane's ask-back before the existing PowerShell path completed it
- **Severity**: low — the user's actual task succeeded in the same conversation two calls later via the existing PowerShell lane; the windows-mcp surface is a scoped-out follow-up, not a broken flow

## Report (verbatim or summarized)

> "This branch of the chat does not have a PowerShell / windows-mcp tool"

No URL was supplied with the report.

## Symptom

Asking the chat to "list top 5 running processes on Windows" does not find a windows-mcp tool (true — none is registered with the chat, by the Option-A scope decision recorded in spec 040's Clarifications), and the first attempt reads as "no tool" because the read-only diagnostics lane answers with an ask-back instead of running. The chat DOES have a general PowerShell path (`hermes_run_powershell`, spec 034), and it completed the user's request on their second phrasing.

## Reproduction

From the audit trail (2026-11-14, HK = UTC+8):

1. **17:40:40** — "list top 5 running processes on Windows": `skill-search` ran, then `run-command` → **blocked with ask-back**: "which read-only diagnostic do you want? The run-command lane…" — the read-only allowlist gate (spec 033) asked back instead of the request landing on a PowerShell tool. This is the turn that reads as "no tool".
2. **17:41:49** — "list top 5 processes by CPU usage": `skill-search`, then `run-powershell` → **executed**: `Get-Process | Sort-Object -Property CPU -Descending | Select-Object -F…` — the PowerShell lane (spec 034) ran the genuine command.
3. **17:42:38** — `run-powershell` → **executed** again (a follow-up in the same conversation).

So the PowerShell tool exists on the Hermes Local Agent branch and works; what does not exist anywhere in the chat is a **windows-mcp** tool (verified: zero references in `src/agentic_rag_mcp/server.py`'s 53-tool surface; the spec-040 lane module ships in the sidecar but registers no chat tool, per the clarified Option-A: "no new owner-facing chat tool").

## Suspected Code Paths

- `src/agentic_rag_mcp/server.py` — 53 registered tools; no windows-mcp tool is registered (by design); `hermes_run_powershell` (line ~1047) is the chat's existing PowerShell path; `hermes_run_command` is the read-only lane whose gate produced the ask-back.
- `src/agentic_rag_mcp/windows_mcp/` — the verified, tested lane module (client + health, spec 040) with no chat exposure — the natural surface for the follow-up tools.
- `src/agentic_rag_mcp/hermes_run_gate.py` — the read-only allowlist whose ask-back fired on attempt 1 ("list top 5 running processes" did not map cleanly to one allowlisted command).
- `dify/AGIAssistant/AGI_Assistant.yml` — the Hermes Local Agent branch's tool instructions (which tool each phrasing should reach; the process-listing phrasing landed on run-command first).

## Root Cause Hypothesis

**High confidence, two stacked parts.** (1) *Designed gap*: the chat has no windows-mcp tool because spec 040's Option-A clarification explicitly scoped the feature to repairing the channel ("no new owner-facing chat tool; a chat-facing tool can be a separate follow-up feature") — the reported absence is the documented deferral, now visible from the chat side. (2) *First-turn friction*: the user's initial phrasing ("list top 5 running processes") routed to the read-only `run-command` lane, whose allowlist gate honestly asked back, so the turn failed to execute and read as a missing tool — while the general PowerShell lane (which does exist and needs only the draft→confirm flow) completed the same request one turn later. The report conflates the two: only the windows-mcp half is a true absence.

## Proposed Remediation

**Preferred** (two independent parts, both cheap now that the lane module is verified):
1. *The follow-up feature the spec already names*: register the windows-mcp lane as chat tools on the Hermes Local Agent branch — a read-only `windows_mcp_process_list` (the Process tool's listing mode, no confirm needed) and `windows_mcp_status` (honest health), with DSL lane rules routing process-listing phrasings to it. The sidecar module, contracts, envelopes, and tests all exist (spec 040); this is registration + DSL rules + tool-sync, not new engineering. Deterministic listings get the fast path with zero prompt, while arbitrary PowerShell keeps the existing two-phase `hermes_run_powershell` confirm.
2. *The routing nudge*: a one-line DSL rule so "list top N processes" phrasings prefer the windows-mcp/PowerShell path over the read-only run-command lane (whose allowlist is intentionally narrower and asks back otherwise).

**Alternatives**:
- Do nothing and rely on `hermes_run_powershell` — workable (proven today) but keeps the first-turn ask-back friction and leaves the verified lane unused by the chat.
- Expose all four windows-mcp tools (Process/Clipboard/Notification/Registry) to the chat immediately — rejected for now: clipboard/registry writes need their own gate review (the registry-write path ran unprompted, per the T019 finding); read-only listing + status is the safe first slice.

**Files likely to change**:
- `src/agentic_rag_mcp/server.py` (tool registrations)
- `dify/AGIAssistant/AGI_Assistant.yml` (lane rules)
- `tests/unit/` (registration/contract pins)

**Tests to add or update**:
- Tool-surface pin (the new tools appear; registry/clipboard deliberately absent from the first slice).
- DSL rule pin (process-listing phrasing routing) in the existing router-test style.

## Risks & Considerations

- Tool count changes (53 → 55) require a Dify tool re-sync + chatflow publish (`deploy all` path) — the documented one-command flow.
- The registry-write-unprompted finding (T019) argues for keeping privileged windows-mcp tools out of the chat slice until a gate review — the preferred slice (read-only listing + status) avoids that entirely.
- The run-command ask-back is CORRECT behavior for its lane (honest allowlist) — the fix is routing preference, not gate loosening.

## Open Questions

- [NEEDS CLARIFICATION: whether you want the windows-mcp chat tools now (the follow-up feature) or only the routing nudge — the assessment recommends both; the lane module is already built, tested, and live-verified.]
