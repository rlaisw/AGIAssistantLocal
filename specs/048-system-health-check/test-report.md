# System Health Check — Test Report

**Feature**: `048-system-health-check`
**Started**: 2026-11-22

## T001 — Baseline before implementation

- Python unit/contract: **1,245 passed, 0 failed, 187 warnings in 280.69 seconds**.
- Frontend: **26 files / 188 tests passed**; TypeScript passed.
- ESLint: one pre-existing warning at `ai-chat-landing/scripts/stop-button-check.mjs:16:7` (`ONLY` unused).
- Working tree: feature planning artifacts only; no source implementation yet.

## Implementation evidence

Later task evidence is appended here as tasks complete.

## T015 — Host and display contract probe (PASS)

- Staged script hash matched source: `1a7519d6b658261b5341cfb6ccd74e0cc76803ca9274c0885f3fffc686b7b14a` (historical simple script; current advanced script is `8045e5438e6c5fad3bacb12f468a4a3e9c8fc5840480e9e93948f5fac3f1ee5e`).
- Host path `C:\ProgramData\agentic-rag\health\health-check.ps1` and report directory were writable; matching WSL path `/mnt/c/ProgramData/agentic-rag/health/reports` was readable.
- One fixed read-only probe produced valid JSON (**9,591 bytes**) and self-contained HTML (**3,804 bytes**); JSON already exceeded the 4,000-character Windows-MCP text bound, confirming file transport is required.
- Parsed payload: `status=ok`, `overall=WARN`, `score=75`, **9 checks**, reliability available.
- `open_settings("reliability monitor")` opened once; `WaitFor` with `condition: window`, `window_name: Performance Monitor` verified the window after 17.15 seconds.
- `Snapshot` confirmed the “Performance Monitor” window title. The Reliability text may require more than the bounded Snapshot output, so WaitFor window verification is the authoritative display check.
- Probe artifacts were removed from the host report directory.

## T027 — Deterministic health validation (PASS)

- Health/action/state/report/concurrency/logging/deploy suites: **552 passed** after correcting two inconsistent new expectations (a FAIL check cannot normalize to WARN; internal HTML bytes are not JSON-serializable and are scanned separately).
- Complete Python unit/contract suite: **1,437 passed, 0 failed, 187 warnings in 288.16 seconds**.
- Frontend: **26 files / 188 tests passed**; TypeScript passed; one pre-existing ESLint warning at `scripts/stop-button-check.mjs:16:7`.
- Ruff on MCP-Action, health, deploy-asset, server, report-route, and integration files: **all checks passed**.
- No MCP tool-count increase: `system_health_check` is an action ID inside the existing tool.

## T029–T035 — Live Dify and health E2E acceptance (PASS)

- Live Dify health draft/cancel on General-cloud and Hermes: **2 passed in 43.94s**; both showed `dialogue_count=1→2`, empty parameters, pending then cancelled, no HelpDesk/report/desktop effects.
- Full owner-present health matrix: **15 passed, 1 environment skip in 329.67s**; one read-only host-state check was skipped by the harness's environment guard.
- Confirmed:
  - direct/decline and instability ask-first behavior;
  - exact offer and no pre-confirm effects;
  - report publication with a 43-character/900-second report URL and 3,804-byte HTML;
  - Reliability Monitor display and screenshot;
  - report/display/screenshot partial outcomes;
  - host hash/staging/malformed/timeout failures;
  - HelpDesk guidance only, no task-helpdesk/ticket/repair;
  - duplicate confirmation and desktop serialization;
  - audit summary only, no URL/token/PII/report HTML.
- During acceptance, the service was corrected to publish/read the HTML before host cleanup, accept the real ReportStore adapter, support the synchronous display test adapter, include caveats/usage, and classify pending proposals as `proposed` in audit.
- 20-run performance benchmark: **20/20 action-ok with report/display/screenshot**, p95 **22.085s**, max **22.096s**, all well below 180 seconds.

## T036 — Final regression gate (PASS)

