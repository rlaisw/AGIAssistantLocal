# Bug Assessment: "the local agent simply has no shell/PowerShell execution capability" — duplicate of the by-design refusal, and the premise is factually wrong

- **Slug**: `the-local-agent-simply-has-no-shell-powershell-execution-capability`
- **Created**: 2026-11-09T08:18+00:00
- **Source**: pasted text (the same blocked-refusal message assessed minutes ago)
- **Verdict**: invalid — **duplicate** of `.specify/bugs/i-cant-execute-powershell-or-any-command-line-lookup-for-you/assessment.md` (same refusal, same turn evidence, same session), **and the slug's premise is factually incorrect**: the local agent *does* have a shell/PowerShell execution capability — WindowsMCP exposes a `PowerShell` tool ("Shell/command execution", verified live: `hermes mcp test WindowsMCP` → 21 tools). What refuses the request is the **sidecar's launch gate** — a deliberate, test-pinned v1 security boundary that never routes shell/command-line phrasing to that tool.
- **Severity**: low — no malfunction; one request class is unsupported by design, answered with an honest verbatim refusal.

## Report (verbatim or summarized)

> "Blocked: shell/PowerShell/command-line requests are refused (v1 launch scope: one program by name or full .exe path only — never arguments, never shell/PowerShell, never scripts or shortcuts)"

Identical to the report assessed in `i-cant-execute-powershell-or-any-command-line-lookup-for-you` (this session, 08:15 UTC) — the same blocked verdict from the same turn (audit `blocked unsupported`, 2026-11-09T08:11:49).

## Symptom

A shell/command-line request ("use windows-mcp powershell, show my windows current ip address") is refused by the launch gate. Expected — this is FR-005 designed behavior, pinned by contract tests; the relay relays it verbatim with honest self-help advice.

## Reproduction

Identical to the twin assessment: ask any shell/PowerShell phrasing → relay calls `hermes_launch_app` (per the anti-fabrication law) → gate blocks (`hermes_launch_gate.py:157`) → verbatim refusal relayed, no workaround attempted. Pinned by `tests/unit/test_hermes_launch_gate.py:131,222`.

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_launch_gate.py:157` — the refusal branch (FR-005, scope documented at `:24`)
- `tests/unit/test_hermes_launch_gate.py:131,222` — the contract that pins the refusal
- WindowsMCP `PowerShell` tool — the capability that exists but is deliberately unrouted (verified live via `hermes mcp test WindowsMCP`)

## Root Cause Hypothesis

**High confidence — not a defect, and not a missing capability.** The premise "simply has no shell/PowerShell execution capability" is wrong at the Windows layer: the agent's WindowsMCP tool surface includes a full `PowerShell` tool. The sidecar's launch gate is the trust boundary between the internet-facing relay and the machine, and specs 029/030 deliberately scoped v1 to bare executables — shell/command-line phrasing is refused in code, with pinning tests. The request class (system-state lookups) has no lane today; opening one is an owner security decision.

## Proposed Remediation

**Preferred**: none — close as duplicate/by-design. Everything of substance is already in the twin assessment: if the owner wants diagnostics lookups (IP, ping, systeminfo), the path is the **plan workflow for an allowlisted `hermes_run_command` spec** (read-only command allowlist enforced in sidecar gate code, honest envelope, full audit parity, following the 028–030 pattern) — not the bug lifecycle. A bug fix here could only loosen the security boundary, which would be a regression, not a fix.

**Alternatives**: unchanged from the twin assessment — type-into-terminal followup (rejected: it is the exact workaround the gate exists to prevent) and exposing WindowsMCP's `PowerShell` tool directly to the relay (rejected outright: bypasses gate + audit; the tool is uncontained full shell).

**Files likely to change**: none (bug lifecycle); spec path documented in the twin assessment.

**Tests to add or update**: none for this bug; the existing pinning tests are the contract working.

## Risks & Considerations

- Same as the twin assessment: any command-execution path is security-sensitive; an allowlist must live in sidecar code, never in a prompt; audit parity per attempt.
- Filing the same refusal under new slugs creates duplicate lifecycles — the decision point is binary (spec or close) and already captured once.

## Open Questions

- [NEEDS CLARIFICATION: same single question as the twin assessment — does the owner want a scoped diagnostics capability? If yes: plan workflow for the `hermes_run_command` spec. If no: close both reports as by-design.]
