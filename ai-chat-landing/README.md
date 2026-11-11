# AGI Chat — AgenticRAG Chat UI

A Chatbot-UI-style chat frontend for the **AgenticRAG** Dify chatflow, built with Next.js 16, Tailwind CSS v4, and shadcn/ui on Base UI primitives (luma preset).

Questions typed here go to the Dify chatflow's Service API, and the AgenticRAG agent's answer streams back — markdown (headings, tables, images), a reasoning panel, and source badges rendered inline. The header's ⬇ button exports the whole conversation as a PDF (client-side render; `lib/pdf-export/`, spec 013 — remote images go through the same-origin `app/api/image-proxy` so they survive the CORS-mode rasterizer). The sidebar shows backend chat history grouped by recency — Today / Yesterday / Previous 7 days / Last month / Few months ago — with resume-on-click, Load more pagination, and first-message draft promotion (`lib/history/`, `app/api/conversations/`, spec 014; each row offers a "…" menu → Delete with inline confirmation — backend-real, survives reload (spec 015). At viewports ≥1280px the chat column and composer widen to `min(90%, 1400px)` of the content area — centered and capped for readability, with long user-message bubbles capped at 672px; below 1280px the layout is unchanged (spec 016). The sidebar's Search chats box filters the list live, case-insensitively — titles of every conversation plus the message text of opened ones — with × / Escape to clear and an explicit no-match state (`lib/history/search.ts`, spec 018). On phones the sidebar becomes an overlay drawer — open it from the panel toggle; a backdrop tap, Escape, or picking a conversation closes it (spec 019). Every fresh load opens on a fresh "New chat" draft — the "How can I help you today?" empty state with feature cards; the old demo fixtures are gone (spec 020). The empty state shows six feature cards (PowerPoint, Infographic, Chart Diagram, CorpIT Helpdesk, AI Chatbot, Agentic RAG DB) in a three-column desktop grid — clicking a card body sends its example prompt; each card's label links to its help page in a new tab (served from `public/example1.html` … `example6.html`, each with a green 16 px prompt-provenance strip — spec 021, pages landed 2026-10-30). While an answer generates, the send button morphs into a Stop control — clicking it halts the backend generation (`app/api/chat/stop`, additive `task` stream event), keeps the partial text and reasoning, shows a session-only "Stopped" caption, and returns the composer to ready in well under a second; switching conversations mid-generation never disturbs the turn (spec 027). Finished answers render their trailing follow-up question (the "Want me to…?" paragraph) as blue text with a 💡 — a display-only renderer change (`lib/follow-up.ts`), so PDF export keeps the raw text.

## Quickstart

```bash
pnpm install
pnpm dev          # http://localhost:3000
```

Press `d` (or the sun/moon icon) to toggle Dark / Light / System.

## Dify configuration

Create an app API key — Dify UI → AgenticRAG app → **API Access** → Create Secret Key (format `app-…`) — and put it in `.env.local`:

```bash
DIFY_API_BASE_URL=http://localhost/v1
DIFY_API_KEY=app-xxxxxxxxxxxxxxxx
```

`next dev` watches `.env.local` and reloads it automatically; `next start` reads it at boot. Without a key (or with Dify down) the UI silently falls back to canned demo replies.

## How it works

```
Browser ── POST /api/chat ──► Next.js route (app/api/chat/route.ts)
                               │  Bearer DIFY_API_KEY — key stays server-side
                               ▼
                     Dify POST /v1/chat-messages (response_mode: streaming)
                               │  SSE: message · reasoning_chunk · message_end · ping
                               ▼
                     proxy re-emits line-delimited JSON:
                     chunk · reasoning · replace · sources · ping · done
                               ▼
Browser appends chunks to the streaming bubble (throttled to 100 ms),
stores Dify's conversation_id per chat for multi-turn context.
```

- `message_end` retriever resources → source badges; `reasoning_chunk` and ` Mohammad...` blocks → the reasoning panel
- Dify keep-alive pings are forwarded; a 120 s silent-connection watchdog aborts and shows a note instead of hanging forever
- Conversation history sidebar, static "AGI Chat" badge (the chatflow's model is fixed server-side), theme dropdown; per-chat Dify `conversation_id` keeps agent memory across turns
- Deck links in answers render as an action bar (⬇ Download / 👁 Preview-Edit) opening the sidecar's completion page (`/decks/<project>/<stem>/`) with per-slide previews — URL recognition and derivation live in `lib/deck-url.ts`

## Stack

Next.js 16 (App Router, Turbopack) · React 19 · Tailwind CSS v4 · shadcn/ui (Base UI, luma preset) · react-markdown (GFM tables + images) · lucide-react icons

shadcn components installed: button, badge, card, accordion, avatar, table, separator, input, textarea, dropdown-menu. The shadcn agent skill lives in `.agents/skills/shadcn/`.

## Testing

`pnpm test` runs vitest (pure logic — deck-URL recognition/derivation, history grouping and delete state, sidebar search, the PDF-export pipeline incl. the image-proxy rewrite, the stop state machine, the chat route's `message_end`→`done` stream finalization and upstream-reader cancellation (`app/api/chat/route.test.ts`), and the follow-up prompt splitter; 143 tests). Browser-facing behavior is covered by the deploy battery's `chat-ui-liveness` and `chat-journey` scenarios (`python -m agentic_rag_mcp.deploy verify` from the repo root). Layout acceptance is measured live by the CDP scripts: `node scripts/wide-layout.mjs` (layout + `--smoke` behavioral — spec 016), `node scripts/landing-check.mjs` (New-chat landing — spec 020), and `node scripts/welcome-cards.mjs` (welcome feature cards — spec 021); all need Chrome on `--remote-debugging-port=9240`.

## Notes

- `pnpm build` while `pnpm dev` is running clobbers the shared `.next/` directory and can kill in-flight streams — validate with `pnpm typecheck && pnpm lint` instead, or build in a separate checkout
- `next dev` prints "Port 3000 is in use / Another next dev server is already running" when a stale server holds the port — `kill <pid>` from the message and restart
- Remote access (phone/LAN): `next.config.ts` lists `allowedDevOrigins` (the host LAN IP) — without it, Next dev blocks cross-origin requests and the page renders but nothing is interactive; add any new access origin there and restart dev
- Restart `pnpm dev` after any dependency change (`pnpm add`/upgrade) — the running server loads `node_modules` at start and dies or misbehaves when the tree is swapped underneath it
