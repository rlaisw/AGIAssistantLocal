# AgenticRAG — Fresh-Host Deployment Runbook

From `git clone` to a verified MCP sidecar (optionally wired into Dify) on any new host.
The same content ships as the `agenticrag-deploy` skill (`~/.config/kilo/skills/agenticrag-deploy/SKILL.md`).

Runtime state lives OUTSIDE this repo in `~/.config/agentic-rag-mcp/` — a fresh
clone has no config, no LanceDB data, no model checkpoints. Everything below
recreates them.

**Port convention (memorize)**: avoid the crowded common ports on the HOST —
use **28080** for the AgenticRAG sidecar and **28888** for SearXNG. Container ports are
aligned: the number you see IS the port everywhere (host = container). Full topology: [`docs/NETWORK.md`](docs/NETWORK.md).

## Step 0 — Prerequisites (verify before starting)

```bash
git --version && docker --version && python3 --version   # need Python 3.12+
pipx --version || python3 -m pip install --user pipx
df -h ~ | tail -1    # need ~4 GB disk (models) and ~2.5 GB free RAM for the sidecar
```

## Step 1 — Install and initialize

```bash
git clone https://github.com/rlaisw/AgenticRAG.git
pipx install -e AgenticRAG
agentic-rag-mcp --init        # writes ~/.config/agentic-rag-mcp/config.toml (defaults)
```

First use auto-downloads to `~/.cache/huggingface/`: embedding model (~90 MB)
and the Laya decision model (~1.7 GB, ~2 GB RAM loaded). The server pre-loads
it in the background at startup — a first ask before the load finishes falls
back gracefully (provenance: "fallback").

## Step 2 — Tune config for THIS host

Edit `~/.config/agentic-rag-mcp/config.toml`:

```toml
[decider]
timeout = 12.0   # MUST exceed measured warm decision latency on this host.
                 # ~140 ms on Apple Silicon; ~7.4 s on a small ARM cloud CPU.

[web.searxng]
url = "http://searxng:28888"   # container-to-container via Docker DNS (Step 5);
                              # the host port 28888 is NOT used here.
```

Measure the decision latency after the model downloads (Step 6 below), then
set `timeout` comfortably above it.

## Step 3 — Build and run the sidecar

```bash
docker build -f AgenticRAG/dify/docker/mcp-server/Dockerfile -t agentic-rag-mcp:latest AgenticRAG
docker run -d --name agentic-rag \
  --network <DIFY_NETWORK> \
  -v ~/.config/agentic-rag-mcp:/root/.config/agentic-rag-mcp \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -v ~/agentic-rag-docs:/data/rag-docs \
  -v /kilocode/AGIAssistant/ppt-master:/opt/ppt-master \
  -p 28080:28080 \
  -e LOG_LEVEL=INFO \
  --restart always \
  agentic-rag-mcp:latest
```

Logs (spec 008): the server writes a persistent leveled log to
`~/.config/agentic-rag-mcp/logs/server.log` — the mounted volume, so history
survives container recreation. `LOG_LEVEL` (or `[logging] level` in
config.toml) sets the level: INFO for working-as-expected events, DEBUG for
full developer traces; rotation caps the file at `rotation_size_mb ×
rotation_count` (default 10 MB × 5). Frame request lines and application
records land in the same file.

Port rule: the sidecar binds **28080** inside the container, so `-p 28080:28080`
maps HOST 28080 → CONTAINER 28080 (aligned). Host checks use `localhost:28080`;
containers on the Docker network use `agentic-rag:28080`.

## Step 4 — Dify integration (only if this host runs Dify)

1. Find the network names (they differ per compose project): `docker network ls`
   — on the reference host: `docker_default`, `docker_ssrf_proxy_network`.
   Join the sidecar to both (`docker network connect <net> agentic-rag`).
2. **SSRF allowlist (without this Dify shows "Cannot connect to MCP server")**:
   in the Dify compose `.env` add
   `SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=agentic-rag`, then `docker compose up -d ssrf_proxy`.
3. Dify UI → Tools → MCP → Add Server: `http://agentic-rag:28080/mcp`
   (container DNS name + the aligned container port 28080; never `localhost`),
   no headers, no Dynamic Client Registration.
4. Import the chatflow: `AgenticRAG/dify/Chatflow Basic (AgenticRAG Agent + PPT-Master).yml` (the deploy CLI imports/updates it as the app **AGI Assistant**)
   (Studio → Import DSL). Re-select tools in the Agent node if they don't resolve.
5. Rules learned the hard way:
   - Never `localhost`/`127.0.0.1` in the Dify UI — Docker DNS name only.
   - To CHANGE a server: delete + re-add (Dify 1.17's edit path 500s on save).
   - When the server gains/removes tools: refresh Dify's cache (Tools → MCP →
     server → Update), or the agent reports "Tool with name X not found".

## Step 5 — SearXNG (only if web_search is wanted)

