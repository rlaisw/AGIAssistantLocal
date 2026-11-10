# Bug Assessment: disk-space checks are refused — the owner-requested allowlist amendment spec 033 anticipated

- **Slug**: `disk-space-usage-isnt-one-of-the-commands-its-allowed-to-execute`
- **Created**: 2026-11-09T09:45+00:00
- **Source**: pasted text (the relay's honest refusal: "The local agent couldn't run that — disk space usage isn't one of the commands it's allowed to execute.")
- **Verdict**: valid — as an **owner-requested capability amendment**, not a malfunction: every layer behaved exactly per design (verified in the audit: the user's "show me harddisk disk spaces usage" reached the gate via a real tool call at 09:38:57; the closed allowlist ask-backed; the relay reported honestly). Spec 033's Clarifications say "Owner may extend the list via a spec amendment only" — this report is that owner decision, and the amendment is small and well-bounded.
- **Severity**: low — no defect, honest UX today (the ask-back shows the list); the gap is one read-only command away from closed under the lane's existing, security-proven pattern.

## Report (verbatim or summarized)

> "The local agent couldn't run that — disk space usage isn't one of the commands it's allowed to execute."

> User asks (this session): "show my harddisk disk spaces", "show me harddisk disk spaces usage" → honest refusal naming the limitation. Same conversation: systeminfo asks complete for real (audit `executed run-command` 09:34:56, 09:36:23), and the locale mapping served "show my system locale of windows desktop" — the lane works; disk space is simply not on the list.

## Symptom

Asking for disk-space usage is refused with an honest "not one of the allowed commands" (the gate's ask-back relayed). Expected (owner's request): disk-space checks run as a read-only diagnostic like the others, with real output relayed.

## Reproduction

1. Ask "show me harddisk disk spaces usage" → the relay calls `hermes_run_command` (anti-fabrication law working) → the gate finds no allowlisted intent for disk phrasing → ask-back with the list → the relay relays the limitation honestly (audit `blocked run-command` 09:38:57 confirms the full chain).
2. 100% reproducible — the mapping does not exist; this is deterministic by design.

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_run_gate.py` — the closed allowlist (spec 033 FR-001): bare set {ipconfig, systeminfo, tasklist, whoami, hostname}, targeted set {ping, nslookup, tracert}; no disk-space intent phrases. "harddisk disk spaces" maps to nothing → the unmapped ask-back.
- `dify/AGIAssistant/AGI_Assistant.yml` — the run-command instruction bullet and the honesty/dispatch notice texts enumerate the working asks (no disk space).
- `specs/033-hermes-run-command/spec.md` — Clarifications: "Owner may extend the list via a spec amendment only"; Follow-ups already name this exact gap ("a small spec amendment can add a read-only volume command").

## Root Cause Hypothesis

**High confidence — by design.** The allowlist is deliberately closed (security model: the user's words never become command syntax) and disk space was consciously deferred at spec-033 time as amendment territory. The refusal chain is correct end-to-end; what is missing is the owner-approved entry.

## Proposed Remediation

**Preferred** — the spec-033 amendment, a **named recipe**: intent phrases map to a **fixed** command string the user never authors — "disk space(s)", "hard disk", "disk usage", "free space", "storage/volume/drive space", "get-volume" → `Get-Volume` (modern Windows PowerShell, read-only, bare; outputs DriveLetter, SizeRemaining, Size per volume). Concretely:

1. `hermes_run_gate.py`: add the recipe (fixed command, `bare` policy — no user arguments ever); order the recipe/intent match so an allowlisted name (`Get-Volume`) is exempt from the generic cmdlet refusal, which stays in force for everything unlisted.
2. Gate tests: mapping matrix (the disk phrases → `Get-Volume`), refusal integrity (unlisted cmdlets like `Get-NetIPAddress` still blocked, flags/pipes/smuggles still refused, recipe takes no args).
3. DSL text updates: the run-command bullet, the tool description, and the honesty/dispatch notice lists gain disk space; publish via the established cycle.
4. Record the amendment in `specs/033-hermes-run-command/spec.md` Clarifications (constitution governance: amendments carry documented rationale).
5. Hot-patch the sidecar gate; live-verify with a real disk ask (`Get-Volume` output with actual sizes).

**Alternatives**:
- `wmic logicaldisk get caption,freespace,size` — deprecated on current Windows; rejected.
- `fsutil volume diskfree <drive>` — requires a drive argument, complicating the no-args policy; rejected for v1.
- Keep refusing (current state) — rejected: the owner has now requested the capability, which is the exact trigger spec 033 defined for an amendment.

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_run_gate.py`
- `tests/unit/test_hermes_run_gate.py`
- `dify/AGIAssistant/AGI_Assistant.yml`
- `specs/033-hermes-run-command/spec.md` (Clarifications amendment record)

**Tests to add or update**:
- Gate: disk-phrase mapping matrix; `Get-Volume` direct-name mapping; unlisted-cmdlet refusals unchanged; no-args on the recipe; the refusal matrix stays green (no flag/pipe/smuggle regressions).

## Risks & Considerations

- The amendment carves a cmdlet into a list whose rule said "no cmdlets" — the security posture is preserved because the recipe is a **fixed string from the gate's table**, never user text; the generic cmdlet refusal stays for everything unlisted; echo-and-attest verification is unchanged.
- `Get-Volume` is read-only (volume inventory with sizes) — no state change; output is short (bounded at 4000 chars like all lane output).
- If the owner prefers a different command at fix time, the recipe table makes it a one-line swap.

## Open Questions

- [NEEDS CLARIFICATION: none blocking — `Get-Volume` is the default recipe (modern, read-only, bare); if the owner prefers `wmic`/`fsutil`, say so before/at `/speckit.bug.fix`.]
