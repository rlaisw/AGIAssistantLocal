# Data Model: Windows-MCP Applet Control (041)

No new persistent stores — the feature reuses the draft/confirm store and the append-only audit trail. The runtime objects:

## Entities

### Settings target (tier 1)
| Field | Type | Notes |
|---|---|---|
| kind | enum | `cpl` \| `settings_page` |
| identifier | string | from the reviewed list (e.g. `sysdm.cpl`, `ms-settings:display`) |
| display_name | string | what the confirm/relay shows the owner |

Validation: identifier must be a member of the reviewed target list (spec Assumptions); unknown or ambiguous → ask-back with the list. One target per request; nothing beyond the identifier is passed to the launcher.

### Read-only allowlist entry (tier 2)
| Field | Type | Notes |
|---|---|---|
| name | string | the query's intent name (e.g. `network-adapters`) |
| command_shape | fixed string | the exact query executed (e.g. `Get-NetAdapter \| Select Name,Status,LinkSpeed`) |
| intent_patterns | list | natural-language mappings (the spec-033 pattern) |

Validation: an unmatched request, or one that maps to a write-shaped command, is refused with the list shown — never a best-effort interpretation. One query per request.

### Draft/confirm record (tiers 3-4, reuses the existing store)
| Field | Type | Notes |
|---|---|---|
| conversation | string | the binding scope |
| kind | enum | `command` (tier 3) \| `gui_sequence` (tier 4) |
| text | verbatim string | tier 3: the exact command; tier 4: the plain-word sequence ("click Uninstall on Zoom, then confirm the removal dialog") |
| state | enum | pending → executed \| re-drafted \| cancelled |

Rules (inherited + extended): a confirm call carries no text — the stored record is what runs; a modified instruction re-drafts; silence never executes; never-list records are refused at draft time AND at confirm time (binding even when both preconditions hold).

### GUI step (tier 4 runtime)
| Field | Type | Notes |
|---|---|---|
| action | enum | `click` \| `type` \| `wait` (snapshot/screenshot are read-only steps) |
| target | string | the control as described in the confirmed sequence |
| value | string \| null | typed text; credential/password fields are refused by the gate before any call |

### Audit row (all tiers, shared funnel)
Unchanged contract: operation class per tier (`windows-mcp-open-*` / `windows-mcp-read-*` / `windows-mcp-gui-*` / the existing powershell classes for tier 3), decision executed/blocked/error, conversation, duration. Additions: tier-4 rows record each step's outcome; credential-field refusals audit the refusal without the field's value (masked per the sensitive rule).

## State transitions

- Tier 1: request → validated → launched → audited executed (or ask-back → audited blocked).
- Tier 2: request → allowlist match → executed read (or refusal with the list → blocked).
- Tier 3: request → draft (audited pending) → plain confirm → stored-text execution (or re-draft / never-list refusal at either phase).
- Tier 4: request → sequence draft → plain confirm → step-by-step execution with per-step audit → completed, or stop at {credential field, UAC prompt, unexpected dialog, deferral} with an honest partial report naming the completed steps.

## Relationships

One chat request → one target/query/draft; one GUI sequence → N steps, each audited; all rows land in the single audit trail; loop-gate classification: the new read/open tools are loop-exempt (deterministic fast path, the spec-040 precedent), tier 3-4 keeps the existing loop rules.
