# Upstream Bug Report: hermes-agent MCP client silently drops tool-call arguments (SSE)

## Summary

The hermes-agent's MCP-over-SSE client **silently drops the arguments of tool calls**, causing the target server to execute tool functions with only their default parameter values. The server receives the call (executes and returns a normal response), but the arguments never arrive. The gateway sees no error — the failure is invisible to the caller. The defect manifests intermittently after a period of session uptime, and as of 2026-11-03, **persists even after full session re-registration and gateway restart**.

## Environment

- **hermes-agent**: commit `bf0203a794` (from `~/.hermes/hermes-agent/.git/HEAD`)
- **Gateway**: `hermes gateway` with api_server platform on `172.17.0.1:8642`
- **MCP server**: OfficeMCP v1.0.5 (`fastmcp==4.1.5`) on `http://127.0.0.1:8888/sse` (Windows host, WSL mirrored networking)
- **MCP config**: `~/.hermes/config.yaml` → `OfficeMCP: url: http://127.0.0.1:8888/sse, enabled: true` (14/14 tools enabled)
- **Transport**: SSE (FastMCP's `/sse` endpoint + `/messages/?session_id=...` POST)

## Reproduction

The defect is **intermittent** — hours between occurrences — but has been observed **five times in two days** with a clean isolation:

### The three-probe diagnosis (separates the layers)

| Probe | Method | Result (always) |
|-------|--------|-----------------|
| 1. Direct raw MCP call to the server | Raw JSON-RPC over SSE (initialize → tools/call with explicit `code` argument) | **Arguments always delivered** — the server executes the code correctly |
| 2. `hermes mcp test OfficeMCP` | The gateway's built-in connection test | **Tools enumerate correctly** — the config and connectivity are fine |
| 3. Lane-level task (a real tool call through the gateway agent) | `POST /v1/responses` → the agent calls the MCP tool | **Arguments dropped** — the server receives the call with empty/default arguments |

This isolation proves: the **server and transport are healthy**; the drop happens inside the **gateway's MCP client session**.

### Evidence from five occurrences (2026-11-02 → 2026-11-03)

**Occurrence 1** (2026-11-02, email compose):
- Agent report: *"the tool dropped my `code` argument on every invocation and ran only its default snippet"*
- The agent fell back to a PowerShell COM detour, which the gateway's consent gate blocked

**Occurrence 2** (2026-11-03, battery O1/O2):
- Agent report: *"the harness delivered my tool_call arguments as empty on 9 consecutive attempts"*
- PowerShell fallback: *"held for user consent and timed out"*

**Occurrence 3** (2026-11-03, user's email task):
- Same args-dropped pattern; the agent's PowerShell fallback executed the compose successfully

**Occurrence 4** (2026-11-03, during the officemcp-connection-error fix verification):
- The first W0 probe (a trivial RunningApps query) timed out at 300s with the sidecar down
- After recovery, the retry passed in 5s — intermittent

**Occurrence 5** (2026-11-03, during the `deploy all` battery):
- After a **full reset** (kill OfficeMCP process + fresh start + COM warm-up via direct call + `hermes mcp remove/add` + `hermes gateway restart`), the gateway's calls **still arrived with empty arguments** on most probes (only 1 of 10 office-lane probes succeeded)
- This is the critical finding: the defect **persists after full session re-registration**, which previously cleared it

### The recovery procedure (now insufficient)

The following used to clear the defect every time (3 recoveries verified on 2026-11-02 → 2026-11-03 morning):
```bash
hermes mcp remove OfficeMCP
yes | hermes mcp add OfficeMCP --url http://127.0.0.1:8888/sse
hermes gateway restart -y --detach
```

As of occurrence 5 (2026-11-03 afternoon), this procedure **no longer clears the defect** — the gateway's tool calls continue to arrive with empty arguments immediately after a clean re-registration + restart.

## The dropped data

The MCP server's `RunPython` tool signature:
```python
def RunPython(code: str = "\nprint(f'hello world from {data}')\noutput=data\n", data: str = "OfficeMCP") -> dict:
```

When the arguments are dropped, the server executes the **default** code (printing "hello world from OfficeMCP") and returns `{"success": true, "output": "Execution completed"}` — a **normal, successful response with wrong data**. The gateway never sees an error, which makes the failure invisible to both the agent and the caller.

## Suspected mechanism

The SSE POST to `/messages/?session_id=...` carries the tool-call arguments as a JSON-RPC request body. The server receives and processes the call (proven by the default-snippet execution), but the `arguments` field arrives empty. Possible causes inside the hermes-agent MCP client:

1. **Serialization**: the client's JSON serialization of tool-call arguments may fail silently (e.g., a type-coercion or encoding issue), sending the method name but emptying the params
2. **Session state**: the SSE session's message-routing table may lose the argument routing after the session state degrades
3. **Threading/async race**: the MCP client may have a race condition between argument construction and the SSE POST

The defect is **not** in:
- The MCP server (direct raw calls always deliver args)
- The SSE transport (byte-clean; the POST reaches the server)
- The mirrored networking (WSL loopback is stable)
- The Dify/sidecar layer (the directive construction is upstream and correct)

## Impact

Every Office-lane turn silently fails — the agent retries (observed: 4-9 consecutive empty deliveries), burns the 300-600s turn budget, or falls back to a PowerShell detour that the gateway's consent gate blocks. The user sees "no response" or a confusing partial failure. The agent cannot execute any real Office task while the session is degraded.

## Workaround

- **Detection**: the agent's instructions include a "SESSION-DEGRADATION RULE" (stop retrying after 2+ consecutive default-echo returns; report `TASK: FAILED — OfficeMCP session stale` with the recovery steps). A battery pre-flight (W0) detects a degraded session in <10s.
- **Recovery**: the re-registration + restart procedure (now only temporarily effective)
- **Bypass**: direct raw MCP calls to the server always work (verified in every occurrence)

## Request

Please investigate the MCP client's tool-call argument serialization and session state management. The three-probe isolation (raw call works → mcp test works → gateway agent call drops args) should pinpoint the layer. The defect is reproducible with any MCP server using the SSE transport — it is not OfficeMCP-specific.
