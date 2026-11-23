# System Health Check — Data Model

**Spec**: [spec.md](spec.md)
**Research**: [research.md](research.md)

## Entities

### HealthCheckProposal

| Field | Rule |
|---|---|
| `action_id` | Exactly `system_health_check` |
| `parameters` | Must be `{}`; any key is rejected |
| `conversation_id` | Required Dify conversation; proposal lookup is conversation-scoped |
| `created_dialogue_count` | Integer `N`; confirm/cancel requires exactly `N+1` |
| `created_at_utc` | Audit/display only |
| `expires_at_monotonic` | Creation + existing 900 seconds |
| `effect` | Fixed read-only diagnostic disclosure: report link, Reliability Monitor, no repair, HelpDesk guidance only |

No host call, script run, display, or screenshot occurs during draft. A newer draft supersedes an older proposal; resolution follows the existing reviewed-action state machine.

### HealthCheckResult

| Field | Rule |
|---|---|
| `status` | `pass`, `warn`, `fail`, or `unknown`; derived from validated check statuses, never trusted from the host |
| `score` | Integer 0–100 recomputed as `max(0, 100 - 15*fail - 5*warn)` |
| `counts` | Non-negative integers for `pass`, `warn`, `fail`, `info`, `skip`; must sum to check count |
| `confidence` | `high`, `reduced`, or `low`; skips/info or unavailable core data prevent `high` |
| `checks[]` | `{id, area, name, status, detail, recommendation?}` with bounded string lengths; status is `pass|warn|fail|info|skip` |
| `reliability` | Recent failure summary, records, and daily failure/informational buckets; unavailable data is explicit, not empty-as-pass |
| `events` | Bounded System/Application error context; unavailable data is explicit |
| `inventory` | Owner-approved computer/user/hardware/password-expiry fields for the report; summary extraction may include only bounded values |
| `report` | Report publication outcome, complete `html`, host file path (`%LOCALAPPDATA%\Temp\selfcheck.html`, visible reference when written), and temporary URL (internal fallback) |

The action result includes the complete HTML report for verbatim chat output and the host file path; the audit remains summary-only and must never contain the HTML, URL, or token.

### ReportArtifact

| Field | Rule |
|---|---|
| `status` | `published` or `failed` |
| `report_url` | Present only when published; `http(s)` origin + `/mcp-action/reports/<43-char-token>` |
| `expires_in_s` | `900` when published |
| `reason` | Sanitized failure reason when not published; no path/token/HTML |
| `token` | 256-bit URL-safe capability; exactly 43 characters; never audited/logged |
| `html` | One self-contained HTML document, UTF-8, max 5 MiB, no active content/external resources beyond data-URI images and inline style |
| `stored_at` / `expires_at` | Absolute wall-clock lifetime; GET does not renew |

The report may display the owner-approved login, email, IP, hardware/serial, password-expiry, event-log, and crash/reliability fields. Those fields never enter the audit or persistent server logs.

### CheckRecord

| Field | Rule |
|---|---|
| `id` / `area` / `name` | Bounded identifying values; shown in report and summary selection |
| `status` | `pass|warn|fail|info|skip`; `skip` means unavailable/restricted, never pass |
| `detail` | Bounded, HTML-escaped host text |
| `recommendation` | Optional bounded remediation text; HelpDesk guidance may use it, but no repair executes |

### ReliabilityEvidence

| Field | Rule |
|---|---|
| `available` | True only when reliability data was actually read |
| `records[]` | Recent crash/hang/Windows-failure records, correlated event count, bounded messages |
| `summary` | Last 24h/7d counts, last failure, top products |
| `timeline[]` | Daily failure/informational counts and product labels for the report graph |

Unavailable/empty reliability data is explicit and affects `confidence`/summary; it never creates fabricated records.

### HelpDeskReferral

A guidance-only object/text inside the action result: affected areas and the statement that HelpDesk can help with repairs. It is not a ticket, task, tool invocation, or repair action.

### AuditEvent

Existing summary-only append-only audit: operation `mcp-action`, conversation ID, action ID, phase/decision, `health=<status>:score=<n>:pass=…:warn=…:fail=…:skip=…:confidence=…`, `report=published|failed|skipped`, display/screenshot status, timings, and sanitized error/reason. It never stores report URL/token/path/HTML, login, email, IP, serial, password-expiry detail, event text, crash text, or credentials.

### HostRunArtifacts

| Field | Rule |
|---|---|
| `run_id` | Server-generated lowercase 32-hex token; not model-controlled |
| `script_path` | Fixed `C:\ProgramData\agentic-rag\health\health-check.ps1`; hash pinned |
| `json_path` | Fixed-run JSON under the fixed report directory |
| `html_path` | Fixed-run self-contained HTML under the fixed report directory |
| lifetime | Created only after confirmed execution; copied into the temporary report store; only those run artifacts are cleaned afterward |

## Lifecycle

```text
none ──draft (no host action)──> pending
pending ──valid next-turn yes──> executing (removed from confirmable store)
executing ──valid summary + report + display + screenshot──> ok
executing ──valid summary + partial report/display/screenshot──> partial
executing ──host failure/malformed data/timeout──> error (or queued-timeout without execution)
pending ──no/cancel/modified/stale/expired──> removed without execution
report published ──900 seconds──> expired/deleted; route 404
```

`health.status=pass|warn|fail` describes the machine, not the action lifecycle. A successful diagnostic with warnings/failures is still action `ok`. `verification="reported"` means a valid structured report was parsed; it is not a settings read-back.

## Validation and invariants

1. Health parameters are exactly `{}`; any other key is rejected before host access.
2. Host JSON and HTML are untrusted input: type/shape/size/enum checks, no NULs, bounded arrays/strings, and HTML escaping/active-content rejection.
3. Counts/score/overall/confidence are recomputed from validated checks; host-supplied values cannot create a pass.
4. Action success is independent of machine health, report success, display success, and screenshot success.
5. Report URL and token are capability secrets: 43 characters, no long-term audit/log copy, 900-second absolute TTL.
6. Only one health action executes per desktop at a time under the existing lock; duplicate confirmations cannot execute twice.
7. No credential fields are accepted or rendered.
8. Host script hash mismatch, missing file, unsupported OS, or read failure fails closed.
