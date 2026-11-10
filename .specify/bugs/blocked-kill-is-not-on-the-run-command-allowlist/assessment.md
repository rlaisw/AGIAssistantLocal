# Bug Assessment: "kill" refused by the run-command allowlist — by design; state-changing operations are the lane's defining boundary

- **Slug**: `blocked-kill-is-not-on-the-run-command-allowlist`
- **Created**: 2026-11-10T07:45+00:00
- **Source**: pasted text (the gate's refusal message)
- **Verdict**: invalid — not a bug: killing a process is a **state-changing operation**, and the run-command lane's defining property (spec 033) is *read-only diagnostics only*. `kill`/`taskkill` sit deliberately in the gate's refusal matrix (FR-002; pinned by tests), and the refusal fired exactly as designed (audit `blocked run-command`, 2026-11-10 07:41:12, reason verbatim with the allowlist shown). Adding kill would not be an amendment like `Get-Volume` (which was read-only and in-class) — it would break the lane's security class.
- **Severity**: low — no malfunction; the chain was fully honest (real tool call → gate refusal → verbatim relay); user impact is that one destructive request class is unsupported by design.

## Report (verbatim or summarized)

> "Blocked: 'kill' is not on the run-command allowlist"

## Symptom

The user asks the chat to kill a process; the run-command gate refuses with the not-on-allowlist reason naming the read-only rule and showing the list. Expected — this is the security boundary working, not a defect.

## Reproduction

1. Ask anything containing "kill"/"taskkill" (e.g. "kill the notepad process") → the relay calls `hermes_run_command` (the law working) → the gate's refused-word scan fires → `blocked` with "read-only diagnostics only, one command per request. Allowed: ipconfig, systeminfo, tasklist, whoami, hostname, ping <host>, nslookup <host>, tracert <host>, Get-Volume (disk space)".
2. 100% reproducible — deterministic by design; confirmed in the audit at 2026-11-10 07:41:12.

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_run_gate.py` — `kill`, `taskkill`, `stop-process` etc. in `_REFUSED_WORDS`; the refusal carries `_RUN_SCOPE` ("read-only diagnostics only, one command per request") and `_ALLOWLIST`.
- `tests/unit/test_hermes_run_gate.py` — the destructive-verb refusal matrix (including `taskkill /im chrome.exe`) pins this exact behavior as a contract.
- `specs/033-hermes-run-command/spec.md` — FR-002: "any other command … or any state-changing verb … refused with zero execution"; Assumptions: "Out of scope: any state-changing execution."

## Root Cause Hypothesis

**High confidence — by design, and correct.** The architecture has deliberately never had a destructive lane: the file lane blocks delete/rename/move everywhere (spec 028's v1 scope), the launch lane takes no arguments (spec 029), and the run-command lane is read-only diagnostics (spec 033's defining property — the reason `Get-Volume` was an acceptable amendment and `kill` is not). Process termination is state-changing with system-stability blast radius; the gate refusing it with the list shown is the boundary doing its job.

## Proposed Remediation

**Preferred**: none in the bug lifecycle — close as by-design. The refusal is the security model; "fixing" it would be a security regression. For the underlying need, the read-only answer is `tasklist` — the user can list running processes from chat today and end one themselves.

**If the owner wants chat-driven process termination** (a genuine capability, but a new spec — the plan workflow, never `/speckit.bug.fix`): a dedicated process-control lane would need its own careful design — e.g. a confirmation round-trip naming the exact target (PID + process name, resolved via `tasklist` first), a system-critical-process denylist, one target per request, the honest-envelope + audit + cancellability machinery, and an explicit spec decision that the system now performs destructive actions. That is owner-level security design, squarely spec-033's "Out of scope" list until the owner says otherwise.

**Alternatives**: none — there is no reading under which kill belongs in the read-only diagnostics allowlist.

**Files likely to change**: none (this bug); the hypothetical spec would define its own.

**Tests to add or update**: none — the existing matrix already pins `taskkill` and the destructive-verb class; today's refusal matched it exactly.

## Risks & Considerations

- Precedent matters: `Get-Volume` was accepted because it is read-only and in-class; accepting `kill` because a user asked would erase the line that makes the whole run-command lane safe — the allowlist's read-only property is what keeps its attack surface auditable.
- A future process-control lane must not be an "allowlist amendment"; it is a new capability class with destructive blast radius (Constitution IV's honest envelopes and the audit machinery apply in full).

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the by-design verdict stands; if the owner wants a process-control capability, that request starts the plan workflow as a new spec.]
