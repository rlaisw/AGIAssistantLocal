# Data Model: Office Save Anywhere

**Feature**: specs/031-office-save-anywhere/spec.md · Supersedes 030 FR-003 · 2026-11-03

## Entities

### SaveTarget (new)

The location a task explicitly names — any local drive, any folder.

| Field | Type | Rules |
|-------|------|-------|
| raw | str | the path token as captured from the prompt (punctuation-tolerant per `normalize_path`) |
| normalized | str | the canonical host-side form (`C:\x` → `/mnt/c/x`; `D:\x` → `/mnt/d/x`; trailing sentence punctuation stripped — bug `fail-to-save-file` behavior, now location-agnostic) |
| origin | `named` \| `default` | `named` when the prompt contains a path token; `default` when none (the work folder) |
| ridealong | on the gate verdict | the gate no longer refuses any named location; the verdict carries the target so the directive and audit can name it |

### DefaultFolder

The owner-configurable default (`hermes_office_root`, default `C:\OfficeMCP`) — **a default, not a boundary**. Unnamed saves land there exactly as before; no refusal class references it anymore.

### OverwriteDecision (new, instruction-enforced)

| Field | Type | Rules |
|-------|------|-------|
| named_existing_file | proceed | the task names the exact file → update it; the step report MUST say an existing file was replaced |
| unsaved_changes_conflict | ask-back | the application holds unsaved interactive changes for the named file → ask before writing; never silently discard |
| ambiguous_target | ask-back | no file named and one would have to be picked → ask; never guess-overwrite |

Enforced at the agent-instruction layer (research R2) — the gate cannot see live application state; the `STEP`/`TASK` protocol machine-checks the report.

### AuditEntry (unchanged shape, new semantics)

| Field | Value after 031 |
|-------|-----------------|
| normalized_path | the **actual target** — the `ACTIVE FILE` report line after a save (a user-named location like `D:\projects\report.docx` in host form), or the default folder for unnamed tasks |
| allowed_root | the configured default (`C:\OfficeMCP`) — remains the lane discriminator for battery cross-checks |

**Invariants**: one append-only entry per step/refusal; the full actual target is recorded (FR-006); the log never prunes.

## State transitions

Unchanged from 030's pipeline — the only difference: the gate's containment block is replaced by SaveTarget extraction; a named location flows through the directive to the agent and back through `ACTIVE FILE` into the audit:

`prompt → gate (kind/app/content-rules + SaveTarget extraction) → [blocked: content rules only — the location class never blocks] | state-resolve → agent turn (directive names the target) → parse markers → per-step audit (normalized_path = actual target) → envelope`

## What this model deliberately does NOT contain

No location allowlist, no system-directory blocklist, no per-drive rules — the operating system's permission checks are the only location guardrail (FR-004), enforced by running as the signed-in user without elevation.
