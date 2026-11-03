# Contract: hermes_office_task — save-anywhere amendment (spec 031)

A **delta contract** against spec 030's `contracts/hermes-office-task.md`. The tool schema is **unchanged** (same name, same parameters, same envelope keys — Constitution I); only the gate semantics, instruction rules, and wording surfaces change. Everything not listed here carries forward byte-identical from 030.

## 1. Gate pipeline — the amendment (replaces 030 §2 step 2)

- **030 step 2 (work-folder containment) is REMOVED.** A named path is never refused for its location. The extracted path tokens become the **SaveTarget**: they ride on the verdict, normalized via the shared `normalize_path` (drive-letter case, mixed separators, trailing sentence punctuation — the `fail-to-save-file` behavior, location-agnostic, FR-007).
- A task naming **no** location continues to use the **default folder** (`hermes_office_root`, default `C:\OfficeMCP`) — the folder is a default, not a boundary.
- All **content** rules are unchanged and fire identically wherever the target lives: the code-execution ban (macro/VBA/DDE/external-link formula), the executables-only `.exe` rule for path launches, the formatting refusal (v1 scope), the recipient rules, confirm/cancel/continue classification.
- The refusal class "outside the Office work folder" is **retired** — its reason text, its actionable-hint sentence (bug `no-powerpoint-tool`), and its unit-test assertion go with it.

## 2. Directive construction (amends 030 §3)

- The directive for a task with a **named** SaveTarget carries the normalized target verbatim and instructs: save/open at exactly that location; create missing parent folders as needed; report the full saved path in `ACTIVE FILE:`. The answer names the full path (FR-001).
- `OFFICE_INSTRUCTIONS` gain the overwrite rule (research R2): a named existing file is updated with an honest "replaced an existing file" step report; an unsaved-changes conflict asks back before writing; an ambiguous target asks; the agent never elevates privileges; an OS permission failure is relayed with the exact operating-system error (FR-003/FR-004).
- The step protocol (`STEP`/`ACTIVE FILE`/`DRAFT ID`/`TASK` markers) is unchanged.

## 3. Audit (amends 030 §2 item 7 / §3)

- `HermesAudit` writer: unchanged. `normalized_path` records the **actual target** — the `ACTIVE FILE` report after a save (user-named location in host form) or the default folder (unnamed). `allowed_root` stays the configured default (`C:\OfficeMCP`) as the lane's battery discriminator.

## 4. Error handling (the core of this feature)

| Failure | Behavior |
|---------|----------|
| OS permission denied (protected/system location) | `error` envelope carrying the OS's exact message; no elevation, no retry-with-privileges; audited |
| Nonexistent deep path | parents created as needed, or the honest creation failure named with the location |
| Removable/network drive absent | honest failure naming the location |
| Existing file, unsaved changes open | ask-back before writing; nothing silently discarded |
| Ambiguous overwrite target | ask-back; never a guess-overwrite |

## 5. Wording surfaces updated (the retired class must not survive in text)

1. The `hermes_office_task` docstring (DSL-sync source): "document work is confined to the Office work folder" → "save or read at any location the user names — any drive, any folder; unnamed saves use the default work folder".
2. `OFFICE_INSTRUCTIONS`: the R2 overwrite/elevation/OS-error rules.
3. The DSL Hermes-node office-rule line: the same sentence.

## 6. Regression mapping (US3/FR-005)

- The 030 contract tests stay green except the **one** assertion that pins the retired refusal (updated to the new expectation).
- The 028 file lane and 029 launch lane: untouched, tests byte-identical.
- The battery's O6 refusal matrix keeps 4 of 5 cases (macros, DDE, address-less compose, mailbox-delete); the out-of-folder case retires; a new named-location probe takes its place (the owner's exact `c:\temp\test` case, verified by reading the file via `/mnt/c`).
