# Data Model: Windows-MCP lane (040)

The lane is a stateless client; the only persisted data is the shared audit trail. Entities below define the runtime objects and the audit rows the lane produces.

## Entities

### PowerShell/Windows-MCP request (runtime object)
| Field | Type | Notes |
|---|---|---|
| tool | enum | `Process` \| `Clipboard` \| `Notification` \| `Registry` (the service's real surface, R2) |
| args | map | the tool's schema (e.g. `Process`: mode, name, pid, sort_by, limit, force) |
| conversation_id | string | required — every attempt is attributable |

Validation: args validated against the captured tool schemas before dispatch (shape mismatch → blocked, no service call); conversation_id required (audited), mirroring the other lanes.

### Consent record (host-owned, lane-observed)
| Field | Type | Notes |
|---|---|---|
| outcome | enum | approved \| declined \| timed_out \| not_required |
| observed_as | enum | success response \| refusal/timeout envelope \| immediate read success |

Lifecycle: read-only operations observed as `not_required` (verified live); privileged operations show the host user-control prompt; a declined/timed-out consent never produces fabricated output — the refusal envelope is the lane's only state after it.

### Audit row (append-only, shared funnel)
| Field | Type | Notes |
|---|---|---|
| ts | ISO 8601 UTC | |
| decision | enum | executed \| blocked \| error |
| operation | string | `windows-mcp-process` \| `windows-mcp-clipboard` \| `windows-mcp-notification` \| `windows-mcp-registry` \| `windows-mcp-status` |
| conversation_id | string | present on every row (spec 036 T030 contract) |
| reason / outcome | string | the honest envelope text or genuine output summary (bounded) |
| duration_s | float | also feeds the loop-gate classification (operational, non-exempt class) |

## State transitions

request → validated → dispatched → (consent: host-owned) → {success: output relayed + audit executed} | {failure: named envelope + audit error} | {blocked: no service call + audit blocked}

There is no stored per-conversation state beyond the audit row and the loop-gate's operational-class map (already existing machinery; no new state stores).

## Relationships

One request → zero or one consent record → exactly one audit row. The lane adds no new storage, migrations, or retention policy — the audit trail's existing rules apply unchanged.
