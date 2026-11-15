# Bug Fix: windows-mcp chat tools registered + routing nudge — deployed; live E2E pending your desktop reconnect

- **Slug**: does-not-have-a-powershell-windows-mcp-tool
- **Fixed**: 2026-11-14T10:00:00+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — code, tools, DSL, and deploy complete (battery 15/15 with the fixed tools-surface check); the final live probes are pending an environment state, not code: the host service is down because your RDP session is disconnected

## Summary

The verified spec-040 lane is now exposed to the chat as two read-only tools — `windows_mcp_process_list` (deterministic listing, no confirm) and `windows_mcp_status` (honest health) — with both ops added to the loop-gate's exempt set (the v2 fast-path precedent), and a DSL routing nudge so process-listing phrasings take the fast path instead of the read-only run-command lane's ask-back. Deployed via `deploy all` (55 tools synced, chatflow published); the battery's stale 5-ppt-tools expectation was fixed to assert both surfaces explicitly. The final live end-to-end waits on you: the Windows-MCP host service is currently down because your RDP desktop is disconnected — the service refuses to start without an active interactive desktop (its own design), which also retro-explains the `CONTROL_UNAVAILABLE` envelope observed when it was last up.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/server.py` | modified | two new `@mcp.tool()` registrations: `windows_mcp_process_list(limit, sort_by, conversation_id)` (delegates to the lane module; the lane audits through the shared funnel) and `windows_mcp_status(conversation_id)` (probe + audit) |
| `src/agentic_rag_mcp/loop_gate.py` | modified (scope addition, logged) | `windows-mcp-process` + `windows-mcp-status` added to `EXEMPT_OPS` — the sub-second deterministic fast-path precedent; without it every listing would re-grow the protocol rounds this morning's loop-gate bug removed |
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | FAST PATH lane rule: process-listing requests take `windows_mcp_process_list` FIRST (not hermes_run_command's allowlist ask-back, not the two-phase PowerShell); arbitrary PowerShell keeps `hermes_run_powershell`; honest error relay + recovery hint + no-claim-without-call |
| `src/agentic_rag_mcp/deploy/battery.py` | modified | `scenario_tools_surface` now asserts the explicit surfaces (ppt = 6 incl. `ppt_write_v2`, stale at 5 since office v2; windows-mcp = the two read-only tools) — every tool-count change becomes a deliberate battery edit |
| `tests/unit/test_windows_mcp_lane.py` | added tests | `TestChatSurface`: both tools registered; privileged windows-mcp tools deliberately NOT registered (the T019 unprompted-registry-write finding); both ops loop-exempt |

## Diff Highlights (optional)

```python
# server.py — the read-only chat surface
@mcp.tool()
async def windows_mcp_process_list(limit: int = 5, sort_by: str = "memory",
                                    conversation_id: str = "", ...) -> dict:
    from .windows_mcp import process_list as _wmcp_process_list
    return await _wmcp_process_list(sort_by=sort_by, limit=limit,
                                    conversation_id=conversation_id,
                                    audit=HermesAudit(cfg.hermes_audit_path))
```

## Tests Added or Updated

- `test_windows_mcp_lane.py::TestChatSurface::test_both_chat_tools_are_registered` — the chat surface exists.
- `…::test_privileged_windows_mcp_tools_are_not_registered` — the first slice is read-only by design (no clipboard/registry/notification chat tools).
- `…::test_both_ops_are_loop_exempt` — no protocol rounds around the deterministic listings.

## Local Verification

- Commands: `pytest tests/unit/test_windows_mcp_lane.py tests/unit/test_loop_gate.py` → **31 passed**; full `pytest tests/unit` → **677 passed, 0 failed**; `ruff check` → clean; `deploy all` → rebuild + sync-tools (**55 tools** before/after) + chatflow update + publish ✓, verify battery **14/15** — the single failure was the battery's own stale 5-ppt expectation, fixed and re-verified standalone: `tools-surface: PASS | tools=55 ppt=6 … windows-mcp=2 (windows_mcp_process_list, windows_mcp_status)`.
- Live probe of the new tool (first attempt): returned the service's **`CONTROL_UNAVAILABLE`** envelope relayed verbatim — correct honest behavior; diagnosing it exposed the real state below.
- **Environment finding (blocks the final live E2E, not the code)**: your RDP session is **disconnected** (`qwinsta`: session 2 = Disc). The windows-mcp service requires an active interactive desktop for its control engine — it exited when the desktop went away (the `CONTROL_UNAVAILABLE` was it reporting its dying control surface), and its Scheduled Task restart fails with `RuntimeError: No active interactive desktop for physical input control` (server.error.log) while you stay disconnected. The lane's `error:windows-mcp-lane-unavailable` envelope with the recovery hint now covers this state — US2/FR-002 behaving exactly as specified, in production.

## Deviations from Assessment

- Scope addition (logged): `loop_gate.py` touched to exempt the two new ops — the assessment's "keep the change minimal" is honored by *not* re-introducing the protocol-round wait the user fought this morning; one frozenset line + a dated comment.
- The assessment's live replay could not run: the host service's desktop dependency (above) — pending, not failed.

## Follow-ups

- ~~Your action: reconnect + start the service~~ **done** — see the verification addendum below.
- The battery's other 14 checks passed against this build before the tools-surface fix; a routine `deploy verify` will show 15/15 whenever next convenient.
- Upstream note (optional): the windows-mcp service could start its non-control tools (Process listing needs no desktop) without the interactive-desktop requirement — that would let the read-only lane survive disconnected sessions; out of our repo.
- The registry/clipboard/notification windows-mcp tools stay out of the chat slice pending a gate review (T019 finding).

## Verification addendum (2026-11-14, post desktop reconnect)

Two gaps surfaced during the live verification and were fixed in the same lifecycle:

1. **The USER_CONTROL consent-wait protocol** — after the service restart, its first response to a tool call is `{"code": "USER_CONTROL", "wait_seconds": ~7}`: an instruction to WAIT for the desktop user's approval and retry (the gateway's documented "retries USER_CONTROL consent waits" pattern). The lane had classified that wait-signal as a refusal. Fixed in `src/agentic_rag_mcp/windows_mcp/client.py`: `_user_control_wait()` parses the signal, the call loop waits the indicated seconds (bounded) and retries up to 4 times; `classify_refusal` no longer treats the wait-code as a refusal. Pinned in `test_windows_mcp_lane.py` (`test_user_control_is_a_wait_not_a_refusal`). Suite 678 passed after the change; sidecar rebuilt; **live probe then returned ok with the genuine top-5 table**.
2. **The agent-node tool bindings** — the first chat replays showed the agent reading the new DSL rule but reporting "that tool isn't in my available function list": `deploy all` had synced the tools to the Dify DB, but the chatflow's Hermes agent node binds an explicit tools array, and my DSL edit had added only instructions. Fixed: both tools added to the agent node's `tools:` entries in `dify/AGIAssistant/AGI_Assistant.yml` (full descriptions, read-only surface) and republished (`deploy chatflow`).
3. Also observed (known, unchanged): bare phrasings still misroute to General (the parked pre-router decision) — the replay needed the "on my computer" local phrasing to reach the Hermes lane; once there, the fast path worked exactly as specified.
