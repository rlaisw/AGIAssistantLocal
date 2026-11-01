## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.

## ai-chat-landing (Chat UI)

Next.js 16 + shadcn/ui (Base UI, luma preset) chat frontend for the Dify AgenticRAG chatflow, in `ai-chat-landing/`. Questions stream through `app/api/chat/route.ts`; the Dify API key lives in `.env.local` (git-ignored — never commit it).

Rules:
- Validate with `pnpm typecheck && pnpm lint` inside `ai-chat-landing/` — NEVER run `pnpm build` while `pnpm dev` is running in the same directory (they share `.next/`; a build mid-request silently kills in-flight streams).
- `pnpm test` in `ai-chat-landing/` runs vitest (pure-logic unit tests, e.g. `lib/deck-url.ts`, `lib/history/`, `lib/pdf-export/`).
- Chat UI feature surface: `app/api/conversations/` proxies Dify `/v1/conversations*` (history groups, resume, delete — specs 014/015); `lib/pdf-export/` backs the header ⬇ PDF export (spec 013; remote answer images are proxied same-origin via `ai-chat-landing/app/api/image-proxy/route.ts` so they survive the html2canvas CORS raster); `scripts/wide-layout.mjs` is the CDP layout acceptance script (wide column ≥1280px, `--smoke` for behavioral checks — spec 016); `lib/history/search.ts` + `search.test.ts` power the sidebar case-insensitive search (spec 018); below md the sidebar is an overlay drawer with backdrop/Escape/selection close paths (spec 019); every fresh load initializes a fresh "New chat" draft — no demo fixtures (spec 020); the empty state shows six feature cards in a 3-col desktop grid — body-click sends, label links new-tab to the card's help page in `public/example1–6.html` (spec 021); while an answer generates, the send button morphs into a Stop control that halts the backend generation via `app/api/chat/stop` and finalizes the turn honestly (partial text kept, session-only "Stopped" caption — spec 027); finished answers render their trailing follow-up question (the "Want me to…?" paragraph) as blue text with a 💡 (`lib/follow-up.ts`, 2026-10-28); the "Hermes File Agent" chatflow lane routes Windows file-task prompts to the sidecar's `hermes_file_task` MCP tool, which gates create/write/read/list operations inside an allowed root (default `C:\temp` via `/mnt/c/temp`), executes via the host Hermes gateway (`172.17.0.1:8642`, bearer key), and writes an append-only audit log (`~/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl`) — blocked/delete/out-of-root prompts are refused with reasons and never reach Hermes (spec 028); the "Hermes Local Agent" lane also routes program-launch prompts — any executable by name or full `.exe` path, never with arguments, never scripts/shortcuts, one target per request, ask-backs for no/ambiguous target — to the sidecar's `hermes_launch_app` MCP tool, which gates purely, executes via the same gateway, and audits every attempt as `operation=launch-app`; `ok` requires the agent's `LAUNCH: SUCCESS` attestation, and WSL interop must be enabled on the host for launches to actually start (spec 029); CDP acceptance instruments live in `scripts/` (wide-layout.mjs, landing-check.mjs, welcome-cards.mjs, stop-button-check.mjs).
- The shadcn skill in `ai-chat-landing/.agents/skills/shadcn/` is CLI-managed (`pnpm dlx skills add shadcn/ui`); `skills-lock.json` tracks versions — do not hand-edit it.
- Full docs: `ai-chat-landing/README.md`; deployment: `DEPLOY.md` Step 8; topology: `docs/NETWORK.md` ⑦⑧.

## Deployment automation (spec 011)

`python -m agentic_rag_mcp.deploy {redeploy|chatflow|verify|cleanup|all}` (run with the project venv's python) rebuilds the sidecar, updates + publishes the Dify chatflow in place, and runs the headless verification battery. Console credentials and the chatflow API key live in `~/.config/agentic-rag-mcp/config.toml` `[dify]` (or `DIFY_*` env vars) — NEVER commit them; the CLI redacts secrets in all output. After changing tool counts or the chatflow DSL, `all` is the one-command path. Runbook: `DEPLOY.md` Step 10.
