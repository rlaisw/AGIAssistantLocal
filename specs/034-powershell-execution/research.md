# Research: PowerShell Execution Lane (spec 034)

Phase 0 output. Every decision was evaluated against the live architecture proven in specs 028–033 (including the 033 lane's live-debugged agent protocol and the office lane's confirm-before-send email flow). No NEEDS CLARIFICATION items remain — both owner decisions were resolved in the specify/clarify session (confirm-every-command; confirmed deletion allowed on this lane).

## D1. Two-phase tool: draft registration + confirm execution

- **Decision**: `hermes_run_powershell` has two phases. **Draft phase**: the relay passes the user's request plus the exact command it drafted; the gate never-list-scans the draft, the tool stores it as the conversation's pending draft, echoes it back verbatim in the envelope, and audits it with its exact text — nothing executes. **Confirm phase**: a separate call (`confirm: true`, no command text) executes the *stored* draft.
- **Rationale**: Makes FR-003 (confirmed text = executed text) **structural**: the confirm call carries no command text at all, so drift between what was shown and what runs is impossible by construction — the stored, scanned, shown string is the only thing execution can refer to. Direct precedent: the office lane's compose→DRAFT PENDING→confirm→send flow (spec 030), plus its conversation-scoped pending state.
- **Alternatives considered**: single-phase with after-the-fact echo comparison (rejected — detects drift instead of preventing it); a separate confirm tool (rejected — one tool, one schema, simpler relay contract).

## D2. Confirmation semantics

- **Decision**: A plain affirmative ("yes", "run it", "confirm") addressed to the shown text confirms the *stored* draft; any modification ("yes but add -Recurse") re-drafts from scratch; a new request drops the pending draft; silence is never consent.
- **Rationale**: Mirrors the office email confirmation rules verbatim (proven UX); keeps the confirm call trivially simple for the relay.
- **Alternatives considered**: requiring verbatim repetition of the command as confirmation (rejected — hostile UX, no security gain since the stored draft binds anyway).

## D3. Never-list: narrow, whole-draft, both phases

- **Decision**: A fixed pattern set in gate code, scanned over the **complete draft text** at registration and re-scanned at execution (defense-in-depth): `format` (volume), `diskpart`, `bcdedit`/`bootcfg`/`bootrec`, `vssadmin … delete`, `reagentc` (recovery), `manage-bde … (off|remove)` (BitLocker), `cipher /w`, `Clear-Disk`/`Initialize-Disk`/`Restore-Disk`, and wipe-class utilities. Ordinary PowerShell — pipes, `Where-Object`, `Remove-Item`, service/process control — is legal here: this lane executes real PowerShell, and the never-list is system-integrity destruction only (the 033 lane's no-pipes/no-args rules stay in *that* lane).
- **Rationale**: The floor must be narrow enough to be auditable and absolute enough to trust; the spec's never-list classes map directly onto these patterns. Smuggling inside chained operators or nested calls is caught because the scan is over the whole exact draft.
- **Alternatives considered**: a broad destructive-verb list (rejected — the owner chose confirmed deletion/process control as legal); prompt-level cautions (rejected — Constitution IV).

## D4. Prompt-injection containment = the human checkpoint

- **Decision**: FR-007's structural reading: instructions discovered in tool outputs, files, or web content can at most produce a **draft the owner sees in full and rejects** — nothing executes without the explicit confirmation of the exact text. The relay instruction carries the provenance rule as defense-in-depth (drafts must be grounded in the user's request alone).
- **Rationale**: Provenance is not mechanically verifiable inside the tool (the relay authors the draft); the confirmation step is the containment that does not depend on provenance being right. This is honest about what code can and cannot guarantee.
- **Alternatives considered**: provenance heuristics in the gate (rejected — unenforceable theater).

## D5. Agent protocol: 033's live-proven instruction set, generalized

- **Decision**: `POWERSHELL_INSTRUCTIONS` = the 033 `RUN_COMMAND_INSTRUCTIONS` with the command source generalized: run EXACTLY the directive's command via `mcp__WindowsMCP__PowerShell` (never the WSL `terminal`), retry `USER_CONTROL` patiently, fall back to the direct WindowsMCP SSE channel (`127.0.0.1:8800`) when the gateway strips arguments, and report `COMMAND:` / `OUTPUT:` / `TASK: COMPLETED` — the tool verifies the echoed command matches the **stored draft** before stamping ok.
- **Rationale**: Every element was debugged live on this host during 033 (the WSL-shell trap, the USER_CONTROL retry, the arg-strip direct-channel recovery); generalizing costs one paragraph.
- **Alternatives considered**: a fresh minimal prompt (rejected — re-learning 033's three live-found failure modes).

## D6. Audit shape

- **Decision**: One row per attempt with the exact text: **draft registration** → `decision=executed, operation=run-powershell`, outcome = the exact draft text (the registration *is* the attempt's audit; an unconfirmed draft's row exists as its record); **execution** → its own row with outcome = the bounded real output, `duration_s` + timing; **never-list refusal** → `blocked` with the rule named; **confirm without pending** → `blocked` ask-back. The audit decisions enum is unchanged.
- **Rationale**: Preserves the one-row-per-attempt invariant and the FR-004 exact-text requirement without extending the shared audit schema.
- **Alternatives considered**: new audit decision values (rejected — Constitution I: the shared enum stays).

## D7. State: mirror of the office pending-draft state

- **Decision**: A tiny `PowerShellState` (in-memory, conversation-scoped, module-level singleton like the office state): `set_pending(conversation_id, command)`, `pending(conversation_id)`, `clear(conversation_id)`. One pending draft per conversation — a new draft replaces (and its registration row supersedes in the log) the old.
- **Rationale**: The office lane's pattern, shrunk to the minimum; one-pending-per-conversation matches one-command-per-request.
- **Alternatives considered**: piggybacking on OfficeState (rejected — different lifecycle, clearer separate); persistence to disk (rejected — pending drafts are ephemeral by design; the audit is the durable record).
