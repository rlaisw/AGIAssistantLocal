# Quickstart — Validate Image-Rich Chat Answers

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Test plan**: [test-plan.md](./test-plan.md)

A runnable validation sequence, cheapest and most deterministic first. Every command runs from the repository root unless stated.

## 0. Prerequisites

- Sidecar stack up (`docker ps`, sidecar `:28080`, Dify at `http://localhost`), Chat UI on `:3000`.
- `node` available (DSL JavaScript tests and CDP scripts use it).
- Owner console credentials in `~/.config/agentic-rag-mcp/config.toml` `[dify]`.
- Both app IDs at hand: `194e1edf-2eba-442c-b10b-231bebb79c37` and `7863fbe2-47f8-48c9-b096-6f7da8536b08`.

## 1. Deterministic checks (no model, no network)

```bash
.venv/bin/python -m pytest tests/unit/test_research_extraction.py \
    tests/unit/test_research_images.py tests/unit/test_research_image_payload.py \
    tests/unit/test_image_prompt_pins.py tests/unit/test_image_cap_dsl.py -q
.venv/bin/python -m pytest tests/contract/test_web_research_contract.py -q
```

Expected: all pass; the prompt-pin and cap tests must have been seen failing before the DSL edit (red first).

## 2. Full suite

```bash
.venv/bin/python -m pytest tests/unit tests/contract -q
```

Expected: green, same count as HEAD plus the new tests; no existing test weakened.

## 3. Deploy

```bash
.venv/bin/python -m agentic_rag_mcp.deploy redeploy      # sidecar carries hits[].images
.venv/bin/python -m agentic_rag_mcp.deploy chatflow      # prompt graph (defaults to app_name)
.venv/bin/python -m agentic_rag_mcp.deploy verify
```

Both apps are mirrors; publish/verify each by explicit ID if the CLI targets only one. Confirm the prompt landed per app:

```bash
docker exec docker-db_postgres-1 psql -U postgres -d dify -tAc \
 "select app_id, (graph::text like '%CAP: an answer MUST NOT inline more than 10 images%') \
  from workflows where app_id in ('194e1edf-2eba-442c-b10b-231bebb79c37','7863fbe2-47f8-48c9-b096-6f7da8536b08') \
  order by updated_at desc limit 4;"
```

Expected: `t` for both apps on their latest rows.

## 4. Payload spot-check (live sidecar)

The sidecar speaks MCP over streamable HTTP; call the tool through the MCP client
(the bare `/mcp` JSON-RPC POST does not complete the handshake):

```bash
.venv/bin/python - <<'EOF'
import asyncio, json
from datetime import timedelta
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

async def main():
    async with streamablehttp_client("http://localhost:28080/mcp",
                                     timeout=timedelta(seconds=120)) as (r, w, _):
        async with ClientSession(r, w, read_timeout_seconds=timedelta(seconds=120)) as s:
            await s.initialize()
            res = await s.call_tool("web_research",
                                    {"query": "how to pair a bluetooth mouse windows 11",
                                     "limit": 2})
            data = json.loads(res.content[0].text)
            for h in data["hits"]:
                print(h["url"], "images:", len(h["images"]),
                      (h["images"][:1] or [""])[0])

asyncio.run(main())
EOF
```

Expected: one `images: <n>` line per hit; a ref with `url`/`alt`/`heading`; a text-only page reports `images: 0`. Hit quality and count depend on the search engine (a transient 0-hit result is possible) — the contract tests in §1 are authoritative for the schema.

## 5. CDP acceptance (real UI)

```bash
node ai-chat-landing/scripts/image-rich-check.mjs            # all four scenarios
PROMPT="Show me the step-by-step instructions for pairing a standard Bluetooth mouse on Windows 11." \
  MIN_IMAGES=3 node ai-chat-landing/scripts/image-rich-check.mjs
```

Expected: how-to ≥ 3 visible images with alt; overview ≥ 2, not clustered; gallery 1–10; text-only 0. Report the counts in the run output.

## 6. Owner-facing live prompts (fresh conversation each)

| Case | Prompt | Follow-up if asked | Pass |
|---|---|---|---|
| How-to | Show me the step-by-step instructions for pairing a standard Bluetooth mouse on Windows 11. | It's a generic Bluetooth mouse on Windows 11 — show the steps with images from the source pages. | ≥ 3 visible, alt everywhere, images with steps |
| Overview | Show me examples of mechanical keyboards and what makes each one different. | Just the overview with example images from the sources. | ≥ 2, not clustered |
| Cap | Show me a big gallery of mechanical keyboard examples — as many as you can find, with images from the sources. | Just the gallery with images, no more questions. | 1–10 |
| Text-only | What is the capital of France? | — | 0 |

Run once per app (both lanes if the local lane is used).

## 7. Rollback

The pre-feature checkpoint is tag `checkpoint-pre-image-rich-2026-11-25` (DSL snapshot + startup.sh). Re-import `dify/AGIAssistant/AGI_Assistant.yml` from that tag with `deploy chatflow`, or revert the sidecar with `deploy redeploy` after `git checkout`.
