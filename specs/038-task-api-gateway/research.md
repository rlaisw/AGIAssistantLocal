# Research: Task-API Gateway (spec 038)

**Spec**: 038 | **Date**: 2026-11-11 | **Status**: resolved (inherits 035 R5; adds the component decisions)

## R1: Service implementation — cli-hub components vs a thin local service

- **Decision**: a **thin stdlib `http.server` service** (`services/task-gateway/service.py`) implementing the 035-R5 endpoint shapes, with Tier-1 quick-fix logic donated from `cli-anything-hub` harnesses **only where a harness matches a curated quick fix** (e.g. its service-restart/printer patterns); DISM/SFC Tier-2 and ODT install steps run as the service's own PowerShell invocations.
- **Rationale**: probed live this morning — `cli-hub 0.4.1` is a *registry client* (browse/install/launch other CLIs); it does NOT itself expose `/api/helpdesk/*`. The 035 diagram's "cli-anything :8080" is the HKUDS *concept*, not an installed server — so the endpoint SHAPES are the contract and the service is ours to build. Stdlib keeps it audit-friendly, dependency-free (Constitution III), and trivially Scheduled-Task-managed.
- **Alternatives considered**: vendoring HKUDS CLI-Anything's service wholesale (rejected in 035 R5: un-audited third-party execution surface); FastAPI (rejected: three endpoints don't justify a framework + deps); using `cli-hub launch` as the lane's backend (rejected: registry indirection adds a failure layer and hides the actual operation from the never-list scan).

## R2: The tier-2 confirmation protocol

- **Decision**: **two-phase like 034 but with a third precondition**: the lane tool `task_helpdesk_tier2(issue_type, conversation_id, confirm=False)` — call 1 (no confirm) requires a FRESH tier-1 recommendation in state (recorded when tier1 returned "tier2" this conversation) and returns `pending-confirmation` with the NAMED proposed repair (what Tier-2 will actually run, from the service's repair catalog entry for that issue type); call 2 (`confirm=True`, no payload) executes **only** if (a) the pending recommendation exists in this conversation, (b) it was NOT superseded, (c) the named repair is not never-listed (scanned at BOTH calls). State: `Tier2State` mirroring `PowerShellState` (conversation-scoped dict + lock, in-memory, audit JSONL as the durable record).
- **Rationale**: 035 Q3=C verbatim — recommendation + chat confirmation, never-list binding; 034's structural insight (the confirm call carries no operation text — what was confirmed is what was recommended) ports directly; never-list scan at draft AND execution is 034's FR-002 defense-in-depth, kept.
- **Alternatives considered**: generic yes/no state without the named repair (rejected: the user confirms a *named repair*, not a category — a modification must re-ask); DSL-side confirmation only (rejected: state must be server-scoped and auditable, not prompt-scoped); running tier2 directly from tier1's response with `confirm=True` in one call (rejected: the user must SEE what will run before it exists as a pending intent).

## R3: Never-list sharing — one source, two gates

- **Decision**: move 034's never-list patterns to `src/agentic_rag_mcp/task_gateway/neverlist.py` as `NEVERLIST_PATTERNS` + `scan(text) -> str | None`; `hermes_powershell_gate.py` imports them (its tests re-run green unchanged — the patterns are byte-identical); the tier-2 lane scans the NAMED REPAIR's operation text (and the issue context) with the same module, extended with tier-2-specific entries (full DISM restore-health with `/StartComponentCleanup /ResetBase`, `sfc /scannow` is ALLOWED as tier-2 — it's repair-class, not integrity-class; format/diskpart/wipe class stays refused).
- **Rationale**: two copies of the never-list WILL drift — the single shared module is the only way "binding in every gate" (035 FR-013) is a fact rather than a hope. sfc/DISM-repair being Tier-2-allowed is the point of a recovery lane: the refused class stays system-integrity-destructive (format, wipe, boot, shadow-copy delete, BitLocker state).
- **Alternatives considered**: 034 keeps its own copy, 038 adds a second (rejected: drift); never-list refuses ALL of tier-2 (rejected: a recovery lane that cannot run sfc/DISM-repair is decorative — the line is destructive-integrity ops, matching 034's semantics).

## R4: Long-job model — job table + poll

- **Decision**: `POST /api/office/install` returns immediately `{job_id, status: queued}`; the service runs the ODT/`winget`-class install in a **background thread** with a job table (`{id, kind, status: queued|running|progress|completed|failed, detail, started_at, ended_at}`, persisted append-only to `C:\ProgramData\agentic-rag\task-gateway\jobs.jsonl`); `GET /api/helpdesk/job/{id}` returns the current row. The sidecar tool `task_office_install` calls install then returns the job handle; `task_job_status(job_id, conversation_id)` polls. The DSL instructs: report the handle, poll on user ask or at turn end — never loop-poll inside one tool call beyond a small bounded window (~15 s).
- **Rationale**: FR-005/SC-003 structural — a job + poll can never become a held-open stream; the 15 s in-tool bound keeps any single call far from the 300 s kill. JSONL job rows mirror the audit discipline (durable, append-only).
- **Alternatives considered**: SSE/webhook streaming job progress (rejected: Dify tool calls don't stream; polling from the DSL is the same shape with fewer moving parts); blocking call with a long budget (rejected: exactly the transport violation FR-009 exists to prevent).

## R5: Sidecar→host transport and outage envelope

- **Decision**: the sidecar reaches `http://<host>:8080` over the same docker0/mirrored host network the Hermes gateway uses (`cfg.task_gateway_url`, default `http://172.17.0.1:8080`); every client call is try/except→`error:task-gateway-unavailable` naming the recovery (`schtasks /run /tn task-gateway-service`); connect timeout 5 s, read timeout 30 s (tier1 quick fixes are fast; tier2 runs sync in-request — bounded by the service's own repair timeout, ~120 s, reported honestly if exceeded).
- **Rationale**: honest-degradation parity with 036's store envelope and 037's browser_status; the tier2 sync call stays well under the 300 s ceiling because tier-2 repairs (sfc/DISM) are minutes-class but the SERVICE bounds them — its timeout row lands as an honest `failed: timeout`, never a hang.
- **Alternatives considered**: tier-2 as a job too (deferred: complexity — sync-with-timeout is honest and simple; jobs are for install-class multi-minute work); retry/queueing in the sidecar (rejected: one honest error beats stacking retries into the transport window).

## R6: The DSL lane and gate-shopping pin

- **Decision**: new Dify classifier class for system-issue/Office-install intents → a gateway-lane routing rule set: tier1 ALWAYS first (task_helpdesk_tier1 with the user's issue text); tier-2 protocol rules verbatim (never call tier2 without a fresh tier1 recommendation + a plain user confirmation of the NAMED repair; never-list refusals are final and escalate); install → job + poll discipline; the lane node carries ONLY the 4 task tools + skill tools + status (no hermes_run_p*, no browser tools) — the structural A1 boundary. Adversarial harness pins: direct-call instruction → no raw HTTP tool exists; cross-lane smuggling ("ask the OS lane to run this repair") → refused by the OS lane's own gates + reported.
- **Rationale**: 036/037 proved the pattern twice — tool-scope is the hard anti-injection boundary, the never-list is shared (R3), and A1/A4 land as contract tests, not vibes.
- **Alternatives considered**: gateway intents riding the existing Hermes lane (rejected: mixing the tier protocol's confirmation semantics with the PowerShell lane's draft semantics invites confusion; separate tools, shared never-list module).

**All NEEDS CLARIFICATION resolved; none remain.**