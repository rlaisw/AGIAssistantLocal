# System Health Check — Phase 0 Research

**Date**: 2026-11-22
**Spec**: [spec.md](spec.md)

All Technical Context choices are resolved. The live probes listed at the end validate external contracts before execution wiring; they are implementation gates, not unresolved design choices.

## D1 — Extend `mcp_action`; do not add a new MCP tool

**Decision**: Register `system_health_check` as a third `action_id` inside the existing two-phase `mcp_action` tool with a closed empty-parameter schema.

**Rationale**: Reuses proposal TTL, conversation/turn consent, desktop-wide lock, duplicate protection, report/audit integration, and the existing Dify tool contract. The MCP tool surface remains **59** and Dify does not need a new cached tool. `action_id` is already a free string.

**Alternatives considered**: A separate health-check tool would duplicate consent/locking and add a tool surface change. Routing through HelpDesk is repair-oriented and violates the guidance-only boundary.

## D2 — Stage the reviewed script on the Windows host with a hash pin

**Decision**: Commit `windows/health-check.ps1`; extend deployment to copy it to `C:\ProgramData\agentic-rag\health\health-check.ps1` and verify SHA-256 before/after copying. A pinned hash in `mcp_action/health.py` is rechecked immediately before execution. Reject a missing/mismatched script before offering/running.

**Rationale**: The sidecar container does not ship `windows/` and cannot carry the full script safely in the 4,000-character text result. `C:\ProgramData\agentic-rag` is outside the Hermes file lane’s writable `C:\temp` root, reducing accidental overwrite risk. The deploy already runs where `/mnt/c` is visible. A process-scoped `-ExecutionPolicy Bypass` runs only the reviewed file without changing machine policy.

**Alternatives considered**: Manual copy is unsynchronized. Inline command risks size limits and helper-path failures. `C:\temp` is chat-writable. Authenticode signing is heavier for this local deployment.

## D3 — Run through a fixed wrapper with bounded child process

**Decision**: The sidecar invokes one fixed PowerShell wrapper with a model-inaccessible run ID. The wrapper verifies the script hash, launches `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <fixed path> -NoReliabilityMonitor -ReportPath <fixed html path>` under a 120-second child-process deadline, captures its stdout to `<runId>.json`, verifies the HTML exists, writes a small `MCP_ACTION_JSON:<base64>` status marker, and kills only the timed-out child. It never accepts a model-authored path, command, or argument.

**Rationale**: The supplied script prints a potentially large single-line JSON; the wrapper moves it to disk. The child-process deadline is required because the Windows-MCP client has no outer command timeout. `-NoReliabilityMonitor` prevents a duplicate launch; the approved action owns display once.

**Alternatives considered**: Increasing the global 4,000-character bound affects every Windows lane and still risks large payloads. Splitting stdout is brittle. Letting the service cancel without a host deadline can leave an orphaned process.

## D4 — Read artifacts through the read-only `/mnt/c` mount

**Decision**: The script writes `<runId>.json` and `<runId>.html` under `C:\ProgramData\agentic-rag\health\reports`; the sidecar reads them from `/mnt/c/ProgramData/agentic-rag/health/reports`. It never sends the full payload through `call_tool`. Validate UTF-8, required keys, sizes, and HTML structure. After copying the report, invoke a fixed cleanup wrapper to remove only that run’s JSON/HTML artifacts.

**Rationale**: The production deploy mounts `/mnt/c:/mnt/c:ro`; no new mount is required. Host writes happen in PowerShell, and transient run artifacts are cleaned after use. No user files are touched.

**Alternatives considered**: `FileSystem` tool is not in the validated Windows lane and is still text-bound. FileResponse directly from a host path loses tokens on restart. The standalone compose lacks `/mnt/c`; production deploy is the supported path.

## D5 — Add a dedicated 15-minute HTML report store and route

**Decision**: Add `ReportStore` and `GET /mcp-action/reports/{token}` (GET/HEAD; non-GET 405). Tokens are 256-bit URL-safe 43-character capabilities. Store one self-contained HTML document, max 5 MiB, `0600`/`0700`, absolute 900-second TTL, no renewal, startup/30-second janitor cleanup. Serve `text/html; charset=utf-8` with `Cache-Control: no-store`, `Pragma/Expires`, `nosniff`, `no-referrer`, `DENY` framing, no wildcard CORS, `X-Robots-Tag: noindex`, and CSP `default-src 'none'; style-src 'unsafe-inline'; img-src data:; script-src 'none'; ...; sandbox`.

**Rationale**: ScreenshotStore is image/magic-byte/CORS-specific and must not be reused for PII-bearing HTML. The report is a top-level link, not an embedded asset. Chat Markdown already opens normal links in a new tab with `noopener noreferrer`; the image proxy rejects non-images.

**Alternatives considered**: Reuse `/exports` or screenshot route fails TTL/MIME/CORS semantics. Data URLs pollute history and do not expire. Next.js serving requires shared storage/proxy.

## D6 — Verify Reliability Monitor through existing reviewed tools

**Decision**: Add `WindowsDisplay.show_reliability_monitor()`: best-effort pre-check for an existing Performance Monitor window; otherwise call the reviewed `open_settings("reliability monitor")` once; verify the window via `WaitFor`/`Snapshot` using the proven “Performance Monitor” title and reliability text; front via `App switch`; capture with existing `ScreenshotCapture`. Never relaunch after a verification failure. The script always runs with `-NoReliabilityMonitor`.

