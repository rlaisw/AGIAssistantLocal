<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Project — AGI Chat (AgenticRAG Chat UI)

Chatbot-UI-style frontend for the Dify "AgenticRAG" chatflow. `app/api/chat/route.ts` proxies `POST /api/chat` → Dify `POST {DIFY_API_BASE_URL}/chat-messages` (streaming SSE re-emitted as line-delimited JSON: chunk · reasoning · replace · sources · ping · done). The API key lives in `.env.local` (git-ignored) and stays server-side.

- `app/page.tsx` — the whole chat app (client component): sidebar, streaming bubbles, 100 ms throttled state flushes, `parseAnswer` think-tag stripping, 120 s connection watchdog, theme switcher
- `components/markdown.tsx` — react-markdown (GFM + breaks) mapped to shadcn elements; images render inline; infographic links (`/infographics/` URL family) render with a 📌 and blue text (spec 046, `lib/infographic-link.ts`); deck links (`/exports/…pptx` or `/decks/…/` URL families, via `lib/deck-url.ts`) render as the action bar (`components/deck-actions.tsx` — ⬇ Download / 👁 Preview-Edit)
- `app/api/conversations/` — proxies Dify `/v1/conversations*`: history list, resume messages, and delete (backend-real, spec 014–015); `lib/history/` groups sidebar rows by recency; `lib/history/search.ts` + `search.test.ts` back the sidebar case-insensitive search (spec 018); `lib/pdf-export/` renders the header ⬇ conversation PDF (spec 013; remote images are rewritten through `app/api/image-proxy` so html2canvas's CORS-mode raster keeps them — failures degrade to labeled links); the composer's send button morphs into a Stop control while a turn generates — `lib/stop/state.ts` is the pure state machine, `app/api/chat/route.ts` emits one additive `task` event (task+conversation ids) and `app/api/chat/stop/route.ts` halts the Dify generation server-side (spec 027); `lib/follow-up.ts` splits the trailing "Want me to…?" paragraph so it renders as blue text with a 💡 (renderer-only, export unaffected); it also preserves a follow-up immediately before an infographic link, and both Agentic-Strategy prompts require a final follow-up offer after the link and sources
- Below md the sidebar renders as an overlay drawer (backdrop, Escape, selection closes it — spec 019); initial state is a fresh `c-0` "New chat" draft — the demo fixtures were removed (spec 020); the empty state renders six feature cards (3-col desktop grid) — body-click sends the example prompt, the label is a new-tab link to the card's help page in `public/example1–6.html` (spec 021); CDP checks live in `scripts/` (wide-layout.mjs, landing-check.mjs, welcome-cards.mjs, stop-button-check.mjs)
- `scripts/wide-layout.mjs` — CDP acceptance script for the wide chat layout: ≥1280px column `min(90%,1400px)`, 672px user-bubble ceiling; `--smoke` runs the behavioral checks (spec 016)
- No key / Dify down → canned demo replies (fallback mode)
- Validation: `pnpm typecheck && pnpm lint` — NEVER `pnpm build` while `pnpm dev` runs (shared `.next/`)
- Component conventions: follow the shadcn skill in `.agents/skills/shadcn/`

## MCP-Action (specs 047–048)

- **Scope and consent:** `mcp_action` has exactly three reviewed actions: `windows_default_printer`, `word_printer_duplex`, and `system_health_check` (empty parameters only). It is wired only into General-cloud and Hermes; General-local and all PPT-Master lanes remain unchanged, and unsupported procedures remain manual-only. Supported answers give tailored manual steps first, then the standalone final offer exactly `Do you want me to do it automatically for you?` Drafting performs no mutation, application control, display, or capture. Only the stored proposal's immediate next turn (`sys.dialogue_count` N at draft, N+1 at confirm/cancel) can resolve it: the tool classifies raw `sys.query` as plain yes/help-affirmative to confirm or plain no/cancel to cancel; a yes mistakenly sent as a draft returns a non-mutating confirm hint. Proposals expire after 15 minutes; modified, unrelated, stale, orphaned, or repeated responses never execute. There is no production chat-renderer change—the existing Markdown/follow-up renderer handles the offer and temporary image.
- **Execution and evidence:** One desktop-wide lock serializes confirmed execution through verification, display, and capture. The 240-second total budget includes queueing; an action starts only with its full 60-second default-printer or 90-second Word budget remaining, with queue, execution, display, and screenshot times reported separately. Fresh before/after read-back is authoritative for success. Settings `WaitFor` on `Printers & scanners` and Word Print Preview/foreground checks are separate display evidence, never proof of a setting change; if Word preview is visible but not foreground, one supported `App switch` is followed by a fresh COM display check, otherwise the result remains partial and capture is skipped. `screenshot.capture_scope` is `foreground-window` when the UIAutomationClient supplies valid bounds, otherwise `full-display`, with `region_fallback` disclosed on regional errors. The default-printer caveat discloses that choosing a manual default may turn off **Let Windows manage my default printer** and may not persist. Duplex is printer-wide (not limited to the current Word document) and may require existing permission; never auto-elevate or print a test page. Proposal, decision, execution, verification, display/screenshot, refusal, and error outcomes go to the append-only sanitized audit with stage outcomes and timings but no image URLs/tokens/paths or desktop text.
- **Dify binding invariant:** `mcp_action` runtime arguments `conversation_id`, `dialogue_count`, and raw `query` MUST use Dify auto-bound variable selectors (`auto: 0` plus nested `value: {type: variable, value: [sys, …]}`), never `{{#sys.query#}}` template constants. Dify serializes the tool list to JSON before template substitution; newlines/quotes in the raw query make that JSON invalid and collapse the list to a string (`'str' object has no attribute 'get'`). Regression: `tests/integration/test_mcp_action_dify_contract.py::test_raw_query_with_newline_reaches_agent_without_tool_json_crash`.
- **System health check (spec 048):** `system_health_check` runs a pinned read-only host script, returns the complete HTML report verbatim in the answer, writes it to `%LOCALAPPDATA%\Temp\selfcheck.html` as the visible report reference, publishes a temporary internal 15-minute copy at `GET /mcp-action/reports/{token}` (43-character token, no-store, CSP sandbox), displays Reliability Monitor once, and keeps HelpDesk advisory only — never an automatic ticket, repair, or settings change. Its 180-second budget includes execution, report publication, display, and capture.
- **Temporary screenshots:** `GET /mcp-action/screenshots/{token}` serves one PNG/JPEG with an absolute 900-second TTL, a 30-second janitor, and `Cache-Control: no-store`; the chat image proxy preserves upstream `no-store` while retaining its ordinary-image caching. This is an unauthenticated capability URL accepted only for the current single-user local-trust deployment: anyone possessing it can retrieve the image until expiry. Redact tokens from logs; tool results contain no Base64 or local path, and screenshots, tokens, URLs, paths, image bytes, and desktop text must not become long-term audit artifacts.
- **Source and tests:** `src/agentic_rag_mcp/mcp_action/`; `tests/unit/test_mcp_action_*.py`; screenshot/report/MCP contracts in `tests/contract/test_mcp_action_screenshot_route.py`, `tests/contract/test_mcp_action_report_route.py`, and `tests/contract/test_mcp_contract.py`; `tests/integration/test_mcp_action_{dify_contract,e2e}.py`; CDP acceptance in `ai-chat-landing/scripts/mcp-action-check.mjs`.

Deterministic validation (repository root, then `ai-chat-landing/` for the frontend):

```bash
.venv/bin/python -m pytest tests/unit/test_mcp_action_*.py tests/contract/test_mcp_action_screenshot_route.py tests/contract/test_mcp_action_report_route.py tests/contract/test_mcp_contract.py -q
.venv/bin/python -m pytest tests/unit tests/contract -q
cd ai-chat-landing
pnpm test && pnpm typecheck && pnpm lint
```

Deploy safely with `.venv/bin/python -m agentic_rag_mcp.deploy redeploy`, publish both apps by explicit ID, then run `.venv/bin/python -m agentic_rag_mcp.deploy verify`; do not use name-based `deploy all` for the two identically named apps. Opt-in live checks run from the repository root:

```bash
RUN_MCP_ACTION_DIFY_CONTRACT=1 .venv/bin/python -m pytest tests/integration/test_mcp_action_dify_contract.py -q -s
RUN_MCP_ACTION_E2E=1 .venv/bin/python -m pytest tests/integration/test_mcp_action_e2e.py -q -s
RUN_MCP_ACTION_E2E=1 node ai-chat-landing/scripts/mcp-action-check.mjs
```

Mutating CDP runs additionally require `MCP_ACTION_ALLOW_PRINTER_CHANGE=1` or `MCP_ACTION_ALLOW_WORD_DUPLEX=1` and explicit test-printer variables. Live tests are owner-present only, use owner-approved test printers and a disposable unsaved Word document, restore original default/duplex state in `finally` even after failures, and never print test pages.
