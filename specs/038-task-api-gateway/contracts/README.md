# Contracts: Task-API Gateway (spec 038)

**Spec**: 038 | **Date**: 2026-11-11 | Inherits [035 contracts](../035-ai-helpdesk-architecture/contracts/README.md); fixes the concrete shapes the contract tests pin.

## Gateway service HTTP API (Windows host, `127.0.0.1:8080`, loopback-only)

```
POST /api/helpdesk/tier1   {issue_type, issue_text}  -> {recommendation: "none"|"tier2", actions: [...], detail}
POST /api/helpdesk/tier2   {issue_type}              -> {repair_name, repair_text, result, detail}   # bounded ~120 s, sync
POST /api/office/install   {version, channel}        -> {job_id, status: "queued"}
GET  /api/helpdesk/job/{id}                         -> {job_id, kind, status, detail, started_at, ended_at?}
GET  /api/healthz                                   -> {"status": "ok"}
```

- Structured JSON on every path; non-JSON/HTML error responses are the SIDE CAR's malformed case, never parsed as content (FR-009).
- Job statuses are real at every poll (`queued|running|progress|completed|failed`); `failed` carries detail.
- Loopback bind only; the sidecar reaches the host over the docker0/mirrored network (`cfg.task_gateway_url`, default `http://172.17.0.1:8080`).

## Sidecar MCP tool surface (additive: 35 → 39)

All four: `conversation_id` REQUIRED, audited with `duration_s`+`timing` + `conversation_id`.

### task_helpdesk_tier1

```
task_helpdesk_tier1(issue_type: str, issue_text: str, conversation_id: str) -> {
  status: "ok" | "error",
  recommendation?: "none" | "tier2",     # relayed honestly; "tier2" ALSO registers pending tier-2 state
  actions?, detail?, reason?
}
```

- ALWAYS the first gateway call for a system issue (FR-001). On "tier2": registers the recommendation (named repair from the service catalog) conversation-scoped and returns `pending-repair: <name>` guidance.

### task_helpdesk_tier2

```
task_helpdesk_tier2(issue_type: str, conversation_id: str, confirm: bool = False) -> {
  status: "ok" | "blocked" | "error",
  repair_name?, result?, detail?, reason?
}
```

- `confirm=False` (default): requires pending tier-2 state; returns `pending-confirmation` with the NAMED repair + what it will do — **nothing executes**. Never-listed repair → `blocked` + escalation (FR-003, even before confirmation).
- `confirm=True`: executes ONLY the stored named repair, only with a fresh recommendation, only if not superseded; carries no repair payload (034 structural). Never-list re-scanned at execution (defense-in-depth).
- Missing/superseded recommendation → honest blocked reason.

### task_office_install

```
task_office_install(version: str, channel: str, conversation_id: str) -> {
  status: "ok" | "error", job_id?, status?: "queued", reason?
}
```

- Starts the install job and returns the handle (FR-005) — NEVER a held-open call; the DSL polls `task_job_status`.

### task_job_status

```
task_job_status(job_id: str, conversation_id: str) -> {
  status: "ok" | "error", job?: {job_id, kind, status, detail}, reason?
}
```

- Real fields at every poll; unknown id → honest not-found; service down → unavailable envelope + recovery text (`schtasks /run /tn task-gateway-service`).

## Never-list contract (shared module — R3)

- `neverlist.scan(text) -> reason | None` used by BOTH `hermes_powershell_gate` (byte-identical 034 patterns; 034 suite re-pins green) and the tier-2 lane (same class + tier-2 scope).
- Refused class: volume format, diskpart, boot config (bcdedit/bootcfg/bootrec), shadow-copy deletion, recovery environment, BitLocker state, disk wipes — **regardless of lane, recommendation, or confirmation**. Repair-class ops (sfc /scannow, DISM /RestoreHealth without /ResetBase) are Tier-2-allowed.
- Gate-shopping (A1): a refusal here is NOT retryable via another lane; the DSL carries no raw HTTP tool (FR-007 structural) and the OS lane's own gates refuse the same class.

## DSL wiring (per-component ownership)

- Classifier: system-issue/Office-install intents → the gateway lane rules (tier1-first protocol verbatim, tier-2 confirmation semantics, install job+poll discipline).
- Lane node tool scope: the 4 task tools + skill tools + status ONLY (A1 structural boundary).
- General lane unchanged; browser/OS lanes unchanged (their gates refuse the never-list class independently — A1 pin).
- `tool_mcp_providers` rebuild + api/worker restarts after publish.

## Audit contract

Six new `operation` values (`task-tier1`, `task-tier2-draft`, `task-tier2-executed`, `task-tier2-refused`, `task-office-install`, `task-job-status`), house row shape. A1/A4 adversarial refusals MUST appear (SC-006); zero Tier-2 executions without both preconditions is the SC-002 grep.