# Live tests — local-model-unavailable (2026-11-05, post-fix)

## Test 1 — availability probe (the UI's Local toggle)
`GET http://127.0.0.1:3000/api/models` →
`{"models":[{"id":"cloud","available":true},{"id":"local","available":true}]}`
**PASS** (was `local:false`)

## Test 2 — Dify container → Ollama reachability
`docker exec agentic-rag python -c "httpx.get('http://172.17.0.1:11434/api/tags')"`
→ status 200. **PASS** (before the fix the WSL server was down: empty stream)

## Test 3 — end-to-end local round-trip (the original failure case)
`POST http://127.0.0.1:3000/api/chat` `{"query":"Say OK.","aiModel":"local"}`
→ `task` → streamed `chunk`s ("OK. How can I assist you today?") → `done`.
**PASS** (before: ping → task → done, no chunks, UI showed the reset message)

## Test 4 — no thinking in the answer path
The streamed answer contains no reasoning block. Direct no-think sanity via the
request-level switch (what Dify sends through the plugin):
`POST 127.0.0.1:11434/api/chat` with `"think": false` → `"OK."`,
`done_reason:"stop"`. **PASS**

## Test 5 — direct no-think behavior notes (documentation)
- On the WSL server (0.40.11), qwen3 still emits thinking when called **without**
  `think:false` (system-prompt `/no_think` alone is not honored for this prompt).
  This is why the chatflow nodes' `completion_params: think: false` matter.
- The Windows server (0.40.14, if the app is ever run manually) behaves the same
  way; only `think:false` suppresses thinking.

## Re-verify after next reboot
Run `./reboot.sh` — step [4/6] must report `Ollama: up on :11434 (2 models)` and
the health table must show `Ollama :11434: ok`; then repeat Test 1 and Test 3.
