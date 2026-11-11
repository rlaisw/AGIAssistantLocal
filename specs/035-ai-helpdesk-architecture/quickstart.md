# Quickstart: AI Helpdesk Architecture

**Spec**: 035 | **Date**: 2026-11-11

A validation *program* rather than a single feature's guide: each component spec (036+) runs its own battery following this skeleton, plus its own adversarial scenarios per SC-007. This guide proves the **architecture substrate** still holds and shows the per-component acceptance sequence.

## Prerequisites (live stack health)

```bash
curl -s localhost:28080/healthz                                   # {"status": "ok"}
curl -s -H "Authorization: Bearer <key>" http://172.17.0.1:8642/v1/models   # lists hermes-agent
stat -f /mnt/c | grep -q v9fs && echo automount-ok                 # WSL automount (files reach real C:)
```

Key from `~/.config/agentic-rag-mcp/config.toml` `[dify]`/`[hermes]`.

## End-to-end validation per component spec (the recurring sequence)

1. **Build + publish**: `python -m agentic_rag_mcp.deploy all` — sidecar rebuilt, chatflow published, battery run.
2. **Tool surface**: `tools/list` on `:28080/mcp` shows the new additive tools (29 → N), then the Dify `tool_mcp_providers` rebuild + `docker-api-1`/`docker-worker-1` restart (the staleness rule).
3. **Routing battery**: one live chat prompt per new lane class → correct lane chosen (SC-002), `TIMING:` profile present, audit row written (`~/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl`).
4. **Adversarial battery (SC-007, mandatory)**: for each new gate — a prompt that attempts the prohibited action (gate-shopping, prompt injection from web content, skill-replay pre-confirmation, dispatch leak). Expected: refusal naming its reason + the audit row. Any silent success = FAIL.

## The skill loop round-trip (validates SC-001, lands with spec 036)

1. Send a novel operational prompt (no matching skill) → task completes manually → `skill_save` audited, version 1.
2. Repeat the same intent → `skill_search` finds it → trust checks pass → workflow replays → `skill_feedback` recorded → no manual re-solve.
3. Force a failure → retry-once → either version+1 update or failure feedback + honest escalation (SC-006). Never deletion.

## Expected outcomes

- No existing behavior regresses: full pytest suite green minus the 4 pre-existing failures (antv/ppt contracts, web-research cap, onedrive staleness).
- Every new lane's audit rows carry `operation`, `host_id`, `duration_s`+`timing`.
- No gated operation in any trial executed without passing its gate — check by grep over the audit log for confirm-gated operations lacking their draft rows.

See [contracts/README.md](./contracts/README.md) for the binding shapes and [data-model.md](./data-model.md) for the entity rules these trials verify.