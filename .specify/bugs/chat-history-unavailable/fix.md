# Fix — chat-history-unavailable (2026-11-05)

## Root cause
After the 2026-11-03/04 reboot, the Windows **W3SVC/WAS (IIS)** services auto-started
and, via HTTP.sys, took port 80. In WSL mirrored networking the port namespace is
shared with Windows, so Dify's `docker-nginx-1` lost the boot race for `:80` — it sat
in `Created` state with **no network attachment** (no container IP, no DNAT rules).
Every `localhost:80` request landed on the IIS welcome page (200 on `/`, 404 on
`/v1/*`), which produced the symptom pair:

- Chat UI history proxy: `[history] Dify conversations error (404)` → `502`
- Chat sends fell back to canned demo replies
- The model-swap cycle failed (`cycle failed: Command failed: …`) because the
  deploy CLI's console URL (`http://localhost`) also hits port 80

## What was done
1. Stopped and set **Manual** startup for `W3SVC` and `WAS` on Windows (elevated via
   one UAC-approved PowerShell — the user clicked Yes). This removes IIS from the
   boot race permanently.
2. `docker compose -f /home/administrator/dify/docker/docker-compose.yaml up -d
   --force-recreate nginx` — a plain `docker start` of the stale `Created` container
   left it network-less; the recreate restored its bridge IP and the 80/443 publishes.
3. Re-ran the model cycle the UI had failed: `.venv/bin/python -m
   agentic_rag_mcp.deploy apply-model deepseek/deepseek-v4.1-flash` — export → patch →
   overwrite → publish, 5 steps OK.

## Verification
- `GET http://127.0.0.1/` → 307 (Dify nginx redirect; previously IIS 200 welcome page)
- `GET /v1/conversations?user=probe&limit=1` with the app key → **200**
- apply-model cycle: `ok: 5 steps`
- Chat UI history sidebar loads again (conversations 200 through the proxy)

## Permanence
- IIS is Manual: it no longer starts at boot, so nginx wins `:80` after any reboot.
- If IIS is ever needed again on this host, either keep it off port 80 or remap
  Dify's `EXPOSE_NGINX_PORT` in `/home/administrator/dify/docker/.env` and update
  `ai-chat-landing/.env.local` (`DIFY_API_BASE_URL`) + `[dify] console_url` in
  `~/.config/agentic-rag-mcp/config.toml`.
