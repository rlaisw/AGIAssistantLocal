# Agentic RAG MCP Server

Agentic retrieval-augmented generation as an MCP server, with a **dual-system workflow**: an embedded structured **decision node** (System 1) routes every request, and a **LangGraph reflexion graph** (System 2) handles complex questions with self-correcting, memory-conditioned retries. Includes the **Hermes Local Agent lanes** — spec 028's security-gated `hermes_file_task` (Windows file operations create/write/read/list inside an allowed root `C:\temp` via `/mnt/c/temp`, through the host Hermes gateway, append-only audit log) and spec 029's `hermes_launch_app`: launches any Windows executable by name or full `.exe` path — never with arguments, never scripts/shortcuts — gated and audited the same way. 241 unit tests, contract-preserved responses, provenance on every decision.

Specs: [`specs/001-agentic-rag-mcp/`](specs/001-agentic-rag-mcp/) (server, ingestion, contracts) · [`specs/002-laya-reflexion-nodes/`](specs/002-laya-reflexion-nodes/) (dual-system replacement — supersedes 001's routing/loop design).

> **Deploying to a new host?** Follow [`DEPLOY.md`](DEPLOY.md) — the complete clone-to-verified runbook (install, config, sidecar, Dify wiring, SearXNG, verification, troubleshooting). **Port convention**: host ports avoid the crowded defaults — sidecar **28080**, SearXNG **28888** (aligned: container port = host port).

## Architecture

```
question ──► System 1: embedded Laya decision model (one pass, no text generation)
             choice (route) + score (complexity 1–10) + sufficiency boolean
                 ├─ direct_retrieval / source_management ─► single retrieval step
                 └─ deliberative_reasoning / live_web ─► System 2 reflexion graph:
                        Actor ─► Evaluator (score+verdict) ─► Self-Reflector ─► Episodic Memory
                        (loop gated ONLY by the evaluator; union of all reflections
                         conditions every retry; bounded by max_iterations)
```

Outage behavior: if the decision node is unavailable/invalid/timed-out, the keyword heuristic routes and responses are marked `provenance: "fallback"` (FR-003 of spec 002).

## MCP tools — 25 total (16 core below + 5 `ppt_*` spec 009 + 2 `antv_*` spec 012 + `hermes_file_task` spec 028 + `hermes_launch_app` spec 029)

| Tool | Purpose |
|---|---|
| `ask` | Agentic Q&A with citations; every response carries `decision` (route, complexity, sufficiency, provenance, latency) and `reflections` (per-trial evaluator scores/verdicts/critiques) |
| `search` | Direct vector search over LanceDB |
| `web_search` | Live web via SearXNG (fallback chain: searxng → tavily → exa) |
| `fetch_url` | Fetch a live page; returns `date_utc` (HTTP Date header = live UTC clock) |
| `web_research` | Grouped web research: multi-engine search via the provider chain + per-page outline-preserving scrape (text + belonging image in document order), bounded for the LLM, honest snippet fallbacks, inline rendered HTML artifact (spec 003) |
| `sources_add` / `sources_list` / `sources_remove` / `sources_sync` | Knowledge-base source management (local_folder, sqlite, onedrive) |
| `graph_query` | Optional Graphify layer (enable `[features] graphify = true`; build with the graphify skill) |
| `specialty_search` | Domain-scoped search: results only from a profile's configured authoritative sites (spec 005) |
| `specialty_profiles` | List available specialty profiles (name, sites, description) — agent calls this first |
| `sources_auth` | Complete Microsoft sign-in for OneDrive sources (device code flow) |
| `onedrive_list_files` | Browse OneDrive file metadata (names/paths/sizes only — nothing downloaded); optional name filter (spec 007) |
| `onedrive_embed_files` | Embed ONLY the named OneDrive files, one-time; per-file honest outcomes; the drive is never synced (spec 007) |
| `status` | Decision-node provenance, source health, index counters, and the active logging config (level, file, writability — spec 008) |

## OneDrive — on-demand embedding (spec 007)

OneDrive sources are **on-demand only**: your drive is never scanned, synced, or embedded wholesale. Connecting ingests zero files.

```
1. sources_add(type:"onedrive", {client_id, tenant_id})   → register (nothing ingested)
2. sources_auth(source_id)                                → device code; sign in at
                                                            login.microsoft.com/device
3. onedrive_list_files(source_id, search="…")             → metadata only, nothing downloaded
4. onedrive_embed_files(source_id, files=[…])             → embed EXACTLY the confirmed files
```

- The chat agent shows file matches and **asks you to confirm** before embedding — never more than you confirmed.
- Local folders and sqlite sources keep their automatic sync; OneDrive is excluded from the watcher entirely.
- **Staleness reminders**: when an answer cites a OneDrive file that changed in the cloud after embedding, the answer carries a reminder with both timestamps — the system never re-downloads on its own; you re-embed with one command.
- Azure app requirements: delegated `Files.Read`; single-tenant apps must pass their `tenant_id` at `sources_add`. Setup details: [DEPLOY.md](DEPLOY.md#onedrive-on-demand-setup).

## Reading the logs (spec 008)

The server writes a persistent, leveled log to `<state_db dir>/logs/server.log` (default `~/.config/agentic-rag-mcp/logs/server.log` — the mounted volume, so history survives container recreation):

- **INFO** — working-as-expected events (startup, watcher cycles, embeds, answers, health transitions); records carry counts, not user text
- **WARNING / ERROR** — every failure with its reason; nothing fails silently
- **DEBUG** — full developer trace (tool entries with arguments, routing decisions, retrieval counts, probe outcomes) — question text and file names appear **only** at DEBUG
- Credentials are redacted at every level; rotation caps disk at `rotation_size_mb × rotation_count` (default ~50 MB)

Console (stderr) mirrors the file at the same level, so `docker logs` keeps working. Set `LOG_LEVEL=DEBUG` in the container environment for a troubleshooting session; the active level is visible in the `status` tool's `logging` field.

## Install

```bash
pipx install -e .
agentic-rag-mcp --init   # writes ~/.config/agentic-rag-mcp/config.toml
```

## MCP host config (stdio)

```json
{ "mcpServers": { "agentic-rag": { "command": "agentic-rag-mcp" } } }
```

## Dify integration

A stateless-HTTP sidecar for Dify ships in [`dify/`](dify/): Dockerfile, compose fragments (Dify networks + HF-cache mount), and a ready-to-import chatflow DSL (`dify/Chatflow Basic (AgenticRAG Agent + PPT-Master).yml`, imported as the app **AGI Assistant**). Build and run:

```bash
docker build -f dify/docker/mcp-server/Dockerfile -t agentic-rag-mcp:latest .
docker run -d --name agentic-rag --network <dify_network> \
  -v ~/.config/agentic-rag-mcp:/root/.config/agentic-rag-mcp \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -p 28080:28080 --restart always agentic-rag-mcp:latest
```

Dify UI → Tools → MCP → URL `http://agentic-rag:28080/mcp` (container port aligned; the host also publishes **28080**, so host-side checks use `http://localhost:28080/healthz`). Edit MCP servers by delete + re-add (Dify 1.17's edit path has an identifier-vs-UUID bug).

## PPT-Master deck generation (specs 009–010)

Users can type "help to generate a powerpoint, introduce Dify software" in the chat and get a native editable `.pptx`. Five additive MCP tools (`ppt_project_init`, `ppt_icon_sync`, `ppt_write_page`, `ppt_check`, `ppt_export` — 16 → 21 tools; spec 012 adds two AntV tools → 23 total; spec 028 adds `hermes_file_task` → 24) bridge the [ppt-master](https://github.com/hugohe3/ppt-master) toolchain; the AGI Assistant chatflow (`dify/AGIAssistant/AGI_Assistant.yml`) routes deck requests to a PPT-Master agent node (rulebook: `dify/ppt-master-rulebook.md`), Windows file-task and program-launch prompts to the Hermes Local Agent node, and everything else to the AgenticRAG agent. Every export returns a completion page (`http://localhost:28080/decks/<project>/<stem>/`) with per-slide previews and a download control (`/exports/<project>/<file>.pptx`); the Chat UI renders deck links as an action bar (⬇ Download / 👁 Preview-Edit). Setup: mount the ppt-master clone at `/opt/ppt-master`, rebuild, refresh Dify's tool cache — full runbook in `DEPLOY.md` Step 9.

### Hermes File Agent lane (spec 028)

Windows file tasks typed in the chat ("create a folder Test in C:\temp and write hello.txt inside it") route through the same classifier to a **Hermes File Agent** node whose only tool is `hermes_file_task`. The gate (`src/agentic_rag_mcp/hermes_gate.py`) normalizes Windows/host paths, enforces containment inside the active root (default `C:\temp` via the `/mnt/c` drive mount), allows only create/write/read/list (no delete/rename/move in v1), asks back when no location is named, and writes every verdict to an append-only audit log (`~/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl`). Execution goes through the host Hermes gateway's `/v1/responses` (`172.17.0.1:8642`, bearer key) — the sidecar is the only caller. Blocked and out-of-scope prompts are refused with reasons and never reach Hermes. Full story: `specs/028-hermes-mcp-lane/`.

### Hermes program-launch lane (spec 029)

Program launches typed in the chat (*"launch Outlook"*, *"open Excel"*, *"run C:\tools\mytool.exe"*) route to the same **Hermes Local Agent** node, which carries a second tool `hermes_launch_app`. Its gate (`src/agentic_rag_mcp/hermes_launch_gate.py`) allows ONE executable — by bare application name or full `.exe` path (Windows/host styles normalized) — and refuses everything else with the rule named: launch arguments and command lines, shell/PowerShell phrasing, scripts (`.bat/.cmd/.ps1`), shortcuts (`.lnk`), non-executable paths, and two applications in one prompt (ask-back). There is **no allowlist** — any executable the prompt names may launch (trusted single-owner model, per the clarify session). Execution goes through the same Hermes gateway; the agent must end its report with `LAUNCH: SUCCESS` or `LAUNCH: FAILED: <reason>`, and the tool stamps `ok` only on an explicit SUCCESS — failures relay honestly with recovery hints, and every attempt is audited as `operation:"launch-app"` in the same append-only log. WSL interop must be enabled on the host (`/etc/wsl.conf` `[interop] enabled=true`) for launches to actually start Windows programs. Full story: `specs/029-hermes-launch-programs/`.

## AntV charts & infographics (spec 012)

Two additive MCP tools: `antv_chart(chart_type, data, title, …)` renders statistical charts (bar/line/pie/radar/sankey/…; geography types excluded) via the GPT-Vis service and returns an embeddable image URL; `antv_infographic(description)` stores declarative AntV Infographic syntax on the sidecar and serves it at `http://localhost:28080/infographics/<id>/` — the browser loads `@antv/infographic@0.2.20` from jsDelivr and renders client-side (~276 templates across 8 families: chart, sequence, sequence-interaction, list, hierarchy, relation, compare, quadrant). The chatflow agent picks templates from the DSL's `tool_description` — after editing the server docstring, sync the DSL and run `python -m agentic_rag_mcp.deploy chatflow` or the model keeps using stale template names. Agent rule (2026-10-27): generated visuals pick the tool by output type — `antv_chart` returns `image_url`, inlined as `![title](image_url)`; `antv_infographic` returns an interactive page, given as a labeled markdown link (not inlinable). Deck pages referencing remote chart images export self-contained. Data posture and private-rendering config: `DEPLOY.md` Step 11.

## Deployment automation (spec 011)

One command rebuilds, redeploys, updates the Dify chatflow, and runs a headless verification battery — no Dify UI actions, no prompts: `python -m agentic_rag_mcp.deploy all` (also `redeploy` / `chatflow` / `verify` / `cleanup`, each with `--dry-run`). Tool-cache re-sync is version-gated (Dify 1.17 workaround built in); credentials live in config/env, never in the repo. Runbook: `DEPLOY.md` Step 10.

## Chat UI (optional frontend)

[`ai-chat-landing/`](ai-chat-landing/) is a Chatbot-UI-style Next.js frontend wired to the Dify chatflow's Service API: questions stream the AgenticRAG agent's answers with full markdown (tables, images), a reasoning panel, source badges, and deck action bars. The sidebar shows backend chat history with recency grouping, resume-on-click, Load-more pagination, and per-row delete (specs 014–015); the header's ⬇ button exports the conversation as a PDF (spec 013); at viewports ≥1280px the column widens to min(90%, 1400px) with a 672px user-bubble readability ceiling (spec 016); the sidebar search filters conversations live, case-insensitively — titles plus loaded message content (spec 018); on phones the sidebar is an overlay drawer (spec 019); every fresh load opens on a fresh "New chat" draft (spec 020) whose empty state shows six feature cards in a three-column desktop grid — body-click sends the example prompt, the label links to the card's help page in a new tab (static pages in `ai-chat-landing/public/example1–6.html`, spec 021). One env var to go live — a Dify app API key in `ai-chat-landing/.env.local`. Run with `pnpm dev` (http://localhost:3000); without a key it falls back to demo replies. Details: [`ai-chat-landing/README.md`](ai-chat-landing/README.md).

## Configuration

```toml
[logging]                   # persistent leveled log file (spec 008)
level = "INFO"               # DEBUG|INFO|WARNING|ERROR; LOG_LEVEL env overrides;
                            # invalid values fall back to INFO with a WARNING record
# log_file = ""             # default: <state_db dir>/logs/server.log
rotation_size_mb = 10.0      # rotate at this size; keep rotation_count generations

[decider]                   # System 1 (see "System 1 decision node" details below)
enabled = true              # false => keyword heuristic routes (provenance: fallback)
model_repo = "convaiinnovations/laya"
model_dir = ""              # optional local checkpoint dir
timeout = 12.0              # exceeded => fallback (~7.4s warm on ARM CPU)
noul_threshold = 0.5

[web.searxng]
url = "http://searxng:28888"  # container-to-container (Docker DNS); host port is 28888 —
                             # see DEPLOY.md Step 5 for the JSON-API settings recipe

[web.specialty]               # specialty_profiles.json path (spec 005)
# file = ""                # empty = default ~/.config/agentic-rag-mcp/specialty_profiles.json

[web.research]               # web_research tool bounds (spec 003)
max_pages = 3                # pages scraped per call (cap 5)
per_page_chars = 6000        # content bound per page
fetch_timeout_s = 15.0       # per-page fetch timeout
overall_timeout_s = 30.0     # end-to-end bound for a research call
max_concurrent = 4           # parallel page fetches

[features]
graphify = false            # optional graph-search layer over graphify-out/graph.json

[antv]                      # spec 012 visualization tools
chart_service_url = "https://antv-studio.alipay.com/api/gpt-vis"  # GPT-Vis renderer
                             # (private: deploy GPT-Vis-SSR and point here)
chart_timeout_s = 30.0
max_inline_image_bytes = 2_097_152    # deck self-containment cap
infographic_max_syntax_bytes = 65_536
```

### System 1 decision node

Every `ask` request is routed by an embedded decision model (Laya, `convaiinnovations/laya`) in one pass — returning a route choice (`direct_retrieval` / `deliberative_reasoning` / `live_web` / `source_management`), a complexity score (1–10), and a knowledge-base-sufficiency boolean. No text is generated.

- First run downloads ~1.7 GB to the Hugging Face cache (~2 GB RAM loaded); the server pre-loads in the background at startup.
- Warm inference is hardware-dependent: ~140 ms on Apple Silicon, ~7.4 s on a small ARM cloud CPU — set `timeout` above your measured latency.
- Every response carries a `decision` object with `provenance` (`decision_node` | `fallback`) and `latency_ms`.
- Deliberative routes run the LangGraph reflexion graph (Actor → Evaluator → Self-Reflector → Episodic Memory); `reflections` in the response records each trial's score, verdict, and critique.

## Known pin

`faster-whisper==1.2.1` calls `av.open(..., metadata_errors="ignore")`, removed in PyAV 19. The vendored copy in `.venv` is patched; without the patch, unreadable audio files are skipped with a reason instead of crashing the batch (per FR edge-case). Upstream tracker: Pin PyAV<19 or upgrade faster-whisper when fixed.
