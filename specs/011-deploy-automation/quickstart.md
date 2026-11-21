# Quickstart — Deployment Automation Validation Guide

Runnable end-to-end validation for spec 011. Prereq: the stack from DEPLOY.md running (Dify + sidecar + chatflow published at least once).

## 1. Configure credentials (once)

```bash
python3 - <<'EOF'
import tomllib, pathlib
# add to ~/.config/agentic-rag-mcp/config.toml:
# [dify]
# console_url = "http://localhost"
# console_email = "administrator@tvb.com.hk"
# console_password = "<your console password>"
# api_key = "app-..."   # the chatflow's service API key (same one ai-chat-landing uses)
EOF
```

Or export `DIFY_CONSOLE_EMAIL`, `DIFY_CONSOLE_PASSWORD`, `DIFY_API_KEY`.

## 2. Run the automated battery

```bash
VENV=/home/administrator/.local/share/pipx/venvs/agentic-rag-mcp/bin/python
$VENV -m agentic_rag_mcp.deploy verify --dry-run   # prints the plan, touches nothing
$VENV -m agentic_rag_mcp.deploy verify             # full battery incl. chat-journey
$VENV -m agentic_rag_mcp.deploy verify --skip-chat # without the service-API scenario
```

Expected: per-scenario PASS lines with evidence, a summary (failures first if any), exit 0.

## 3. Full automation pass

```bash
$VENV -m agentic_rag_mcp.deploy all
```

> **Host caveat (2026-11-21):** this host has two live apps both named `AGI Assistant`, so name-based `deploy all`/`chatflow` can publish to the wrong app. Use `deploy redeploy`, publish both apps by explicit ID, then `deploy verify`.

Expected: image rebuild → container recreate → health ok → MCP registration ensured (or tool cache re-synced with before/after counts, e.g. `21 → 21` or `16 → 21`) → chatflow draft-updated and published → battery green. Zero prompts, zero UI actions.

## 4. Automated test battery (developer)

```bash
$VENV -m pytest tests/unit/test_deploy_config.py tests/unit/test_deploy_sync_payload.py \
  tests/integration/test_deploy_console.py tests/contract/test_deploy_cli.py -v
$VENV -m pytest          # whole suite incl. spec 009/010 (P16)
```

## 5. Fresh-host proof (optional)

On a new host: follow DEPLOY.md Steps 0–4 (Dify compose up), then set credentials and run `all` — the MCP registration, chatflow import, publish, and verification all happen unattended (spec SC-001).

## 6. Honest-failure spot checks

| Do | Expect |
|---|---|
| Wrong console password | exit 2 at the login step with renewal instructions; no partial mutation |
| Stop the sidecar mid-`all` | health-wait times out with a bounded-timeout message; battery never runs |
| Re-run `all` on a healthy stack | idempotent: no duplicate registrations/imports; counts unchanged |
