# Implementation Plan: System Health Check — Read-Only Desktop Diagnosis

**Branch**: `048-system-health-check` | **Date**: 2026-11-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/048-system-health-check/spec.md`

## Summary

Add `system_health_check` as a third reviewed action inside the existing two-phase `mcp_action` tool. It takes no parameters. After explicit confirmation it runs the supplied read-only Windows diagnostic from a hash-pinned host script, reads the full machine-readable result and HTML report from host files through the existing read-only `/mnt/c` mount, recomputes an honest summary, returns the complete HTML report in the action result for verbatim chat output, writes it to %LOCALAPPDATA%\Temp\selfcheck.html, publishes a temporary copy through a 15-minute capability URL, opens and verifies Reliability Monitor exactly once, and returns temporary screenshot evidence. It never repairs: findings direct the user to HelpDesk guidance only. No new MCP tool, runtime dependency, database, or frontend change is introduced.

## Technical Context

**Language/Version**: Python 3.12+; existing Windows PowerShell 5.1 script on the interactive Windows host

**Primary Dependencies**: Existing FastMCP/Starlette sidecar, `asyncio`, Windows-MCP `PowerShell`/`WaitFor`/`Snapshot`/`Screenshot`/`App` tools, existing `open_settings` Reliability target, existing `mcp_action` proposal/audit/ScreenshotCapture machinery, Dify Chatflow; standard-library `html`, `secrets`, `pathlib`, `json`, `hashlib`; no new dependency

**Storage**: Host script/artifacts under `C:\ProgramData\agentic-rag\health`; container-local temporary HTML report store under `/tmp/agentic-rag-mcp-reports`; no database or durable report archive

**Testing**: `pytest`/`pytest-asyncio`, Starlette contract tests, Dify live draft/cancel contracts, owner-present Windows end-to-end tests, existing Vitest suite for unchanged frontend rendering

**Target Platform**: Single WSL2/Docker sidecar with read-only `/mnt/c` mount, one interactive Windows 11 desktop, current Dify deployment

**Project Type**: Local web-service/chatflow desktop automation with additive reviewed action and HTTP artifact route

**Performance Goals**: At least 95% of successful checks produce a summary, report URL, and verified Reliability Monitor display within 180 seconds; queue wait reported separately

**Constraints**: Strictly read-only diagnostic; no repair/settings/service/registry changes; no credentials; report URL 15-minute TTL; owner-approved PII fields may appear in report but not audit; one desktop-wide execution; no new MCP tool; existing 59-tool surface remains

**Scale/Scope**: One desktop, one health check at a time, fixed diagnostic defaults, two approved assistant lanes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Contract Preservation — PASS**: `system_health_check` is a new value of the existing `action_id` string; no MCP tool or schema is added. The report route is additive and separate from screenshots. Printer/Word behavior and `ask` contracts remain unchanged.
- **Tests-First — PASS**: [quickstart.md](quickstart.md) defines red-first unit, contract, Dify, live E2E, privacy, timeout, and failure-stage checks before implementation; full suite must finish green.
- **Minimal Dependencies — PASS**: Existing infrastructure and stdlib only. The supplied script is staged as a reviewed host asset; no new service or package.
- **Honest Answers — PASS**: Python recomputes score/overall/counts and marks skipped/unreadable checks explicitly. Action success is separate from machine health. Report, display, and screenshot outcomes are independent; raw diagnostics never fabricate a pass or repair.
- **Spec-Driven Replacement — PASS / NOT APPLICABLE**: Additive action; no retired design.
- **Quality Gates — PASS**: 180-second target is measured; failure behavior and stage budgets are explicit; existing suites must stay green.

## Project Structure

### Documentation (this feature)

```text
specs/048-system-health-check/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── system-health-check.md
│   ├── report-route.md
│   └── host-health-script.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 only
```

### Source Code (repository root)

```text
windows/
└── health-check.ps1                 # reviewed read-only diagnostic script

src/agentic_rag_mcp/mcp_action/
├── health.py                        # fixed wrapper, SHA-256 pin, artifact paths, JSON normalization
├── reports.py                       # 15-minute HTML ReportStore + publisher
├── state.py                         # third action, closed empty parameter schema
├── actions.py                       # execute_system_health_check + fixed command builder
├── service.py                       # health draft/execute/evidence/audit, 180s deadline
└── screenshots.py                   # unchanged, reused for monitor evidence

src/agentic_rag_mcp/server.py         # service wiring; mcp_action description

dify/docker/mcp-server/server.py     # report base URL, GET route, CSP headers, janitor
src/agentic_rag_mcp/logging_setup.py # report-token redaction
src/agentic_rag_mcp/server.py        # report publisher injection
src/agentic_rag_mcp/deploy/
├── __main__.py                      # stage host asset during redeploy
└── host_assets.py                   # copy/hash check for the Windows script
dify/AGIAssistant/AGI_Assistant.yml  # approved-lane prompts, tool descriptions, honesty guard
src/agentic_rag_mcp/deploy/battery.py# report-route honest-error smoke