**Rationale**: Spec 042 established that `mmc.exe -ArgumentList 'perfmon.msc','/rel'` opens the visible Reliability view and that the window title is “Performance Monitor”. The action must not claim the chart data is ready merely because the window exists.

**Alternatives considered**: Starting `perfmon /rel` directly silently exits in the service context. A second mmc launch can duplicate windows. Unverified screenshots must not be presented as proof.

## D7 — Recompute health status/counts in Python; separate action success

**Decision**: Treat host JSON as untrusted. Validate types/enums/shape/limits and recompute check counts, overall (`fail` > `warn` > `pass` > `unknown`), score (`max(0, 100 - 15*fail - 5*warn)`), and confidence (`high` only when all core checks produced pass/warn/fail and reliability is available; `reduced` for skips/info; `low` when no applicable/core data). The action `status=ok` means the summary/evidence stages succeeded; `health.status=fail` is a valid health finding, not an action failure.

**Rationale**: Host claims are untrusted and skips must remain visible. The read-only action has no before/after setting state; use `verification="reported"` to mean a valid structured report was parsed. Report/display/screenshot have independent outcomes.

**Alternatives considered**: Trusting script score/status hides malformed or inconsistent output. Treating `health=fail` as action error would mislead the user about a successful diagnostic.

## D8 — Health-specific 180-second deadline inside the 240-second total

**Decision**: Add `_HEALTH_ACTION_BUDGET_S=180` to an explicit action-budget mapping while preserving 60/90 defaults. A health action starts only if the full 180 seconds remains (`queue_wait <= 60`). Run script/wrapper ≤120 seconds, report publication inside execution, display WaitFor ≤30 seconds, and skip capture if less than the minimum remaining evidence budget. Return `partial` with `budget_exhausted` if a later stage cannot finish; never silently extend.

**Rationale**: FR-019 includes diagnostic, report, display, and capture. The existing pre-execution queue check alone is insufficient. Existing 60/90 semantics and timing shape remain unchanged.

**Alternatives considered**: Raising total budget risks Dify’s 300-second stream ceiling. A background job would add lifecycle complexity not needed for one bounded diagnostic.

## D9 — HelpDesk guidance only; explicit prompt override

**Decision**: Add health protocol to General-cloud and Hermes only. It informs the user that HelpDesk can help with repairs but never calls `task_helpdesk_tier1/2`, creates a ticket, or executes a repair. The health prompt explicitly overrides the existing “system issues first call tier-1” rule only for the health-check turn; a later explicit repair request uses normal HelpDesk routing.

**Rationale**: The owner chose guidance-only. The existing tier-1 prompt would otherwise create an automatic HelpDesk request and violate the spec.

**Alternatives considered**: An automatic handoff or repair is explicitly rejected. Generic HelpDesk text without a routing override risks model/tool conflict.

## D10 — Dify evidence and privacy guard

**Decision**: Track health summary/report/display/screenshot evidence in `honesty_check`. Allow a report URL only when `report.status=="published"` and the URL is an exact `http(s)` `/mcp-action/reports/<43>` returned by the tool. If the report is published and the visible answer omits the link, append one Markdown link deterministically. Block forged report URLs, fabricated scores/counts, monitor claims without display evidence, and repair/HelpDesk-request claims without the corresponding real tool result. Audit/log only `health=<status>:score=<n>:counts...`, `report=published|failed`, display/screenshot statuses, and timings. Never audit the report URL/token/path/HTML/PII.

**Rationale**: The report contains owner-approved PII but must not become a long-term artifact. The model must not fabricate a report/score/repair. Deterministic link insertion prevents a successful report from being unusable.

**Alternatives considered**: Full report in model context is unsafe and redundant. Relying only on prompt compliance risks missing/forged links.

## D11 — Testing and deployment strategy

**Decision**: Red-first unit tests for state/action/wrapper/parser/store/route/budget/audit/DSL; contract tests for the new report route and unchanged MCP surface; live Dify draft/cancel for both approved lanes; opt-in owner-present confirm E2E with report URL, Reliability Monitor, timeout/failure stages, HelpDesk guidance, and read-only invariants. Deployment stages the script and reuses the 59-tool surface; no new MCP tool-cache entry.

**Rationale**: The highest-risk areas are untrusted host payloads, large-output/file transport, 180-second staging, and PII capability URLs, so each needs a deterministic check plus one live probe.

**Alternatives considered**: Relying only on live tests is flaky and slow. Reducing the report route to a simple path would bypass privacy/expiry tests.

## Live contract probes required before dependent implementation

1. **Host staging**: confirm write access to `C:\ProgramData\agentic-rag\health`, `/mnt/c` casing, and hash verification.
2. **Wrapper/file output**: run one read-only diagnostic with a disposable run ID; confirm JSON/HTML files, marker size under 4,000 chars, child timeout/kill behavior, and no Reliability Monitor launch.
3. **Reliability display**: confirm the Performance Monitor window title/text and exactly-one-launch/verification behavior.
4. **Report URL**: confirm reachable public origin, route headers/CSP, and token redaction in logs.
5. **Dify**: confirm health draft/cancel in General-cloud and Hermes; confirm a health confirm does not invoke a HelpDesk tool.

No `NEEDS CLARIFICATION` markers remain for planning.
