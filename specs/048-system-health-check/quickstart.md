# System Health Check — Validation and Test Plan

**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)
**Contracts**: [action](contracts/system-health-check.md) · [report route](contracts/report-route.md) · [host script](contracts/host-health-script.md)

## 1. Policy and safety

1. **Red first**: add each deterministic test before its implementation and verify it fails for the expected missing behavior.
2. **Read-only invariant**: the health action may write only its own JSON/HTML run artifacts. It must never change settings, registry, services, applications, files outside those artifacts, or perform repairs.
3. **Credentials**: never ask for, collect, type, render, or store passwords, MFA codes, tokens, client secrets, or other credentials.
4. **Owner-approved report content**: the HTML report may display login, email, IP, hardware/serial, password-expiry, event, and crash/reliability data. Do not redact the report itself.
5. **Persistent privacy**: report URL/token/path/HTML and PII must not enter audit records or persistent logs. Tokens are redacted in access logs.
6. **Owner-present live checks**: health execution opens Reliability Monitor and captures the desktop. Run live confirm checks only with the owner present and a disposable diagnostic machine/account.
7. **No HelpDesk mutation**: the health action and its follow-up guidance must not call `task_helpdesk_tier1/2`, create a ticket, or execute a repair.
8. **Temporary artifacts**: report URL expires in 900 seconds; host JSON/HTML run artifacts are cleaned after publication; no test waits 15 real minutes (use fake clocks).

## 2. Prerequisites and pre-implementation probes

- Python venv, sidecar/Dify/Windows-MCP/Office gateway healthy, interactive Windows 11 desktop.
- Read-only probe that `C:\ProgramData\agentic-rag\health` is writable by the deploy/user context and `/mnt/c/ProgramData/...` casing works.
- Probe the fixed wrapper with a disposable run ID:
  - script SHA-256 is found and checked;
  - JSON and HTML are created;
  - stdout marker is <4,000 characters;
  - Reliability Monitor is **not** launched by the script;
  - a forced child timeout kills only the health child.
- Probe Reliability Monitor display: verified title “Performance Monitor”, reliability text/Snapshot fallback, App switch, and screenshot.
- Probe the report route public origin, headers/CSP, token redaction, and expiry with a fake clock.
- Probe Dify health draft/cancel in General-cloud and Hermes; confirm no HelpDesk tool call on a health turn.

If any external shape differs, update research/contracts before implementing dependent code.

## 3. Unit test matrix

### Proposal, consent, and action state

| ID | Case | Expected |
|---|---|---|
| H-U01 | Create `system_health_check` with `{}` | Valid pending proposal; no host effect |
| H-U02 | Supply any health parameter (`printer`, `foo`, or a non-empty list) while `parameters=None`/`{}` is treated as empty | Non-empty parameters rejected/error; no host effect |
| H-U03 | Draft health proposal | No script, display, screenshot, or report call |
| H-U04 | No/cancel/modified/orphan/repeated/wrong-turn/expired confirmation | Existing fail-closed behavior; no execution |
| H-U05 | New health draft / two conversations / duplicate confirmation | Supersession/isolation/atomic single execution preserved |

### Host script and wrapper

| ID | Case | Expected |
|---|---|---|
| H-U06 | Source script hash pin | Repo file hash equals constant; edited file without pin update fails |
| H-U07 | Script inspection | No mutating verbs, no `Start-Process`, no repair/credential commands; only read queries + own artifacts |
| H-U08 | Fixed wrapper | Validates 32-hex run ID; fixed script/output paths; no model interpolation |
| H-U09 | Wrapper success | JSON/HTML paths, small marked status, exit status; no large text through `call_tool` |
| H-U10 | Child timeout/launch failure | Honest timeout/error; only health child killed; no retry of unknown state |
| H-U11 | Hash mismatch/missing script/output dir | Error before diagnostic; no report/score |
| H-U12 | Missing/malformed/truncated/NUL/oversized JSON | Error; no summary/report claim |
| H-U13 | Missing/invalid/truncated/oversized HTML | Summary may remain; report failed/partial |
| H-U14 | UTF-8/BOM, bounded arrays/strings, required sections | Accepted only within caps; oversized values rejected |
| H-U15 | Read-only artifact cleanup | Removes only exact `<runId>.json/html`; never user files; cleanup failure sanitized |