**Known behavior — transient empty results**: the upstream engines
(google cse, brave, duckduckgo, wikipedia) periodically CAPTCHA/429 the
instance (`docker logs searxng` shows `SearxEngineCaptchaException` /
`TooManyRequestsException` with ~3-minute suspensions). During those
windows `web_search`/`web_research`/`specialty_search` all return empty —
the agent correctly reports "no results" and answers from general
knowledge (flagged). They recover on their own; repeated probing
*refreshes* the suspensions, so retry after a few quiet minutes. The
engine set in `/home/administrator/searxng/settings.yml` was diversified
(2026-10-27) with mojeek/qwant/startpage/swisscows to reduce
single-provider block windows.

The stock image ships WITHOUT the JSON API enabled — the AgenticRAG provider
uses `format=json`, so create the settings first:

```bash
mkdir -p ~/searxng && cat > ~/searxng/settings.yml <<'EOF'
use_default_settings: true
server:
  secret_key: "change-me-to-a-random-string"
  limiter: false
search:
  formats:
    - html
    - json
EOF

docker run -d --name searxng \
  -v ~/searxng:/etc/searxng \
  -p 28888:28888 \
  --restart unless-stopped \
  searxng/searxng
docker network connect <DIFY_NETWORK> searxng
```

Verify: `curl -s "http://localhost:28888/search?q=test&format=json" -o /dev/null -w "%{http_code}"`
→ must be 200 (403 = JSON not enabled). The sidecar reaches SearXNG via
`http://searxng:28888` inside the Docker network — the host port is only for
your testing. First query after container recreation is slow (engines warm up).

## Step 6 — Ingest sources (LanceDB starts empty)

