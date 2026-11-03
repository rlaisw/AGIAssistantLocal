# Research: Office Save Anywhere (Phase 0)

**Date**: 2026-11-03 · Everything below is grounded in this session's live evidence — the gate source (read fully during five bug cycles today), the live probes, and the 030-era artifacts.

## R1 — The gate change, precisely

- **Decision**: in `office_gate.py`'s `gate_office`, the work-folder containment block (the `_RE_PATH_TOKEN` loop that refuses paths outside `office_root`) is **removed**; the extracted path tokens — if any — ride along on the verdict as the named `SaveTarget` (normalized via the shared `normalize_path`, which already tolerates trailing punctuation per the `fail-to-save-file` fix). No path token → the directive uses the default folder (`office_root`), exactly as today. The `.exe`-only and code-exec checks are untouched (they are content rules, not location rules).
- **Rationale**: the boundary is becoming a default — the single inversion the spec asks for. Every other gate behavior has contract tests pinning it.
- **Alternatives considered**: a configurable allowlist of extra roots (rejected — the owner chose "any folders" outright, and an allowlist reintroduces the `fail-to-save-file`/`no-powerpoint-tool` dead-end class); per-drive rules (unasked for).

## R2 — Overwrite semantics and the agent instruction

- **Decision**: the gate does NOT parse overwrite intent (it cannot know whether a named file exists) — the rule is enforced at the **agent instruction layer**: `OFFICE_INSTRUCTIONS` gains — "if the task names an existing file, update it and report honestly that an existing file was replaced; if the application holds unsaved interactive changes for it, ask back before writing; never elevate privileges; if the OS denies a write, relay the exact error." The sidecar's `STEP`/`TASK` protocol then carries the report (the audit records the actual target from `ACTIVE FILE`/the step text).
- **Rationale**: the agent (via OfficeMCP COM/PowerShell) is the only layer that can see the live application state; the 030 protocol already machine-checks its honesty. Asking the gate to pre-check file existence would add a second truth source and can't see unsaved changes anyway.
- **Alternatives considered**: sidecar-side existence probe (rejected: no Windows filesystem visibility from the container, and it can't detect unsaved state); refuse all overwrites (contradicts the spec's owner decision).

## R3 — Audit and envelope shape

- **Decision**: `HermesAudit` is unchanged. The office tool's `_audit` call keeps `allowed_root=cfg.hermes_office_root` (the configured default — it remains the lane discriminator for battery cross-checks, `C:\OfficeMCP`) and `normalized_path=state.active_document(conversation_id)` — which after a save IS the actual saved target (set from the `ACTIVE FILE:` report line, including user-named locations like `D:\projects\x.docx`). So FR-006's "full actual target" is already how the machinery records it — no code change needed in the audit path; the contract documents it.
- **Rationale**: zero new code for the audit requirement — the existing `ACTIVE FILE` → `ActiveDocument` → audit flow already carries the true location; the battery's O7 check continues to work unchanged.
- **Alternatives considered**: a new audit field (rejected — writer schema change for no gain).

## R4 — Wording surfaces to update (the retired refusal class)

- **Decision**: three texts change: (1) the `hermes_office_task` docstring/tool description loses "document work is confined to the Office work folder (default C:\OfficeMCP)" and gains "save or read at any location the user names — any drive, any folder; unnamed saves use the default work folder"; (2) `OFFICE_INSTRUCTIONS` gains the R2 rule; (3) the DSL node's office-rule line gains the same sentence. The `no-powerpoint-tool` actionable-hint sentence in the gate reason retires with the refusal class it served (its unit-test assertion retires too).
- **Rationale**: a refusal class that no longer exists must not survive in user-facing text — otherwise the agent relays stale rules (the exact confusion the `no-powerpoint-tool` transcript showed).
- **Alternatives considered**: keep the old text "just in case" (rejected — stale rules are how the earlier bugs confused users).

## R5 — Test strategy and error handling (per plan input)

- **Failing-first gate matrix** (`test_office_gate.py`): the owner's exact case (`…save it to C:\temp\test`) → **ok** (currently blocked — the failing-first proof); `D:\projects\` → ok; a second drive path with punctuation (`D:\docs.`) → ok (the R1 tolerance is location-agnostic); **retired-refusal check**: no reason string mentions "outside the Office work folder" anymore; the executable-only and code-exec refusals still fire identically (macros/DDE/`=` formulas blocked wherever the target lives).
- **Tool wrapper** (`test_hermes_office_tool.py`, client mocked): the directive for a named-location task carries the named path; an OS-permission failure (the mocked client returns a permission-denied error) → `error` envelope with the OS error relayed; a successful save at a named location → the audit's `normalized_path` is the named target.
- **Battery** (`scenario_hermes_office_task`): one new probe — the owner's exact prompt, verified by reading the file at `c:\temp\test` through `/mnt/c/temp/test` (stdlib `zipfile`, same as O1); the existing O6 refusal matrix keeps 4 of 5 cases (the out-of-folder case retires; macros/DDE/address-less/mailbox-delete stay).
- **Error handling matrix** (unit or battery): permission-denied → honest error with the OS message; nonexistent deep path → parents created or honest failure; removable drive absent → honest failure; unsaved-changes conflict → ask-back (instruction-level, verified via the agent report in the live battery).
