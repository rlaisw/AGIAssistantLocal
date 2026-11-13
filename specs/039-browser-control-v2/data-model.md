# Data Model: Browser Control v2 (spec 039)

**Spec**: 039 | **Date**: 2026-11-13 | Inherits 037; no persistent new entities.

## ActionResult (per verb call, ephemeral)

| Field | Type | Rules |
|---|---|---|
| status | ok \| error \| ask-back | ask-back = element/option not found (FR-011); error = engine/transport failure (honest envelope, FR-015) |
| verified | bool | read-back result (FR-009); false on mismatch → error with the mismatch named |
| summary | str | one-line honest report of the effect (masked for sensitive fields) |
| screenshot | ref | the after-action capture (best-effort; always attempted, never fails the action) |
| audit | row | operation `browser-<verb>-v2`, conversation_id, decision, duration_s |

## Verb payloads (validated at the tool boundary)

| Verb | Payload | Boundary rules |
|---|---|---|
| select | target (field description), option (visible label) | non-empty both; option matched by label → value fallback; no match → ask-back listing options |
| type | target, text (literal, any field incl. sensitive) | text exactly as the user provides; verified by displayed read-back |
| form | fields: {target: value} (literal) | ≥1 field; each per-type rules; partial failure reports per-field results honestly |
| press-key | key (Enter/Escape/Arrow*/Tab) | allowlist of key names |
| tabs | action: list/switch/open/close, target? | one action per call |
| wait | condition: text-appears or navigation, text?, bound_s (default 10, max 30) | bounded; timeout → honest error with what was waited for |

## Validation rules (testable)

- No match on target/option → ask-back naming the page's actual elements/options (never a best-guess).
- Field read-back compares DISPLAYED value (the doc/numeric lessons).
- Sensitive values never appear in `summary`, audit `outcome`, or error text.
- Every call audits; unavailable engine → recovery-hint envelope.

## Relationships

```
BrowserWorkflow (a chat turn) 1──* ActionResult  (per verb, in order)
ActionSet (click/select/type/...) *──1 engine tool (1:1 mapping, R1)
AuditRecord 1:1 every verb (operation per verb)
```