# Data Model: Reliability Monitor applet (042)

One runtime object joins the existing tier-1 model; no new stores.

## Entities

### Settings target (new entry on the tier-1 inventory)
| Field | Value / Rule |
|---|---|
| display_name | "reliability monitor" |
| synonyms | "reliability history", "stability monitor" (all resolve to the same entry; natural-phrasing aliases follow the installed-programs precedent) |
| launch | the perfmon.msc/rel per-host form (research R1 — plain `perfmon /rel` is the silent-die case) |
| kind | the launcher's fourth per-host branch: perfmon-hosted (distinct from `.msc`-direct, `.cpl`, and Settings pages) |

Validation: identical to every target — one target per request, unknown/ambiguous asks back with the list, nothing beyond the launch form executes.

## State transitions

Unchanged from the tier-1 contract: request → resolved → launched (audit `windows-mcp-open` executed) | ask-back (blocked) | the shared down/deferral envelopes.

## Relationships

One request → one target → one audit row. The window titles as "Performance Monitor" (Reliability is perfmon.msc's `/rel` view) — the verification check matches the window title, not the view's label.
