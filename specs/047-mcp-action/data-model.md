# MCP-Action — Data Model

**Spec**: [spec.md](spec.md)
**Research**: [research.md](research.md)

## Entities

### GuidedProcedure (ephemeral)

| Field | Rule |
|---|---|
| `request` | The user's own Office/Windows how-to request; research and desktop content cannot supply action parameters |
| `domain` | `windows`, `word`, `excel`, `powerpoint`, `outlook`, or other; only supported domains can receive an offer |
| `manual_steps` | Tailored instructions remain available regardless of automatic-action support |
| `action_id` | Optional; only a reviewed action ID makes the procedure eligible for `mcp_action` draft |

### PendingProposal (in memory, one per conversation)

| Field | Type / validation |
|---|---|
| `proposal_id` | Random identifier for internal correlation; not a screenshot capability |
| `conversation_id` | Required non-empty Dify conversation ID; lookup is conversation-scoped |
| `action_id` | `windows_default_printer` or `word_printer_duplex` |
| `parameters` | Closed, validated parameter object described below |
| `effect` | Server-generated plain-language change and display disclosure; caller text is never stored as executable content |
| `created_dialogue_count` | Integer `N` from Dify; confirm/cancel requires exactly `N+1` |
| `created_at_utc` | Wall-clock timestamp for audit/display only |
| `expires_at_monotonic` | Creation + 900 seconds; age/authorization checks use the injected monotonic clock |
| `status` | Conceptually `pending`; terminal/resolved proposals are removed from the active store |

The active store holds no screenshot bytes, raw chat history, document names, or executable command text. A newer draft atomically supersedes the prior proposal. Every state operation opportunistically removes expired proposals so abandoned conversations cannot accumulate stale entries. The store is intentionally ephemeral: sidecar restart fails closed with no pending proposal.

### Action parameters

| Action | Closed parameter schema |
|---|---|
| `windows_default_printer` | `printer: string` — trimmed, non-empty, no NUL/CR/LF, bounded length; must resolve to exactly one installed printer by case-insensitive exact comparison |
| `word_printer_duplex` | `printer: string` with the same rule, plus `orientation: "long-edge" \| "short-edge"` mapped only to `TwoSidedLongEdge` or `TwoSidedShortEdge` |

Unknown keys are rejected. The server never accepts PowerShell, UI steps, COM code, a caller-authored effect, or a replacement target on confirm/cancel.

### ActionResult (returned to the agent)

| Field | Rule |
|---|---|
| `status` | `pending-confirmation`, `ask-back`, `unsupported`, `cancelled`, `ok`, `partial`, `blocked`, `queued-timeout`, or `error` |
| `action_id` | Present for a recognized reviewed action |
| `effect` / `offer` | Draft only; offer is exactly `Do you want me to do it automatically for you?` |
| `changed` | Execution only; true only when before and after states differ in the requested direction |
| `before` / `after` | Sanitized printer/default/duplex values needed for the report; no document or desktop contents |
| `verification` | `verified`, `mismatch`, `unavailable`, or `not-run`; success requires `verified` |
| `display` | `{status, reason?}` where status is `displayed`, `partial`, `unverified`, `attempted-but-failed`, or `skipped` |
| `screenshot` | `{status, capture_scope, image_url?, expires_in_s?, region_fallback?, reason?}`; `image_url` exists only when status is `captured`; `capture_scope` is `foreground-window` or `full-display`, and `region_fallback` is present only after a regional capture error |
| `timing` | `{queue_wait_s, execution_s, total_s, display_s, screenshot_s}`; queueing is never hidden inside execution time, and display/capture timings are `null` when those stages were not attempted |
| `error` / `reason` | Bounded sanitized explanation; no raw CLIXML, credentials, executable payload, or unconstrained stderr |

An already-active target returns `ok`, `changed:false`, and `verification:"verified"`. A verified setting with display or screenshot failure returns `partial`. A mismatch or unknown mutation outcome never returns success.

### ScreenshotArtifact (private and temporary)

| Field | Rule |
|---|---|
| `token` | `secrets.token_urlsafe(32)`; exactly 43 URL-safe characters; used only for temporary delivery and redacted from logs |
| `bytes` | Exactly one decoded PNG/JPEG image, magic-byte validated, maximum 10 MiB; never returned to Dify or written to audit |
| `mime_type` | Determined/validated as `image/png` or `image/jpeg` |
| `path` | Private dedicated container `/tmp` directory; mode `0600`, parent `0700`; never exposed in the tool result |
| `created_at` / `expires_at` | Absolute 900-second lifetime; GET does not renew it |
| `public_url` | Derived from the established sidecar public base URL; appears only in the captured screenshot result and expires with the artifact |

A janitor sweeps every 30 seconds; startup/shutdown removes leftovers. Browser/PDF pixels already delivered to the user are outside server retention control.

### AuditEvent (existing append-only audit)

Records `operation="mcp-action"`, `conversation_id`, `phase`, `action_id`, sanitized outcome/reason, duration, queue/execution/display/capture timing, and refusal/error status. It never records raw query text beyond the classified decision, screenshot bytes/tokens/URLs/paths, document names, desktop text, or executable script payloads.

## Lifecycle and transitions

```text
none ──draft──> pending
pending ──new draft──> superseded (removed)
pending ──plain no/cancel on next turn──> cancelled (removed)
pending ──modified response / intervening turn──> invalidated (removed)
pending ──age >= 900 seconds──> expired (removed)
pending ──valid plain yes on next turn──> reserved/executing (atomically removed from confirmable store)
executing ──verified, display + screenshot succeeded──> ok
executing ──verified, later evidence stage failed──> partial
executing ──no remaining budget──> queued-timeout (no execution)
executing ──verification mismatch / unavailable / exception──> error
```

A wrong-conversation confirmation does not remove the real proposal. Two simultaneous confirmations for one proposal produce at most one reservation. Resolved proposals cannot be executed by a later yes.

## Concurrency and integrity invariants

1. A short state lock protects dictionary lookup + reservation/removal and is never held across `await`.
2. One server-wide desktop `asyncio.Lock` covers before-read, mutation, after-read, display verification, and capture.
3. Draft and cancel do not acquire the desktop lock.
4. An action starts only when its complete 60/90-second reviewed budget remains inside the 240-second total budget.
5. The desktop lock is not released while an underlying host operation may still be running.
6. Only captured screenshots receive a URL; no URL means the agent must not emit an image.
