# Bug Assessment: "I can't execute PowerShell or any command-line lookup for you" — the v1 launch scope refusing shell requests by design

- **Slug**: `i-cant-execute-powershell-or-any-command-line-lookup-for-you`
- **Created**: 2026-11-09T08:15+00:00
- **Source**: pasted text (the blocked-refusal message + the relay's full Reasoning trace for the turn, conversation `1a59cc02-…`)
- **Verdict**: invalid — not a bug: the refusal is the designed, test-pinned v1 launch-scope security boundary, and the relay behaved exactly per contract (real tool call, verbatim refusal, no workaround). The report is really a **capability request**: "show my Windows IP address" has no supported lane today. Opening one is an owner security decision — spec-sized work, not a bug fix.
- **Severity**: low — no malfunction anywhere in the turn; user impact is that one class of requests (shell/command-line lookups) is unsupported, with an honest refusal and self-help advice as the answer.

## Report (verbatim or summarized)

> "Blocked: shell/PowerShell/command-line requests are refused (v1 launch scope: one program by name or full .exe path only — never arguments, never shell/PowerShell, never scripts or shortcuts)"

> User ask: "use windows-mcp powershell, show my windows current ip address". The relay's reasoning shows textbook behavior: it recognizes the shell-execution request, calls `hermes_launch_app` with the full task text **because the anti-fabrication law requires a tool call in this turn**, the gate blocks (shell/PowerShell phrasing), it relays the refusal verbatim, explicitly declines to work around it ("Never re-attempt a blocked operation with rephrased paths… the refusal stands" — correctly refusing the "open PowerShell and type ipconfig" loophole it considered), and closes with honest advice: the user can run `ipconfig` / `Get-NetIPAddress` themselves.

## Symptom

The user asks for a command-line lookup (their Windows IP address); the launch lane refuses all shell/PowerShell/command-line phrasing. Expected behavior — this is the v1 launch scope working as specified (FR-005: "shell/command-line phrasing → refused"), not a defect; but it leaves a real user need unserved by any lane.

## Reproduction

1. Ask: "use windows-mcp powershell, show my windows current ip address" (any shell/command phrasing).
2. The relay calls `hermes_launch_app(task, conversation_id)`; the gate returns the blocked verdict (audit: `blocked unsupported` at 2026-11-09T08:11:49, reason verbatim above).
3. The relay relays the refusal verbatim and stops (no retry, no workaround, honest self-help advice).

100% reproducible — the behavior is pinned by contract, not intermittent.

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_launch_gate.py:157` — the shell/PowerShell refusal branch; scope documented at `:24`; FR-005 named in the docstring at `:127`.
- `tests/unit/test_hermes_launch_gate.py:131,222` — the refusal is **test-pinned** ("open notepad and also run powershell" → blocked; "open chrome and type powershell trick" → blocked): the behavior is a deliberate contract, not drift.
- The DSL launch bullet (relay-side): mandates passing shell requests to the tool and relaying the refusal verbatim, "do not try to work around those" — followed to the letter in this turn.
- Capability context (verified live): `hermes mcp test WindowsMCP` → 21 tools **including a `PowerShell` tool** ("Shell/command execution") — the underlying capability EXISTS on the Windows side; it is the sidecar's gate that deliberately never carries such requests to it.

## Root Cause Hypothesis

**High confidence — not a defect.** The v1 launch scope ("never arguments, never shell/PowerShell, never scripts or shortcuts") is the sidecar's security boundary between the internet-facing relay and the user's machine, designed in specs 029/030 and enforced in `gate_launch` with pinning tests. The reported turn shows every layer correct: the anti-fabrication law drove a real audited tool call, the gate refused, the relay passed the refusal through verbatim and refused the workaround path. The user's real need — a system-state lookup — simply has no lane in the current tool surface (file ops, bare launches, Office control), so the launch lane (the nearest match, since the user named powershell) correctly refused it.

## Proposed Remediation

**Preferred**: none in the bug lifecycle — close as by-design. The refusal is the safety boundary doing its job; "fixing" it by loosening the gate would be a security regression, not a fix.

**If the owner wants the capability** (a spec, run via the plan workflow — not `/speckit.bug.fix`): a new sidecar tool `hermes_run_command(task, conversation_id)` following the established 028–030 pattern — gate → agent's WindowsMCP `PowerShell` tool → honest envelope → audit as `operation=run-command`. The gate must carry a **read-only diagnostics allowlist** (e.g. `ipconfig`, `ping`, `nslookup`, `systeminfo`, `tasklist`, `whoami`) with: no arbitrary commands, no arguments beyond a narrowly parsed target (host/IP), no output redirection, injection-resistant parsing, and the same verbatim-relay rules. The allowlist must live in the sidecar gate (code), never in a prompt.

**Alternatives**:
- Type-into-terminal as a desktop followup ("open PowerShell and type ipconfig") — rejected: it is exactly the workaround the relay correctly refused ("the refusal stands"); enabling it would make the gate's shell refusal meaningless.
- Exposing WindowsMCP's `PowerShell` tool directly to the Dify relay — rejected outright: it would bypass the sidecar's gate and audit entirely; the WindowsMCP tool is full shell execution with no containment.

**Files likely to change** (only if the spec proceeds):
- `src/agentic_rag_mcp/` — new gate module + tool registration in `server.py` (pattern: `hermes_launch_gate.py` / `hermes_office_task`)
- `tests/unit/` — gate matrix mirroring the launch-gate suite
- DSL `hermes_agent` instruction + tool description (publish cycle)

**Tests to add or update**:
- Only in the spec path: an allowlist gate matrix (allowed diagnostics pass; arbitrary commands, arguments, pipes, redirection, encoding tricks → blocked with verbatim reasons; audit per attempt).

## Risks & Considerations

- Any command-execution path is security-sensitive by nature: the blast radius of the WindowsMCP `PowerShell` tool is the whole machine — the allowlist must be enforced in code at the sidecar, with the prompt carrying none of the security weight.
- Injection surface: user text reaching a shell parser (even allowlisted commands) needs the same defensive parsing the launch gate uses for `.exe` targets and the office gate uses for cell content.
- Audit parity: every attempt (blocked or executed) must land in `hermes-mcp/audit.jsonl` like the other lanes.
- The refusal UX is already good (verbatim reason + self-help advice) — the only unserved part is the action itself.

## Open Questions

- [NEEDS CLARIFICATION: does the owner want a scoped diagnostics capability at all? If yes, the next step is the plan workflow for the allowlisted `hermes_run_command` spec (security-sensitive, spec-sized). If no, this bug closes here as by-design.]