**Documents folder (spec 023):** the deployment creates and mounts
`~/agentic-rag-docs/` ⇄ container `/data/rag-docs` automatically
(Windows/WSL hosts: the folder is reachable in Explorer at
`\\wsl.localhost\<distro>\home\<user>\agentic-rag-docs\`; a literal
Windows-side folder like `C:\RAGDOCS` works by adding
`("/mnt/c/RAGDOCS", "/data/win-docs")` to the `MOUNTS` list in
`src/agentic_rag_mcp/deploy/docker_ops.py` + `deploy redeploy` + a one-time
`sources_add` — the 9P bridge makes /mnt/c I/O slower than the native WSL
folder). Drop documents there and register the source once:

```sh
curl -s -X POST localhost:28080/mcp -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"sources_add","arguments":{"type":"local_folder","config":{"path":"/data/rag-docs"}}}}'
```

Supported types: `.pdf` (text-based only — encrypted or scanned PDFs are
skipped with a reason), `.docx` (paragraph text), `.xlsx`, `.pptx`.
Audio (`.mp3`/`.wav`/`.m4a`) is scanned but skipped unless the image
installs the `[audio]` extra. `.md`/`.txt` are not scanned. Auto-update:
the watcher re-syncs every 5 minutes; `sources_sync` for instant. Verify
with `sources_list` → `healthy` and `status` (documents/chunks counts).

**Never** register sources under hidden directories (e.g. `~/.config/...`):
the folder scanner excludes dot-directory paths, so such sources silently
ingest nothing. Any other mounted folder works via
`sources_add {"type": "local_folder", "config": {"path": "/data/your-docs"}}`.
A SQLite database in the documents folder registers as its own source:
`sources_add {"type": "sqlite", "config": {"db_path": "/data/rag-docs/faq.db", "table": "faq", "template": "Q: {row[question]} A: {row[answer]}"}}`.

## OneDrive (on-demand) setup

OneDrive sources are **on-demand** (spec 007): connection ingests zero files;
you browse metadata and embed only the files you explicitly confirm. The
watcher never touches OneDrive.

**Azure app registration (one-time):**

1. Register an app in Entra ID; note the **client_id**
2. Add delegated permission **`Files.Read`** (Microsoft Graph) and grant consent
   — that is the only permission needed; `offline_access` is requested by MSAL
   automatically (never pass it explicitly — MSAL rejects reserved scopes)
3. If the app is **single-tenant**, note the **tenant_id** — it MUST be passed
   at `sources_add` (a `common` authority cannot see single-tenant apps, and
   the device flow will fail to start)
4. Optional app-only path: `client_secret` + **application** `Files.Read.All`
   requires a target `user` (UPN) in the config; the delegated device flow
   above is the normal path and needs no secret

**Connect (via the Dify chat or any MCP client):**

```
sources_add {"type": "onedrive", "config": {"client_id": "<id>", "tenant_id": "<tenant>"}}
sources_auth {"source_id": "<id>"}     → returns sign_in_url + user_code
```

Visit https://login.microsoft.com/device, enter the code, sign in with the
account that owns the OneDrive — complete ALL steps to "You may now close
this window". The connection completes automatically within seconds (the
background thread completes the same flow whose code you entered).

**Then:** `onedrive_list_files` to browse (nothing downloads), confirm the
matches, `onedrive_embed_files` for exactly the confirmed files. Answers citing
a cloud-changed file carry a staleness reminder; re-embedding is always your
explicit command.

## Step 6b — Specialty search profiles (optional, for domain-scoped questions)

Create `~/.config/agentic-rag-mcp/specialty_profiles.json` with your domain profiles:

```bash
cat > ~/.config/agentic-rag-mcp/specialty_profiles.json <<'EOF2'
{
  "microsoft": {
    "sites": [
      "learn.microsoft.com",
      "techcommunity.microsoft.com",
      "educba.com",
      "alitajran.com",
      "newhelptech.wordpress.com"
    ],
    "description": "Microsoft product documentation and community"
  },
  "huawei": {
    "sites": ["support.huawei.com", "forum.huawei.com"],
    "description": "Huawei networking and enterprise products"
  }
}
EOF2
```

Hot-reloaded: edit the file at any time — new profiles are usable on the very
next search call, no restart needed. The Dify agent calls `specialty_profiles()`
first to discover available topics, then picks the right profile for the question.

## Step 7 — Verify (the 5-minute battery)

```bash
curl -s localhost:28080/healthz                                  # {"status": "ok"}
curl -s -X POST localhost:28080/mcp -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'   # 26 tools (16 + 5 ppt_* + 2 antv_* + hermes_file_task + hermes_launch_app + hermes_office_task)
# then exercise: status, search, ask, sources_list, sources_add/sync/remove,
# web_search (live), fetch_url (live), graph_query (honest disabled error)
```

## Step 8 — Chat UI (optional, web frontend for the Dify chatflow)
[`ai-chat-landing/`](ai-chat-landing/) streams the AgenticRAG agent's answers in a Chatbot-UI-style web app. Requires Step 4 (Dify running + chatflow imported).

```bash
cd ai-chat-landing && pnpm install
# Dify UI → AgenticRAG app → API Access → Create Secret Key (format app-…)
cat > .env.local <<'EOF'
DIFY_API_BASE_URL=http://localhost/v1
DIFY_API_KEY=app-your-key-here
EOF
pnpm dev        # http://localhost:3000
```

The API key stays server-side — the Next.js route handler `app/api/chat/route.ts` proxies `/api/chat` → Dify `/v1/chat-messages`, and `.env.local` is git-ignored. Without a key the UI runs in demo mode with canned replies. Never run `pnpm build` while `pnpm dev` is up in the same directory (they share `.next/`). Details: [`ai-chat-landing/README.md`](ai-chat-landing/README.md). Layout acceptance (spec 016): `node ai-chat-landing/scripts/wide-layout.mjs` measures the wide chat column via CDP (Chrome on `--remote-debugging-port=9240`); `--smoke` adds the behavioral checks (history buckets, Load more, PDF export, delete). Remote access from other machines: `next.config.ts` lists `allowedDevOrigins` (the host LAN IP) — add any new access origin there and restart `pnpm dev`, or the page renders but nothing is interactive.

## Step 9 — PPT-Master deck generation (optional, spec 009)

Lets users type "help to generate a powerpoint, introduce Dify software" in the chat and receive a native editable `.pptx` download link. Requires the ppt-master clone (Step 0 of its own README: `git clone https://github.com/hugohe3/ppt-master.git` into the repo root, `python3 -m venv ppt-master/.venv`, install its requirements) plus the sidecar rebuilt with the ppt mount (Step 3 above includes `-v .../ppt-master:/opt/ppt-master`; the image bakes the export-path deps).

1. Rebuild + recreate the sidecar (Step 3), verify 26 tools: `tools/list` shows `ppt_project_init`, `ppt_icon_sync`, `ppt_write_page`, `ppt_check`, `ppt_export`, plus `antv_chart` and `antv_infographic` (spec 012, Step 11), `hermes_file_task` (spec 028, Step 12), `hermes_launch_app` (spec 029), and `hermes_office_task` (spec 030 — needs the Windows-side Office automation service running and the gateway wired: `officemcp sse --port 8888 --host 127.0.0.1 --folder C:\OfficeMCP` on Windows, then `yes | hermes mcp add OfficeMCP --url http://127.0.0.1:8888/sse` on the host).
2. Dify UI → Tools → MCP → the server → **Update** (cache refresh; new tools appear).
3. Import the chatflow v2 DSL: `dify/Chatflow Basic (AgenticRAG Agent + PPT-Master).yml` — adds an intent router (deck requests → PPT-Master agent, everything else → the existing AgenticRAG agent). Publish.
4. Verify: ask for a one-page deck on a known topic; expect progress narration, then a `[Download the deck](http://localhost:28080/exports/<project>/<file>.pptx)` link that downloads a valid PowerPoint. Exported decks land under `ppt-master/projects/<project>/exports/`.

