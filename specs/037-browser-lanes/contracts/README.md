# Contracts: Browser Lanes (spec 037)

**Spec**: 037 | **Date**: 2026-11-11 | Inherits [035 contracts](../035-ai-helpdesk-architecture/contracts/README.md); fixes the concrete shapes the contract tests pin.

## Sidecar MCP tool surface (additive: 33 → 35)

### browser_scripted_run

```
browser_scripted_run(script: str, args: dict, conversation_id: str) -> {
  status: "ok" | "ask-back" | "error",
  steps?: [ { step, ok, summary } ],      # per-step checkpoints, in order
  expect?: [str],                          # what was verified
  reason?                                   # ask-back: missing slots named; error: honest cause + recovery
}
```

- Resolves the script from the registry (files in `scripts/browser/`); unknown name → honest not-found error (never a fabricated run).
- Args validated against the script's `params` schema; missing slot → `ask-back` naming `{{slots}}` (never a guess — the 036 discipline).
- Executes on the Windows host via the existing hermes execution channel; per-step JSON lines verified against `expect` in order; first failed checkpoint aborts naming it (FR-005).
- Every run (completed/aborted/error) audits `operation=browser-scripted-run` with `conversation_id`, `duration_s`+`timing`.

### browser_status

```
browser_status(conversation_id: str) -> {
  status: "ok" | "error",
  dynamic: { reachable: bool, url },       # :3002 probe
  scripted: { registry: int },            # script count
  reason?                                  # honest-unavailable + recovery text (start the Scheduled Task)
}
```

- Probe failure → `error:browser-lane-unavailable` naming the recovery command (`schtasks /run /tn playwright-mcp-server`); never a hang, never a fabricated "reachable".

## Script file contract (`scripts/browser/<name>.py`)

```
# name: <snake_case>            — matches filename
# version: <int>
# params: {"<slot>": "<description>", ...}
# expect: ["<checkpoint n>", ...]
<body: Playwright script; one JSON line per step: {"step": n, "ok": bool, "summary": str}>
```

- Registry load validates: name match, version present, params/expect parse, **no credential-looking literals, no machine-specific paths** (036 validator regexes reused). A rejected script never enters the routing surface.
- Credentials pass per-run as `args` slots, never baked into the body (FR-006).

## Gated-lane protocol (extends spec-034; binding here)

- Browser lanes carry **no confirm-gated tools of their own** — but a browsed page's injected instruction to use one is untrusted content: routing to a gated lane requires the **user's own re-ask**, which passes the normal gates (draft→confirm). No browser-originated text ever shortcuts this (FR-008).

## DSL wiring (per-component ownership rule)

- Intent classifier: new class — browser intents. Known-flow phrasing (fixed login/scrape/form) → scripted; exploratory → dynamic; **no browser intent maps to the OS lane** (FR-002 pin, A13-style contract test).
- Browser lane instructions carry: the untrusted-content law verbatim (R4 layer 1), the tool scope = browser + skill + status only (R4 layer 2), long-flow split guidance (FR-003), and honest-relay rules.
- General lane unchanged (skill-tools question scope from 036).
- `tool_mcp_providers` rebuild + `docker-api-1`/`docker-worker-1` restart after publish (staleness rule).

## Hermes-native MCP registration (035 FR-018)

`playwright-mcp-server` Scheduled Task (`windows/playwright-mcp-task.xml`) auto-starts `%APPDATA%\npm\playwright-mcp.cmd --port 3002 --host 127.0.0.1`; the Hermes agent registers the endpoint natively (`hermes mcp add PlaywrightMCP --url http://127.0.0.1:3002/sse`). Consent-policy retries and direct-channel fallback follow the existing WindowsMCP pattern.

## Audit contract

Two new `operation` values: `browser-scripted-run`, `browser-status` — house row shape (operation, conversation_id, decision, outcome/reason, `duration_s`+`timing`). Adversarial A2 refusals MUST appear as audit rows (SC-006); A2's assertion includes **zero non-browser tool calls** in the turn (verified via the lane's tool scope + audit absence).