### Health normalization

| ID | Case | Expected |
|---|---|---|
| H-U16 | Counts/score/overall from host claims | Python recomputes from checks; inconsistent host values ignored |
| H-U17 | pass/warn/fail/info/skip statuses | Overall = fail > warn > pass > unknown; `skip` never becomes pass |
| H-U18 | Skipped/unavailable core checks | Confidence reduced/low; no “complete coverage” claim |
| H-U19 | Reliability unavailable/empty | Explicit skipped/empty state; no invented records |
| H-U20 | Malformed types/negative counts/count mismatch | Error or safe normalized subset; never fabricated pass |
| H-U21 | Credential-like or unknown fields | Not rendered/accepted; no secrets in result/audit |
| H-U22 | Owner-approved PII fields | Allowed in report only; absent from chat summary unless explicitly needed; absent from audit |

### Report store and publisher

| ID | Case | Expected |
|---|---|---|
| H-U23 | Token format | 256-bit URL-safe 43-character token |
| H-U24 | HTML validation | Complete document, UTF-8, ≤5 MiB; reject NULs/truncated/active content/external resources |
| H-U25 | Storage modes | Directory `0700`, file `0600`, no symlink/traversal |
| H-U26 | TTL 899.99/900/900.01 with fake clock | Accepted/expired boundary exact; GET does not renew |
| H-U27 | Publisher success/failure | URL only on success; sanitized generic failure; no path/token leak |
| H-U28 | Cleanup | Idempotent, skips symlinks, removes only owned expired reports |
| H-U29 | HTML escaping/injection | `<script>`, `<iframe>`, quotes, `&` in host text are escaped; no active content |

### Service orchestration and evidence

| ID | Case | Expected |
|---|---|---|
| H-U30 | Health confirm success | Summary + report URL + Reliability Monitor + screenshot in one execution |
| H-U31 | Health `fail` with successful evidence | Action `ok`; health `fail`; HelpDesk guidance |
| H-U32 | Report publish failure | Action `partial`; summary retained; no report URL |
| H-U33 | Display failure | Action `partial`; report retained; screenshot skipped |
| H-U34 | Screenshot failure | Action `partial`; report/display remain |
| H-U35 | Timeout/queue boundary | Full 180s must remain (`queue_wait<=60`); timeout/partial honest; no execution on queued-timeout |
| H-U36 | Stage budget exhaustion | Skip lower-priority evidence; `budget_exhausted`; no fabricated success |
| H-U37 | Transport/host exception | Sanitized `error`; no partial OK; no blind retry |
| H-U38 | Reliability Monitor exactly once | One launch attempt, verified title; no relaunch after failure |
| H-U39 | Audit privacy | Only health status/score/counts/confidence, report published/failed, display/screenshot, timing; no URL/PII/HTML |
| H-U40 | HelpDesk boundary | No task-helpdesk call/ticket/repair; guidance text only |
| H-U41 | Locking/concurrency | One desktop action; duplicate/parallel health requests serialized or blocked |
| H-U42 | Unsupported OS; non-elevated/supported-but-restricted checks | Unsupported OS is an honest error/no offer; restricted checks are explicit skip/info; no fabricated pass |

### Dify DSL and logging

| ID | Case | Expected |
|---|---|---|
| H-U43 | Prompt eligibility | Instability or explicit health request only; other/direct unsupported no offer |
| H-U44 | Ask-first/manual/exact offer | Context questions first; manual or concise guidance; exact final paragraph; no draft before |
| H-U45 | Health action parameters | No parameters; `action_id=system_health_check` only |
| H-U46 | HelpDesk conflict | Health prompt overrides tier-1/tier-2 automatic routing for this turn; later repair request normal |
| H-U47 | Report/score/display honesty | Real evidence allowed; forged report URL/score/display/repair/HelpDesk request blocked; missing published URL appended once |
| H-U48 | Approved lanes | Present in General-cloud/Hermes; absent General-local/PPT; exact offer still gated by pending proposal |
| H-U49 | Log redaction | `/mcp-action/reports/<43>` token masked; screenshot/other redactions unchanged |
| H-U50 | Existing reviewed-action regressions | Printer/duplex, yes/newline bindings, MCP schemas and skill replay unchanged |