- Complete Python unit/contract suite: **1,437 passed, 0 failed, 187 warnings in 285.95s**.
- Frontend Vitest: **26 files / 188 tests passed**.
- TypeScript: **`tsc --noEmit` passed**.
- ESLint: **0 errors**, one pre-existing warning at `ai-chat-landing/scripts/stop-button-check.mjs:16:7` (`ONLY` unused).
- Live Dify contract suite: **5 passed in 162.67s** — general-cloud and Hermes health draft/cancel, plus the existing newline and yes regressions. Both health rows showed empty parameters, `pending` then `cancelled`, no HelpDesk, and no report/desktop effect.

## T037 — Documentation (PASS)

Updated `AGENTS.md`, `ai-chat-landing/AGENTS.md`, `README.md`, `DEPLOY.md`, and the external `agenticrag-deploy` skill for:

- the third reviewed action `system_health_check` with empty parameters;
- the pinned host script and fail-closed SHA-256 staging;
- the 15-minute `GET /mcp-action/reports/{token}` capability URL and `no-store`/CSP posture;
- HelpDesk guidance-only behavior with no automatic ticket or repair;
- the unchanged **59-tool** MCP surface.

## T038 — Index refresh (PASS)

- Graphify manual saved-node-preserving update: **11,473 nodes, 18,785 edges, 1,003 communities, 132 hyperedges**. All 243 previously saved semantic nodes were re-added before export; 34 changed docs were semantically extracted and cached.
- `graph.html` and `GRAPH_REPORT.md` regenerated; `manifest.json` and `cost.json` updated.
- `ccc index`: **26,951 chunks across 1,070 files, 0 errors**.
- codebase-memory: **15,766 nodes / 34,803 edges**, status `ready`.

## T039 — Acceptance reconciliation and cleanup (PASS, one UX criterion unmeasured)

| Requirement | Status | Evidence |
|---|---|---|
| FR-001 eligibility | PASS | Live Dify health draft + E2E explicit/instability journeys |
| FR-002 ask-first, no run | PASS | E2E ask-back rows; state tests |
| FR-003 manual guidance first | PASS | DSL/health tests and live answers |
| FR-004 exact offer | PASS | DSL pins + E2E confirmation rows |
| FR-005 proposal has no side effect | PASS | Draft tests + live contract (`no host effects`) |
| FR-006 no run before yes | PASS | State/service tests |
| FR-007 only stored proposal on N+1 | PASS | Turn/expiry/supersession tests; E2E |
| FR-008 strictly read-only | PASS | Host-script verb scan; H-E13 printer read-back; remaining read-only rows |
| FR-009 health summary | PASS | Normalization tests; live `status/score/counts/checks` |
| FR-010 reliability records | PASS | T015 probe; live JSON reliability data |
| FR-011 temporary HTML report URL | PASS | E2E report publication; 20/20 benchmark |
| FR-012 15-minute unguessable non-cached URL | PASS | Report-store and route contracts; expiry 404 |
| FR-013 approved report fields unredacted | PASS | HTML payload fixtures/tests |
| FR-014 audit summary only | PASS | Health audit assertions; no full report |
| FR-015 Reliability Monitor shown once | PASS | Display tests + live `WaitFor` verification |
| FR-016 display/capture outcomes separate | PASS | Partial-result E2E rows |
| FR-017 full HTML + summary | PASS | Owner override 2026-11-22: complete `report.html` appended verbatim and written to `%LOCALAPPDATA%\Temp\selfcheck.html`; the visible answer uses the path and strips the temporary URL; live confirm verified |
| FR-018 HelpDesk guidance only | PASS | E2E and live Dify HelpDesk rows |
| FR-019 180-second budget | PASS | Benchmark p95 22.085s, max 22.096s |
| FR-020 explicit skips/info | PASS | Normalization and live payload tests |
| FR-021 honest failure/partial | PASS | H-E05–H-E12/H-E16 matrix |
| FR-022 existing consent/serialization rules | PASS | State, concurrency, duplicate, expiry tests |
| FR-023 approved lanes only | PASS | DSL tests + General-cloud/Hermes live rows |
| FR-024 repair request → HelpDesk only | PASS | Decline/repair-request E2E and live rows |
| FR-025 no credentials collected | PASS | Privacy scan; audit assertions |
| SC-001 offer only after guidance | PASS | DSL and live offer rows |
| SC-002 no execution on no/modified/orphan/expired | PASS | State and E2E negative matrix |
| SC-003 ≥95% within 180s | PASS | 20/20 (100%) |
| SC-004 summary + resolvable URL | PASS | E2E and benchmark rows |
| SC-005 warnings → HelpDesk, no repair | PASS | HelpDesk preservation rows |
| SC-006 expiry 404 + no PII in audit | PASS | TTL 404 and privacy-scan tests |
| SC-007 ≥90% participant identification | **NOT MEASURED** | No formal participant UAT session was run; not claimed as passed |