tests/
├── unit/
│   ├── test_mcp_action_state.py
│   ├── test_mcp_action_actions.py
│   ├── test_mcp_action_tool.py
│   ├── test_mcp_action_dsl.py
│   ├── test_mcp_action_concurrency.py
│   ├── test_mcp_action_health.py
│   ├── test_mcp_action_reports.py
│   ├── test_logging_setup.py
│   ├── test_deploy_docker_ops.py
│   └── test_deploy_cli.py
├── contract/
│   ├── test_mcp_action_report_route.py
│   ├── test_mcp_contract.py
│   └── test_deploy_cli.py
└── integration/
    ├── test_mcp_action_dify_contract.py
    └── test_mcp_action_e2e.py
```

**Structure Decision**: Keep the action and host-script logic in the existing `mcp_action` package. A small independent `reports.py` mirrors the proven screenshot store. Extend only the approved Dify agents. No frontend production change is needed because the chat renderer already opens Markdown links in a new tab.

## Implementation Sequence

1. **Tests and live contract probes**: Add failing unit/contract/DSL tests for the third action, report store/route, hash pin, malformed payloads, budget, display, honesty, and audit privacy. Probe script staging permissions, wrapper output/file shapes, and the Reliability Monitor title/text condition before enabling execution.
2. **Host script and fixed wrapper**: Add the reviewed script; stage it to `C:\ProgramData\agentic-rag\health\health-check.ps1` with SHA-256 verification; build a fixed wrapper that checks the hash, runs the script with `-NoReliabilityMonitor` under a 120-second child-process deadline, captures stdout to `health-<runId>.json`, verifies/creates `health-<runId>.html`, emits a bounded marker, and cleans only its own old run files.
3. **State and execution**: Add the empty-parameter allowlist entry; draft stores no host effects; confirm executes the stored action. Read JSON/HTML from `/mnt/c/ProgramData/...`; validate UTF-8 JSON and HTML, recompute score/overall/counts/confidence, and reject oversized/malformed/truncated data.
4. **Report publication and privacy**: Implement the 15-minute report store/publisher and route with no-store, CSP sandbox, no CORS, exact token grammar, startup/janitor cleanup, and log redaction. Remove host JSON/HTML run artifacts after successful copy; never expose path/token/report content in audit.
5. **Display and evidence**: Open Reliability Monitor once, verify the window, front it, and reuse ScreenshotCapture. Report summary, report URL, display, and screenshot outcomes separately.
6. **Action budget and outcomes**: Add the 180-second health budget and a stage deadline; keep the 240-second total, 60-second default, and 90-second Word budgets unchanged. Return `ok` for successful diagnostic/evidence even when machine health is `warn`/`fail`; use `partial` for report/display/capture failures.
7. **Dify and honesty**: Add health prompt guidance to General-cloud and Hermes only; enforce no-parameter draft, explicit next-turn confirm/cancel, no HelpDesk tool call, no repair, report-link evidence, and no fabricated score/display/report. Add live Dify draft/cancel and opt-in confirm acceptance.
8. **Deploy and validate**: Extend host staging/deploy battery without adding an MCP tool; run full deterministic suites, deploy safely by explicit IDs, then owner-present live health checks and report-URL/expiry/privacy acceptance.

## Error-Handling Design

| Stage | Condition | Required result and side-effect policy |
|---|---|---|
| Draft | Any parameter supplied, unsupported phase/action, wrong conversation | Bounded `error`/`ask-back`; no host call, diagnostic, display, or screenshot |
| Draft | Host script missing/hash mismatch or unsupported OS | Report readiness failure honestly and do not offer an executable proposal until corrected |
| Confirm | No proposal, wrong turn, modified/repeated/orphan/expired response | Existing fail-closed behavior; no execution |
| Queue | Full 180-second budget unavailable inside 240 seconds | `queued-timeout`; proposal consumed; no host call |
| Host run | Script missing, hash mismatch, execution policy denied, service offline, child timeout | Sanitized `error`; no fabricated health result; kill only the timed-out child; no retry of an unknown mutation |
| Host output | Missing/small marker, missing JSON/HTML, malformed/truncated/oversized data | Sanitized `error`; no summary/report; files may be left only for diagnosis and must not be exposed |
| Health parse | Invalid types/enums/counts, host claims inconsistent | Recompute from validated checks; if core data unusable, `error`/`unknown`; explicit skips, never pass |
| Report publish | HTML invalid/active content/oversized/store failure | `partial` when summary exists; report `failed` with no URL; summary retained |
| Display | Monitor already open, launch/verification/focus denied | One launch attempt and verified window; otherwise `partial` with `display=unverified`; no relaunch loop |
| Screenshot | Capture unavailable/deferred/invalid image | `partial` with separate capture failure; report and summary remain |
| Budget | Evidence stage exceeds remaining 180/240 seconds | `partial` with `budget_exhausted`; skip lower-priority stages; never extend silently |
| Cleanup | Host run artifacts cannot be removed | Report URL still expires; sanitized cleanup failure; no user files touched |
| Evidence route | Malformed/unknown/expired report token; non-GET | Indistinguishable 404/no-store or 405 `Allow: GET`; no token/path/report leakage |
| Privacy | Audit/log serialization | Only overall/score/counts/status and stage outcomes; no report URL/token/path/HTML/PII/event/crash text |

## Post-Design Constitution Re-check

All pre-design gates still pass. The plan adds no MCP tool, dependency, or breaking schema; preserves printer/Word behavior; uses the proven capability route pattern; and makes every read-only diagnostic, report, display, screenshot, timeout, permission, and partial outcome explicit. No Complexity Tracking justification is required.
