# Contract: `system_health_check` Reviewed Action

## Action identity

| Field | Rule |
|---|---|
| `action_id` | Exactly `system_health_check` |
| `parameters` | Must be `{}`; any key is rejected |
| Tool | Existing `mcp_action`; no new MCP tool |
| Mode | Read-only diagnostic |
| Budget | 180 seconds, inside the 240-second total |
| Lanes | General-cloud and Hermes only |

## Eligibility and draft

Eligible when the user reports Windows 11 instability—freezes, hangs, application crashes, BSODs—and asks for diagnosis, or explicitly requests a system health check. Missing critical symptom context triggers one or two ask-first questions and ends that turn.

Draft request:

```json
{
  "phase": "draft",
  "conversation_id": "conv-123",
  "dialogue_count": 4,
  "query": "",
  "action_id": "system_health_check",
  "parameters": {}
}
```

Draft response:

```json
{
  "status": "pending-confirmation",
  "action_id": "system_health_check",
  "effect": "Run a read-only desktop health check, publish a temporary report, and display Reliability Monitor. The check does not repair or change the system; HelpDesk can help with repairs.",
  "notice": "Please wait about 2-5 minutes and do not use the keyboard or mouse during System-Self-Check is running\nuntil the report is finished",
  "offer": "Do you want me to do it automatically for you?",
  "expires_in_s": 900,
  "caveats": ["The report may contain sensitive system and reliability details."]
}
```

Draft performs no host call, scripting, diagnostic, display, or screenshot. The agent supplies tailored manual guidance (or concise explicit-request guidance) and the exact final-paragraph offer.

## Confirm

Plain yes on the immediately following `N+1` turn executes the stored action. Confirm/cancel accept no replacement action, parameters, code, path, or target. Modified, unrelated, expired, repeated, orphaned, or wrong-conversation responses fail closed under the existing reviewed-action rules.

## Success result

```json
{
  "status": "ok",
  "action_id": "system_health_check",
  "changed": false,
  "verification": "reported",
  "health": {
    "status": "warn",
    "score": 72,
    "counts": {"pass": 8, "warn": 3, "fail": 1, "info": 2, "skip": 2},
    "confidence": "reduced"
  },
  "report": {
    "status": "published",
    "report_url": "http://localhost:28080/mcp-action/reports/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "expires_in_s": 900,
    "usage": "When host_path_status is written, present Complete report file: <host_path> once and do not include a /mcp-action/reports/ URL. The complete report is returned in report.html and is appended verbatim by the finalizer. A temporary link may be used once only when no host file was written."
  },
  "display": {"status": "displayed"},
  "screenshot": {"status": "captured", "capture_scope": "foreground-window", "image_url": "http://localhost:28080/mcp-action/screenshots/BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB", "expires_in_s": 900},
  "caveats": [],
  "timing": {"queue_wait_s": 0.0, "execution_s": 96.4, "total_s": 96.4, "display_s": 1.2, "screenshot_s": 0.5}
}
```

`verification:"reported"` means a valid structured diagnostic result was parsed; it is not a settings read-back. `health.status` describes the machine and does not determine action success. `changed` is always false.

## Status semantics

| Layer | Values |
|---|---|
| action `status` | `ok`, `partial`, `error`, `blocked`, `queued-timeout`, plus existing draft/cancel statuses |
| `health.status` | `pass`, `warn`, `fail`, `unknown` |
| `confidence` | `high`, `reduced`, `low` |
| `report.status` | `published`, `failed`, `skipped` |
| `display.status` | `displayed`, `partial`, `unverified`, `attempted-but-failed`, `skipped` |
| `screenshot.status` | `captured`, `attempted-but-failed`, `skipped-display-unverified`, `skipped` |

`ok` requires a valid summary and successful report, display, and screenshot stages. A valid summary with report/display/screenshot failure is `partial` and retains the summary. A host failure, missing/malformed JSON, unsupported OS, hash mismatch, or timeout is `error`. A `health=fail` result with successful evidence is still action `ok`.

## HelpDesk boundary

For warnings, failures, or recurring crashes, name the affected areas and state that HelpDesk can help with repairs. Do not call `task_helpdesk_tier1`, `task_helpdesk_tier2`, create a ticket, route a repair, or claim a repair/HelpDesk request occurred. Ordinary guidance text is allowed.

## Evidence and audit

- The report URL is published only when the HTML is valid and stored; it is returned once in chat and expires after 900 seconds.
- Reliability Monitor is launched once, verified, fronted, and captured; display and screenshot outcomes are independent.
- Chat returns the bounded health summary and report link; it never dumps the HTML.
- Persistent audit receives only `health=<status>:score=<n>:pass=…:warn=…:fail=…:skip=…:confidence=…`, `report=published|failed|skipped`, display/screenshot statuses, and timings. It never receives report URL/token/path/HTML, login, email, IP, serial, password-expiry detail, event text, crash text, or credentials.
- Report contents may include the owner-approved fields; logging/audit redaction does not apply to the HTML itself.

## Dify wiring

- Add the action and no-parameter rules to both approved prompts and tool descriptions.
- The exact offer requires a real pending result; health execution/report/display/screenshot claims require corresponding tool evidence.
- A published report URL is accepted only if returned by the tool; if omitted, append it once deterministically.
- On health turns, override the ordinary task-gateway “system issues first call tier-1” rule; HelpDesk is guidance-only. A later explicit repair request follows normal HelpDesk routing.
- Do not register the action on General-local or PPT-Master.
