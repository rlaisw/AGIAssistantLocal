# Bug Assessment (re-run, supersedes 2026-11-08): The ~300 s chat-side cut is the plugin library's MAX_REQUEST_TIMEOUT=300 default — an env var the daemon never sets

- **Slug**: `the-local-agent-hit-a-transport-error`
- **Created**: 2026-11-09T01:55+00:00 (re-assessment per test.md's failed-verification recommendation; the 2026-11-08 assessment blaming the provider row is preserved in git)
- **Source**: pasted text (the agent's transport-error relay) + the failed verification's restart-controlled samples + this hunt
- **Verdict**: valid — root cause now identified with high confidence
- **Severity**: medium — chat-side tool calls are cut at 300 s; the honest 540 s envelope never fires through the chat

## Report (verbatim or summarized)

> "The local agent hit a transport error — the connection dropped before it could report back ('peer closed connection without sending complete message body')"

The failed verification (test.md) eliminated the provider row, api-1, and the plugin daemon (both samples cut at ~300 s of tool time invariant to all three). This hunt located the remaining candidate.

## Symptom

Chat-side tool calls die at ~300 s with "peer closed connection"; expected: up to the sidecar's honest 540 s envelope.

## Reproduction (evidence chain)

1. Both test.md samples: cut at 300.000 s ± 10 s of tool time, invariant to row=600 + api restart + daemon restart
2. `strings /app/main`: the daemon binary consumes only `PLUGIN_MAX_EXECUTION_TIMEOUT` (600, set, different knob — the daemon's own execution deadline, which the 603 s kill already showed firing later)
3. **The agent plugin's own venv** (`langgenius/agent-0.0.51/.venv/.../dify_plugin/config/config.py`): `class DifyPluginEnv(BaseSettings)` — `MAX_REQUEST_TIMEOUT: int = Field(default=300, "Maximum request timeout in seconds")` and `MAX_INVOCATION_TIMEOUT: int = Field(default=250, "for backwards invocation")`
4. `dify_plugin/core/runtime.py`: the plugin's back-invocation HTTP client (`httpx.request(...)`) uses `self.session.max_invocation_timeout` as **read/write timeout** for every invoke — and the daemon's environment (checked: 287 vars) defines **neither** `MAX_REQUEST_TIMEOUT` nor `MAX_INVOCATION_TIMEOUT`, so the library defaults (300/250) apply
5. The mechanism: agent plugin (daemon) → back-invocation POST to the api → the api holds the MCP stream open (row=600) → the **plugin-side client times out at its default** → drops the connection → api aborts the MCP stream mid-body → "peer closed connection without sending complete message body" relays honestly to the chat

## Suspected Code Paths

- `dify_plugin/config/config.py` (`MAX_REQUEST_TIMEOUT=300`, `MAX_INVOCATION_TIMEOUT=250` — pydantic BaseSettings, so **environment variables of the daemon process** are the knob)
- `dify_plugin/core/runtime.py:363-373` — the back-invocation HTTP timeout tuple built from `session.max_invocation_timeout`
- `plugin.py:569` — `max_invocation_timeout=self.config.MAX_INVOCATION_TIMEOUT`
- `/home/administrator/dify/docker/docker-compose.yaml` plugin_daemon environment block — currently lacks both variables

## Root Cause Hypothesis

**High confidence.** The operative 300 s is the dify_plugin library's `MAX_REQUEST_TIMEOUT` default (with `MAX_INVOCATION_TIMEOUT=250` governing the back-invocation read timeout), active in every plugin subprocess because the daemon container never sets these env vars. All previously eliminated components were correct but irrelevant: the row, api, and daemon restarts couldn't affect a library default inside the plugin's own venv process.

## Proposed Remediation

**Preferred**: set both variables in the daemon's environment above the sidecar's 540 s envelope: add to the `plugin_daemon` service's environment block in `/home/administrator/dify/docker/docker-compose.yaml` and the `.env`: `MAX_REQUEST_TIMEOUT=600` and `MAX_INVOCATION_TIMEOUT=600`, then **recreate** the daemon (`docker compose up -d plugin_daemon` — a plain restart does not update env). Expected result: the plugin's back-invocation client tolerates the full envelope; a chat turn that exceeds it ends with the sidecar's honest "Hermes did not finish within 540s" verdict instead of a transport error.

**Alternatives**:
- Patch the library default in the plugin venv — rejected: env vars exist for exactly this; patching adds drift the env avoids
- Live with 300 s — rejected per owner decision (Option A: hunt)

**Files likely to change**:
- `/home/administrator/dify/docker/docker-compose.yaml` (plugin_daemon environment) + `/home/administrator/dify/docker/.env`
- `DEPLOY.md` — document the two variables alongside the provider-row note (both must survive re-deploys)

**Tests to add or update**:
- Live behavioral: re-run the >300 s chat request; expect success or the honest 540 s verdict — never "peer closed connection"

## Risks & Considerations

- `docker compose up -d plugin_daemon` recreates the container (brief plugin unavailability; same recovery path as the restart)
- Both variables must exceed 540 (the envelope) but stay ≤ the daemon's own PLUGIN_MAX_EXECUTION_TIMEOUT (600) — 600 fits exactly
- The plugin venv belongs to a marketplace plugin; env vars from the daemon propagate to plugin subprocesses (confirmed: the daemon env shows 287 vars inherited by plugins) — no plugin re-install needed
- Document in DEPLOY.md: a future Dify upgrade may rename these settings; the re-check command is one `docker exec … env | grep MAX_REQUEST`

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the env knob is the library's documented mechanism; if 600 proves insufficient at the margins, the observed cut time will identify which of the two variables is binding]