- H-E13 now passes: the service evidence uses a compact count + SHA-256 digest, avoiding the Windows-MCP 4,000-character bound. The health check left the printer set, default printer, managed-default semantics, and service-state digest unchanged; report published, Reliability Monitor displayed, screenshot captured.
- Cleanup: host report directory `C:\ProgramData\agentic-rag\health\reports` contains **0 files**; container `/tmp/agentic-rag-mcp-reports` contains **0 files**.
- Privacy: report capability tokens are redacted in `server.log`; no health report URL/token is present in the persistent audit; the dedicated health audit assertions verify no login, email, IP, serial, event, crash, or report-content data. The only unredacted report path in logs is the deliberately invalid `not-a-capability` probe.
- No dishonest success path or deterministic regression remains. SC-007 is the sole open acceptance item and requires an owner-run participant session before it can be claimed.

## T040 — H-E13 compact service evidence (PASS)

- Replaced the full service list with `count` plus a SHA-256 digest over sorted `Name=Status` lines; the payload stays well below the Windows-MCP `TEXT_BOUND=4000`.
- H-E13: **1 passed in 31.71s**. Health `status=ok`, machine `warn` score `70`, report `published`, display `displayed`, screenshot `captured`.
- Audit: 5 rows, executed, summary-only, no token, no PII. Cleanup: 0 owned host artifacts remaining.




## Post-verification owner override — full HTML report (historical simple report, 2026-11-22)

- FR-017 was changed by explicit owner request: the action now returns the complete HTML in `report.html`, the finalizer appends it verbatim, and the wrapper writes the same file to `%LOCALAPPDATA%\Temp\selfcheck.html`.
- Live Dify draft → confirm: `confirm=ok`, answer **8,942 chars**, exactly one `<!DOCTYPE html>`/`</html>` document, report URL present, `%LOCALAPPDATA%\Temp\selfcheck.html` named in the answer, no honesty replacement.
- Host file: `%LOCALAPPDATA%\Temp\selfcheck.html`, **20,413 bytes**, complete single HTML document.
- Tests: **579** MCP-Action/contract tests passed; DSL suite **115 passed**; full unit/contract suite **1,442 passed** before the final negated-repair regression test.
- Audit remains summary-only: no URL, token, HTML, or PII is written to the audit.


## Advanced script upgrade (2026-11-23)

- Supplied `Invoke-AdvancedDesktopSelfCheck.ps1` validated directly: exit **0**, **27.3s**, JSON **17,078 bytes**, HTML **20,420 bytes**, with `computer/user/hardware/runtime/Health checks/Reliability` sections.
- Replaced `windows/health-check.ps1` with the advanced script; pinned SHA-256 is **`8045e5438e6c5fad3bacb12f468a4a3e9c8fc5840480e9e93948f5fac3f1ee5e`**.
- The wrapper now writes `%LOCALAPPDATA%\Temp\selfcheck.html` (actual `C:\Users\RLWC145\AppData\Local\Temp\selfcheck.html`, **20,413 bytes**) and returns that expanded path in `report.host_path`.
- Fixed the HTML active-content guard that falsely matched `sessionType=` as an event handler; the advanced report is now accepted.
- Live E04 (owner-present harness): **1 passed**, `status=ok`, `report=published`, `display=displayed`, `screenshot=captured`, report **20,413 bytes**.
- Affected suites: **585 passed**; Ruff and `git diff --check` clean.
- Live Dify chat verification is currently blocked by Windows MCP `CONTROL_UNAVAILABLE` (host control session), not by the script/report code; restart `windows-mcp-server`/session recovery is pending.