Notes: v1 bounds decks at 5 pages per run (`[ppt] max_pages` in config.toml); same-conversation revisions re-export a new file (old links keep working); the `/exports` route is unauthenticated on the local-trust network, same posture as `/healthz`. Honest failure: a deck with pages that cannot pass the quality check is never exported — the agent reports the failing page instead.

`[ppt]` config reference:

| Key | Default | Purpose |
|---|---|---|
| `scripts_root` | `/opt/ppt-master/skills/ppt-master` | where the ppt-master clone is mounted (host path works when running locally) |
| `projects_root` | `/opt/ppt-master/projects` | serving root for `/exports`; projects always live at `<ppt-master>/projects` (the toolchain hardcodes it), so keep these aligned |
| `python` | `""` (= `sys.executable`) | interpreter for the ppt-master scripts — in the container the image bakes the deps, so the default works; host-side, point it at `ppt-master/.venv/bin/python` |
| `max_pages` | `5` | v1 page bound (spec 009) |
| `script_timeout_s` | `120` | per script invocation timeout |
| `retention_days` | `0` | `0` = keep exports forever (v1) |

**Completion pages & in-chat actions (spec 010)**: every export also returns an additive `page_url` — `GET /decks/<project>/<stem>/` on the same port serves a browser completion page (per-slide previews snapshotted at export time, download button, back-to-chat edit path; honest degraded state if preview generation failed). Slide assets: `GET /decks/<project>/<stem>/slides/<file>.svg`. The AGI Chat UI renders deck links in answers as an action bar (Download / Preview-Edit icons) via its markdown interceptor — the Dify webapp shows the plain link (graceful degradation). Chat UI tests: `pnpm test` (vitest) inside `ai-chat-landing/`.

## Step 10 — Deployment automation (spec 011)