## 4. Contract tests

| ID | Contract | Expected |
|---|---|---|
| H-C01 | Existing MCP tool surface | Still one `mcp_action` tool; action_id remains free string; no new tool/cache count |
| H-C02 | Report route success | Exact HTML bytes, MIME, no-store/CSP/no-referrer/no-CORS; no ETag/Last-Modified |
| H-C03 | Report route failures | Malformed/unknown/expired indistinguishable 404; non-GET 405 + `Allow: GET`; no leakage |
| H-C04 | Route isolation | Report token cannot fetch a screenshot and vice versa |
| H-C05 | Report expiry/repeat | Repeated GET allowed/no renewal; expiry deletes/404; janitor/startup cleanup |
| H-C06 | Host script staging | Deploy copies exact bytes/hash, fails closed on mismatch, no new MCP tool |
| H-C07 | HTML content | No active content/external resources; escaping and size caps |
| H-C08 | Audit/log serialization | No report URL/token/path/HTML/PII/event/crash text in persistent artifacts |

## 5. Dify live contract tests

Run only with `RUN_MCP_ACTION_DIFY_CONTRACT=1`.

| ID | Case | Expected |
|---|---|---|
| H-D01 | Health draft in General-cloud and Hermes | `action_id=system_health_check`, parameters empty, raw query/turn/conversation exact, pending offer; no host side effect |
| H-D02 | Immediate cancel | Cancelled; zero host calls |
| H-D03 | HelpDesk override | Health turn contains guidance, no `task_helpdesk_*` tool call/ticket/repair claim |
| H-D04 | Report/display evidence guard | Forged report URL/score/display/repair blocked; real report link preserved/appended |
| H-D05 | Existing newline/yes binding regression | Unchanged for printer/duplex; health prompts do not reintroduce template-constant binding |

## 6. Owner-present live E2E matrix

Use an opt-in flag such as `RUN_SYSTEM_HEALTH_CHECK_E2E=1`; do not include in normal CI.

| ID | Scenario | Expected evidence |
|---|---|---|
| H-E01 | Explicit direct health request, decline | Concise guidance + exact offer; no script/report/monitor/screenshot; proposal discarded |
| H-E02 | Instability narrative with missing context | One/two targeted questions; no check/offer in ask-back turn |
| H-E03 | Out-of-scope or non-Windows request | Existing behavior/manual only; no health offer |
| H-E04 | Accept health check on Windows 11 | Read-only diagnostic succeeds; summary/score/counts/reliability; temporary report URL opens; Reliability Monitor visible; screenshot; no repair |
| H-E05 | Warning/failure findings | Action `ok`, health warn/fail; HelpDesk guidance; no task-helpdesk call/ticket/repair |
| H-E06 | Report publication failure (injected store failure) | Action `partial`; summary retained; no report URL; honest report failure |
| H-E07 | Reliability display failure (injected/observed) | Action `partial`; report remains; display unverified; screenshot skipped |
| H-E08 | Screenshot failure (injected/observed) | Action `partial`; report/display remain |
| H-E09 | Host offline/hash mismatch/missing script | Sanitized error; no diagnostic/report; no retry/repair |
| H-E10 | Malformed/truncated JSON or HTML | Sanitized error/partial; no fabricated score/report |
| H-E11 | Child timeout/budget exhaustion | Honest timeout/partial; no infinite wait; other injection lanes preserved |
| H-E12 | Report URL expiry/fake clock + token | Before expiry 200; after 900s 404; token absent from logs/audit; host artifacts cleaned |
| H-E13 | Read-only invariant | Default printer/duplex, services, registry, files other than tool artifacts unchanged; no Office/document changes; no HelpDesk mutation |
| H-E14 | Duplicate/parallel requests | One execution; second blocked/queued-timeout honestly; no duplicate report/monitor |
| H-E15 | Report URL rendered in chat | Link opens new tab; no HTML dumped; no image proxy; 15-minute warning present |
| H-E16 | Privacy scan | Audit/logs contain summary/status only; no login/email/IP/serial/password-expiry/event/crash text; report itself retains owner-approved fields |

## 7. Error-handling matrix

