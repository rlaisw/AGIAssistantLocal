# Fix — local-model-unavailable (2026-11-05)

## What was done
1. **Disabled the Windows Ollama app autostart**: renamed
   `…\Startup\Ollama.lnk` → `Ollama.lnk.disabled` and killed its processes.
   Rationale: the stack's local lane uses the *WSL* Ollama server (Dify provider →
   `http://172.17.0.1:11434`); in mirrored networking the Windows app's loopback
   bind steals port 11434 from it at every boot. The app can still be started
   manually, but must not autostart while the WSL server owns 11434.
2. **Made the WSL server a systemd user service** (auto-restart, starts on
   `systemctl --user start ollama`; `reboot.sh` step [4/6] now starts it after every
   reboot):
   `~/.config/systemd/user/ollama.service` with `OLLAMA_HOST=0.0.0.0:11434`.
   The WSL store already contained qwen3:8b and qwen3-8b-nothink from the original
   setup — no model work was needed there.
3. **Repaired the Windows Ollama store** (secondary, so the app is healthy if ever
   used manually):
   - `db.sqlite` `settings.models` corrected from the stale
     `C:\Users\RLWB836\.ollama\models` (renamed-account junction path) to the real
     `C:\Users\RLWC145\.ollama\models`
   - re-pulled `qwen3:8b` (5.2 GB) and recreated `qwen3-8b-nothink` from
     `dify/AGIAssistant/ollama/qwen3-8b-nothink.Modelfile`
   - pinned `OLLAMA_MODELS=C:\Users\RLWC145\.ollama\models` in the user's
     HKCU `Environment` so the old path cannot resurface
4. No Dify/chatflow changes were needed: the local nodes already carry
   `completion_params: think: false`, and the langgenius/ollama plugin forwards it
   to the Ollama API (`llm.py` pops `think` into the request). Note for the future:
   on Ollama ≥0.40.14 only the request-level `think:false` reliably suppresses
   qwen3 thinking — the Modelfile `/no_think` system prompt alone does not. The WSL
   server is 0.40.11; the design works either way because Dify sends the parameter.

## Verification
- `systemctl --user is-active ollama` → active; `ss` → `*:11434` (WSL listener)
- `ollama list` (WSL) → qwen3:8b + qwen3-8b-nothink
- Chat UI probe `GET /api/models` → `{"id":"local","available":true}`
- `docker exec agentic-rag … httpx.get('http://172.17.0.1:11434/api/tags')` → 200
  (Dify's container path to the server)
- **End-to-end**: `POST /api/chat {"query":"Say OK.","aiModel":"local"}` through the
  Chat UI proxy streamed real chunks — "OK. How can I assist you today?" — with no
  thinking block (Dify's think:false honored)

## Permanence
- `reboot.sh` [4/6] starts the service and health-checks `:11434`; the health
  table also gained an Ollama line. Linger is not enabled (needs sudo), so the
  user service starts with the first user session — `reboot.sh` guarantees it.
- If Local is ever greyed out again: check `journalctl --user -u ollama` first, and
  make sure no Windows Ollama app instance is running (port thief).