difyctl note (spec 024): the Dify CLI needs `OPENAPI_ENABLED=true` in
`docker/.env` (1.18.0 Community defaults it to **false** — without it the
whole `/openapi/v1/*` group, including the OAuth device flow, 404s) plus an
API container restart. Install: `curl -L -o ~/.local/bin/difyctl
https://github.com/langgenius/dify/releases/download/1.18.0/difyctl-v1.18.0-linux-x64`
(checksum-gate against the release's checksums file before executing); skill:
`difyctl install skills ~/.config/kilo/skills`; login:
`difyctl login --server http://localhost --insecure --no-browser --no-wait`
(approve in browser). The round-trip script lives at
`dify/difyctl-export-reimport-publish.sh` (export → re-import → publish →
verify integrity).



One command rebuilds, redeploys, updates the chatflow, and verifies the whole stack — no Dify UI actions, no prompts:

```bash
VENV=/home/administrator/.local/share/pipx/venvs/agentic-rag-mcp/bin/python

# configure once (config.toml or env):
#   [dify] console_email / console_password  (Dify console login; env: DIFY_CONSOLE_EMAIL/PASSWORD)
#   [dify] api_key                            (chatflow service key; env: DIFY_API_KEY)

$VENV -m agentic_rag_mcp.deploy verify --dry-run   # plan only, touches nothing
$VENV -m agentic_rag_mcp.deploy redeploy            # build → recreate → health → register/re-sync tools
$VENV -m agentic_rag_mcp.deploy chatflow            # draft-update or import + publish the DSL
$VENV -m agentic_rag_mcp.deploy verify              # 15-scenario headless battery (self-cleaning; stop-generation 2026-10-28, hermes-file-task 2026-10-31, hermes-launch-app 2026-11-01, hermes-office-task 2026-11-02, office-routing guard 2026-11-02)
$VENV -m agentic_rag_mcp.deploy cleanup             # prune deck projects older than [deploy] retention_days (default 30; 0 = keep forever)
$VENV -m agentic_rag_mcp.deploy all                 # everything, aborting honestly on failure
```

Behavior: exit 0 = success · N = failed battery scenarios · 2 = configuration error. Tool-cache re-sync is version-gated (DB path for Dify 1.17.x — the console Update flow doesn't re-sync tools in that version; unknown versions are skipped with a notice). The chatflow command updates the app **in place** (draft + publish — app id and API key preserved) and only imports when no same-name app exists. Console credentials are never logged (masked). Tests: `pytest tests/unit/test_deploy_* tests/integration/test_deploy_console.py tests/contract/test_deploy_cli.py`.

## Step 10b — Local AI model (spec 025, "AI LLM" drop-down)

The Chat UI's model selector offers a local Qwen3 8B alongside the cloud DeepSeek. Prerequisites on the host (rootless, no systemd unit — restart after reboot):

```bash
# Ollama (rootless install; server must bind 0.0.0.0 so Dify's containers reach it)
curl -fsSL -o /tmp/kilo/ollama.tar.zst https://ollama.com/download/ollama-linux-amd64.tar.zst
mkdir -p ~/ollama && tar --zstd -xf /tmp/kilo/ollama.tar.zst -C ~/ollama
ln -sf ~/ollama/bin/ollama ~/.local/bin/ollama
OLLAMA_HOST=0.0.0.0 setsid nohup ollama serve > ~/ollama/serve.log 2>&1 < /dev/null &

# The no-think model (FR-009: reasoning disabled; Dify nodes add think:false too)
ollama pull qwen3:8b
ollama create qwen3-8b-nothink -f dify/AGIAssistant/ollama/qwen3-8b-nothink.Modelfile
```

Register the model inside Dify (installs the marketplace Ollama plugin when
absent, then registers `qwen3-8b-nothink` as a custom LLM pointing at the
docker-bridge address `http://172.17.0.1:11434`, plus the extra OpenRouter
cloud models for the grouped menu — idempotent, safe to rerun):

```bash
$VENV -m agentic_rag_mcp.deploy models
```

Apply a cloud model to the chatflow itself (spec 026, what the Chat UI's
"AI LLM" menu calls server-side): export → patch the three main LLM nodes
→ overwrite the draft → publish. The published app is untouched until the
publish step, so a failure leaves the previous configuration serving; the
exported artifact (`dify/AGIAssistant/AGI_Assistant.yml`) mirrors the
published app and is git-versioned for recovery:

```bash
$VENV -m agentic_rag_mcp.deploy apply-model moonshotai/kimi-k3
$VENV -m agentic_rag_mcp.deploy apply-model deepseek/deepseek-v4.1-flash  # back to default
```

Notes: the chatflow routes on the `ai_model` start input (`local` → the three
`*_local` nodes; absent/anything else → the configured cloud model — the
battery sends no input and stays byte-identical). Cloud selection is global:
the Chat UI's model menu applies it via `deploy apply-model` (spec 026).
Extra cloud models (`z-ai/glm-5.3-flash`, `qwen/qwen3.8-flash`) are
registered as OpenRouter custom models by the same `models` command (the
openrouter plugin was upgraded to 0.1.12 for this; `moonshotai/kimi-k3`
ships in its catalog). The Chat UI probes availability host-side via
`GET /api/models`; a stopped Ollama degrades to the configured cloud model
with a persistent inline note (FR-004), never a fabricated reply. Config keys:
`[deploy] ollama_base_url` (default `http://172.17.0.1:11434`),
`ollama_model` (default `qwen3-8b-nothink`). Live checks:
`node ai-chat-landing/scripts/model-dropdown-check.mjs A|B|C1|C2|D`.

## Step 11 — AntV visualization tools (spec 012)

Two additive MCP tools on the sidecar: `antv_chart(chart_type, data, title)` — statistical charts (bar/line/pie/radar/sankey/…; geography types excluded) rendered by the GPT-Vis service, returning an embeddable image URL; `antv_infographic(description)` — declarative infographics rendered browser-side at `GET /infographics/<id>/` (engine loads from CDN; no server-side DOM). Deck pages referencing remote chart images are exported **self-contained** — the pipeline downloads and embeds image bytes at page-write time (misformat sniffed from bytes; fetch failure = honest gate error).

**Data posture**: by default chart data travels to the AntV public rendering service (`https://antv-studio.alipay.com/api/gpt-vis`) and images are hosted on its CDN — outbound internet required, chart data leaves the network. For private rendering, deploy [GPT-Vis-SSR](https://github.com/antvis/GPT-Vis/tree/main/bindings/gpt-vis-ssr) and set `[antv] chart_service_url` in config.toml (geography chart types are not supported privately; they are excluded regardless). Infographic syntax stays local — only the rendering engine script loads from CDN in the browser. Config keys: `[antv] chart_service_url`, `chart_timeout_s`, `max_inline_image_bytes`, `infographic_max_syntax_bytes`.

**Operator notes**:

- The chatflow agent is driven by the DSL's `tool_description`, not the server docstring. After changing the `antv_infographic` docstring: update both description fields in the chatflow DSL YAML, then `python -m agentic_rag_mcp.deploy chatflow`. A stale description makes the model anchor on one template (every infographic comes out the same style).
- Generated visuals are routed by the agent instruction per output type (rule added 2026-10-27, in both agentic nodes' IMAGES section): `antv_chart` returns `image_url` → inlined as `![title](image_url)`; `antv_infographic` returns an interactive HTML page → given as a labeled markdown link (it cannot be inlined with `![]()`). If answers link charts instead of showing them, or inline infographic URLs, the DSL agent instruction is stale — republish with `deploy chatflow`.
- Template menu: ~276 presets across 8 families (chart, sequence, sequence-interaction, list, hierarchy, relation, compare, quadrant). Key picks: true triangle pyramid = `sequence-pyramid-simple` (`list-pyramid-*` renders stacked badge rows, NOT a triangle); org charts = `hierarchy-structure` / `hierarchy-tree-*`; UML flows = `sequence-interaction-default-compact-card` — message children need `id` + `step` fields and `relations` reference those MESSAGE ids, or arrows don't draw.
- Page gotchas: the served page must close the CDN script tag with a literal `</script>` (an escaped `<\/script>` makes the browser swallow the inline render script → blank page, no errors). Don't add "svg has ≥ 20 chars of text" health checks — sparse-but-valid charts get nuked by them. The page is served with `Cache-Control: no-store` + a `page-version` marker.
- Content sizing per template (seen 2026-10-28): `sequence-snake-steps` and other tight zig-zag layouts want terse content — labels ≤ 5 words, descs ≤ ~8 words, ≤ 6–8 steps; long multi-line descs overlap into unreadable text. For long text prefer `sequence-steps` or `list-row-simple-horizontal-arrow`, or split into two infographics.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Dify: "Cannot connect to MCP server" | SSRF proxy blocks private targets | Step 4.2 allowlist + restart ssrf_proxy |
| `agentic-rag:28080` refused from a container | Wrong path | Container-to-container port = host port (aligned) |
| `localhost:8080` refused on host (old port, now gone) | Old port freed by alignment | Use `localhost:28080` |
| Dify save/edit of MCP server → 500 | Dify identifier-vs-UUID bug | Delete the entry, re-add |
| Every decision is `provenance: "fallback"` | timeout too small for this host | Raise `[decider] timeout` above measured latency |
| `web_search` returns empty | No SearXNG / JSON disabled / not on network | Step 5 (settings.yml + network + 200 check) |
| SearXNG JSON returns 403 | `formats` missing json | Add `- json` to settings.yml, restart container |
| Tool not found after server update | Dify's cached tool list is stale | Update tools in Dify's MCP page |
| Sidecar OOM-killed / host low on RAM | Decision model ~2 GB resident | `[decider] enabled = false` + restart = instant relief |
| Edited file's changes don't appear in answers | Wait for the 5-min watcher cycle or run `sources_sync` | Auto-update replaces old chunks (eviction fix, commit 5c9b4ae) |
| OneDrive device flow fails to start | Single-tenant app + `common` authority, or a reserved scope passed explicitly | Pass the real `tenant_id` at `sources_add`; never include `offline_access`/`profile`/`openid` in scopes — MSAL adds them internally |
| Device sign-in stays "pending" forever | Browser flow not completed (or code expired after 15 min) | Re-run `sources_auth`, complete ALL browser steps to "You may now close this window" — the background thread completes the same flow whose code you entered |
| No DEBUG detail in the log file | Level is INFO | `-e LOG_LEVEL=DEBUG` + recreate; confirm via `status` → `logging.level` |
| Infographic page blank in browser, no errors | Page served by a pre-fix image (escaped `<\/script>` swallowed the inline script), or stale chatflow | Rebuild the sidecar from current source (`deploy redeploy`); page serves `Cache-Control: no-store`, so a plain refresh suffices |
| Agent always renders the same infographic style | Chatflow DSL `tool_description` is stale (model never sees new template names) | Update both description fields in the DSL YAML + `deploy chatflow` |
| UML sequence diagram renders without arrows | Messages lack `id`/`step` fields, or relations point at participant labels instead of message ids | Give each message `id X` + `step N`; relations `- from m1 / to m2 / label …` |
| Image build hangs at the pip layer (20+ min, ~0 CPU, frozen sockets) | Stalled multi-GB CUDA torch wheel download — pip has no per-socket timeout (seen 2026-10-22; first attempt dead at 25 min) | Kill and rerun `deploy all` — COPY layers are cached, only the download repeats; to cut the download ~10×, force CPU-only torch per the Dockerfile header note (`pip install --index-url https://download.pytorch.org/whl/cpu torch` before the main install) |
| Exported PDF drops remote images that display fine in chat | Pre-2026-10-28 Chat UI: html2canvas-pro rasterizes with `useCORS` and remote hosts without ACAO headers silently drop out of the PDF | Pull current `ai-chat-landing/` — the export path rewrites remote images through the same-origin `app/api/image-proxy` before rasterizing; failures degrade to labeled links |
| Model links a chart instead of showing it, or inlines an infographic URL as an image | DSL agent-instruction generated-visuals rule is stale (charts inline via `image_url`, infographics link — rule added 2026-10-27) | `python -m agentic_rag_mcp.deploy chatflow` to republish the artifact instruction |
| Scatter chart renders an empty frame (axes, no points) | GPT-Vis scatter plots `x`/`y` numerics only — `category`/`value` records are ignored by the renderer (verified 2026-10-28: image bytes don't scale with point count) | Fixed 2026-10-28: `antv/charts.py` auto-maps numeric `category`/`value` pairs to `x`/`y` and the tool description documents the shape; if it regresses, check the sidecar runs the patched `charts.py` (docker cp) and the DSL `tool_description` is synced |
| Chat UI "Stop" click stops the view but the backend keeps generating (answers grow after reload) | `/api/chat/stop` failing upstream (Dify down / proxy 502) — the client aborts locally regardless; the backend halt is verified by the battery's `stop-generation` scenario | Check the Dify stack (`docker ps`); rerun `python -m agentic_rag_mcp.deploy verify` — a persistent 502 there is a defect, not a client bug (spec 027 FR-006) |
| An agent node (e.g. PPT-Master) fails in ~59 ms with `object of type 'NoneType' has no len()` — deck questions return empty answers | Null variable selectors (`{"type": "variable", "value": null}`) exported onto agent params crash Dify 1.18's `variable_pool.get(None)` before any LLM/tool call (bug ppt-no-response, fixed 2026-10-29) | Re-run the model apply (`/api/models/apply` or `$VENV -m agentic_rag_mcp.deploy chatflow`) — `strip_null_variable_params` in `deploy/model_apply.py` normalizes every apply cycle; regression-pinned in `tests/unit/test_deploy_model_apply.py` |
| A cloud turn fails with OpenRouter 403 "This model is not available in your region" | Transient OpenRouter endpoint geo-gating (observed once 2026-10-29) — independent of the chatflow config | Usually transient — retry or apply a different model; distinct from the deterministic len(None) failure above |
| Hermes file tasks all return `error:Hermes gateway unreachable` | The host Hermes gateway (or its API server on `172.17.0.1:8642`) is down, or the key drifted between `~/.hermes/.env` (API_SERVER_KEY) and the sidecar's `[hermes]` config (spec 028) | Start it with `hermes gateway restart -y --detach`; verify `curl -H "Authorization: Bearer <key>" http://172.17.0.1:8642/v1/models`; re-align the key in both places if it drifted |
| A file task answers `blocked` unexpectedly | The gate is doing its job: target outside the active root, a delete/rename/move request (v1 scope), or no location named (ask-back) — the reason always names the active root and scope (spec 028 FR-004/011/014) | Read the reason: give the location when asked back; out-of-scope operations are declined by design — the audit log (`~/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl`) records every verdict |
| New sidecar MCP tool errors "Tool with name X not found" in the chatflow | Dify caches the MCP provider's tool list in `tool_mcp_providers` at registration — a console Update or chatflow publish NEVER re-syncs it (old gotcha; hit again 2026-10-31 with hermes_file_task, and 2026-11-01 with hermes_launch_app) | Rebuild `tools` from the live sidecar `tools/list` (25-entry list: name/title/description/inputSchema), UPDATE the row, and restart `docker-api-1` + `docker-worker-1` — the `tool_sync` db-resync path now supports Dify **1.18** as well as 1.17 (schema validated live 2026-11-01, spec 029), so `deploy redeploy` re-syncs automatically; the antv/ppt/contract snapshot tests were amended to the current 25-tool surface the same day |
| Hermes-branch answers start with a literal `agentic_strategy.text…` prefix | Known Dify 1.18 rendering: the shared Answer merge node prints variable references for nodes that didn't run in that branch (pre-existing since the 1.18 upgrade — reproduces on the 028-era DSL; spec 029 T021 documented it) | Cosmetic — the lane's verdict text follows immediately after the prefix; a topology fix (per-branch answer nodes) is deferred |
| Office tasks answer `error` naming the Office automation service | The Windows-side OfficeMCP service isn't running, or the gateway's MCP connection to it is stale (seen 2026-11-02: the gateway SIGTERMs on service-manager rotation and a stale session stalls turns to the 300 s budget) | Start it on Windows: `officemcp sse --port 8888 --host 127.0.0.1 --folder C:\OfficeMCP` (launchable via WSL interop), wire once with `yes \| hermes mcp add OfficeMCP --url http://127.0.0.1:8888/sse`, and restart the gateway (`hermes gateway restart -y --detach`) to re-establish the MCP session — the lane's error carries this exact hint |
| Agent steps fail with `TheOfficer object has no attribute 'IsFileExists'` | OfficeMCP v1.0.5 upstream bug: the exposed `IsFileExists` tool calls `Officer.IsFileExists`, but the implementation is misspelled `IsFileExits` — the tool always raises (found live 2026-11-02) | The sidecar's `OFFICE_INSTRUCTIONS` tell the agent not to use that tool (verify by opening files instead); a one-line fix exists upstream (`OfficeMCP.py` line 106) if you choose to patch the installed package |
| Office tasks refused for `c:\temp`-style save locations | Historical (2026-11-03, bugs no-powerpoint-tool + spec 031): spec 031 removed the work-folder boundary — save/read at any named location works; unnamed saves use the default `C:\OfficeMCP` (owner-configurable via `office_root` in the `[hermes]` config section) | No action — any named location saves; only the OS's own permission rules protect system folders (honest error relay, never a fabricated success) |
| Office agent turns hang to the timeout with `RunPython` "arguments stripped" / "returned only the default echo" | **Recurring known defect** (officemcp-connection-error, hermes-agent issue #148459): the gateway's MCP client drops tool-call **arguments** — the OfficeMCP server receives the call with empty args and executes the default snippet. **2026-11-05 model (args-capture evidence, `C:\temp\officemcp_calls.log`): the strip oscillates on its own schedule** (a stripped phase outlasted 71 idle minutes and 15-canary bursts; waiting and canary-retrying are both unreliable; restarts can re-arm it). Args-free tools work throughout. **Proven bypass (live 2026-11-05): the agent's browser/fetch tool talks MCP-SSE directly to `http://127.0.0.1:8888/sse` and delivers full arguments while the gateway client is stripped** — the defect is isolated to the gateway's MCP client serialization | **Recovery (deployed in the agent's instructions): after 2 canary echoes the agent switches to the direct browser MCP channel and finishes the task there — no restart, no wait.** If OfficeMCP itself is unreachable, start it (`officemcp sse --port 8888 --host 127.0.0.1 --folder C:\OfficeMCP`) — but **do NOT restart the gateway, re-register OfficeMCP, or restart OfficeMCP to fix the strip** (each can re-arm it). **Durable fix is upstream** — hermes-agent #148459: argument serialization drops params in an oscillating pattern |
| Hermes file tasks succeed but files never appear in Windows Explorer | WSL drive automount is disabled: `/etc/wsl.conf` has `[automount] enabled=false`, so `/mnt/c` is a plain Linux directory — file tasks write to the WSL virtual disk, not the real `C:` (seen 2026-10-31) | Set `[automount] enabled=true` in `/etc/wsl.conf`, `wsl --shutdown` from Windows, reopen WSL, restart the stack (Docker auto-starts; `hermes gateway restart -y --detach`; chat UI `pnpm dev`); verify with `ls /mnt/c/` showing `Users`, `Windows`, etc. and `stat -f /mnt/c` reporting `v9fs` |
| Program launches return honest errors naming WSL interop / vsock | WSL interop is disabled (`/etc/wsl.conf` `[interop] enabled=false`) or the WSL–Windows vsock channel is down (often after a Windows sleep/resume) — no WSL-side executor can start Windows programs (seen 2026-11-01, spec 029) | From Windows PowerShell: `wsl -u root sed -i 's/^enabled=false$/enabled=true/' /etc/wsl.conf` then `wsl --shutdown`, reopen WSL, restart the stack + Hermes gateway; the lane answers honestly with this hint until interop works |
| A launch answers `blocked` naming the no-arguments / executables-only rules | The launch gate is doing its job: the prompt carried launch arguments/command-line/shell phrasing, or named a script (`.bat/.cmd/.ps1`) or shortcut (`.lnk`) instead of a program, or named two applications (spec 029) | Read the reason; relaunch one program by bare name or full `.exe` path with nothing attached — the audit log records every verdict |
| Launch prompts get a general answer instead of the Hermes lane | Dify holds TWO "AGI Assistant" apps: `deploy chatflow` publishes to the first name match, but the chat API key can belong to the other app (seen 2026-11-01 — publishes went to the orphan `7863fbe2`, chat ran on `194e1edf`) | Publish to the app that owns the chat key (check `GET /apps/{id}/api-keys`), or delete the orphan duplicate; the DSL is single-source either way |
| Deck scenarios fail `PPT_SCRIPT_FAILED` / `KeyError: 'project_id'` after `deploy all` | `deploy all` bind-mounts `<repo>/ppt-master` at `/opt/ppt-master`, but the ppt-master clone is gitignored — a fresh workspace has none; docker auto-creates the host dir root-owned and the tools find no `skills/ppt-master` (seen 2026-11-01) | Populate the clone in this workspace: if docker already made root-owned dirs, first `docker run --rm -v <repo>:/w agentic-rag-mcp:latest sh -c "chown -R 1000:1000 /w/ppt-master"`, then `tar -C /kilocode/AGIAssistant/ppt-master --exclude=./projects -cf - . \| tar -C <repo>/ppt-master -xf -` — the bind mount is live, no container restart needed |
| Chat UI loads from another machine but nothing is interactive | Next dev blocks cross-origin requests without an `allowedDevOrigins` entry (page renders, hydration dead) | Add the access origin to `allowedDevOrigins` in `ai-chat-landing/next.config.ts` and restart `pnpm dev` |

> **Note (close-excel-wait-long-time, 2026-11-06)**: the live Dify DB row
> `tool_mcp_providers` for `agentic-rag` has `timeout` raised 30 → 300
> (long office turns need it; `sse_read_timeout` is 300 by default). This row
> is not in git — **re-apply after any provider re-sync** (`sync-tools` /
> db-resync may reset it):
> `docker exec docker-db_postgres-1 psql -U postgres -d dify -c "UPDATE tool_mcp_providers SET timeout = 300 WHERE name = 'agentic-rag';"`