| Stage | Injection | Required behavior |
|---|---|---|
| Draft | Parameter supplied | Error/ask-back; no host call |
| Health execution | Missing script/hash mismatch | Error; no offer/execution |
| Health execution | USER_CONTROL/exhausted consent | Blocked/deferred; no report/score |
| Wrapper | Child timeout | Kill child; timeout/error or partial if valid files already produced |
| Files | Missing JSON | Error; no summary/report |
| Files | Malformed/truncated JSON | Error; no fabricated result |
| Files | Missing/invalid HTML | Summary may return; report failed/partial |
| Parser | Invalid types/count mismatch | Recompute or error; no pass fabrication |
| Report store | Oversize/invalid/active HTML | Publication failed; no URL |
| Report store | Disk failure | Sanitized publication failure; summary retained |
| Display | Already open/launch fails/verification fails | One launch/verified result or partial; no relaunch loop |
| Screenshot | No image/malformed/oversize | Partial; report/summary retained |
| Budget | Stage exceeds remaining 180/240 | Partial/budget-exhausted; skip lower-priority stage |
| Evidence route | Expired/bad token/non-GET | 404 indistinguishable or 405; no leakage |
| Audit | Serialization failure | Do not alter honest host outcome; sanitized event/error |
| Cleanup | Host artifact removal fails | URL still expires; sanitized warning; no unrelated deletion |

## 8. Performance, privacy, and acceptance traceability

- **SC-001**: H-U43–H-U45, H-D01, H-E01–H-E03.
- **SC-002**: H-U04, H-D02, H-E01, H-E14.
- **SC-003**: At least 20 owner-present full health runs; at least 19/20 (95%) action-ok with report URL + verified display within 180s; queue wait reported separately. Record false/timeout samples honestly.
- **SC-004**: H-U16–H-U21, H-U30, H-E04, H-E15; report URL resolves before expiry.
- **SC-005**: H-U31/H-U40, H-D03, H-E05; no HelpDesk tool/ticket/repair.
- **SC-006**: H-U23–H-U29, H-C02–C08, H-E12/H-E16; route expiry and audit/log privacy.
- **SC-007**: User-acceptance review of summary/report link (at least 90% correct health result, top reliability finding, next step); formal participant study remains external.

## 9. Commands

From repository root:

```bash
.venv/bin/python -m pytest tests/unit/test_mcp_action_health.py tests/unit/test_mcp_action_reports.py tests/unit/test_mcp_action_state.py tests/unit/test_mcp_action_actions.py tests/unit/test_mcp_action_tool.py tests/unit/test_mcp_action_dsl.py tests/unit/test_mcp_action_concurrency.py tests/unit/test_logging_setup.py -q
.venv/bin/python -m pytest tests/contract/test_mcp_action_report_route.py tests/contract/test_mcp_contract.py tests/contract/test_deploy_cli.py -q
.venv/bin/python -m pytest tests/unit tests/contract -q
```

Dify and live checks:

```bash
RUN_MCP_ACTION_DIFY_CONTRACT=1 .venv/bin/python -m pytest tests/integration/test_mcp_action_dify_contract.py -q -s
RUN_SYSTEM_HEALTH_CHECK_E2E=1 .venv/bin/python -m pytest tests/integration/test_mcp_action_e2e.py -q -s -k health
```

Deploy safely (explicit app IDs; never name-based `deploy all` on this host):

```bash
.venv/bin/python -m agentic_rag_mcp.deploy redeploy
# publish both explicit app IDs, then:
.venv/bin/python -m agentic_rag_mcp.deploy verify
```

Expected: all deterministic checks green; live report URL loads with CSP/no-store; Reliability Monitor visible; no system settings/files (other than tool artifacts) changed; no HelpDesk tool call; original test environment restored.

## 10. Completion evidence and exit criteria

Record:

- unit/contract/Dify/live command results and full-suite count;
- script hash/staging probe, wrapper file/marker/timeout evidence;
- 20-run 180-second performance samples;
- report URL 200/404/header/CSP/token-redaction evidence;
- Reliability Monitor display/screenshot and partial-stage cases;
- audit/log privacy scan;
- read-only before/after evidence and cleanup of host/container report artifacts.

The feature is complete only when all deterministic suites are green, the report route and script contracts pass, owner-present health E2E passes or is explicitly environment-blocked with owner sign-off, and no repair/HelpDesk mutation or PII audit leak remains.
