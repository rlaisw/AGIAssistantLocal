# Contract: the reliability-monitor target (042)

One new entry on the tier-1 open contract (`contracts/applet-tiers.md`, spec 041). Everything except the target row and the launch form is inherited verbatim.

## Target row

| Surface | Synonyms | Launch form |
|---|---|---|
| reliability monitor | reliability history, stability monitor | `Start-Process mmc.exe -ArgumentList 'perfmon.msc','/rel'` (the live-verified per-host form — plain `perfmon /rel` silently exits from the service's context; research R1) |

## Behavior (inherited, unchanged)

- **In**: natural language + `conversation_id`; one target per request.
- **Gate**: bounded to the inventory (now 35 surfaces); unknown/ambiguous → ask-back with the list.
- **Out**: the Reliability Monitor window opens on the owner's desktop; `{status: ok, target, command}`; audited `windows-mcp-open` executed.
- **Errors**: the shared honest envelopes — service-down (recovery hint), desktop-activity deferral (named envelope + hands-off guidance), unknown target (ask-back).
- **Edge**: the window opens before the reliability chart computes — the relay claims the window opened, never the data's readiness.

## Verification surface

Window presence: an mmc window titled "Performance Monitor" in the interactive session (perfmon.msc's title regardless of the `/rel` view).
