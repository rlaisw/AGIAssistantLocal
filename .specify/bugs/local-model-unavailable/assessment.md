# Assessment — local-model-unavailable (2026-11-05)

## Symptoms
- User selects Local (Qwen3 8B) in the Chat UI and sends a message → empty stream →
  "The local model could not answer this message and the selection was reset to
  DeepSeek. Please send again."
- The auto-reset's apply cycle also failed at the time (separate port-80 bug).
- `ollama list` on Windows: empty. WSL: no process listening on 11434.

## Investigation trail
1. `http://127.0.0.1:11434/api/tags` answered `{"models":[]}` — but `ss` showed no
   11434 listener in WSL: in mirrored networking that loopback hit the **Windows**
   Ollama app (running from `C:\Users\RLWB836\AppData\Local\Programs\Ollama`,
   server v0.40.14).
2. The Windows store (`C:\Users\RLWC145\.ollama\models` — `rlwb836` is a junction to
   `RLWC145`, a renamed account) had manifests but most blobs were gone; a fresh
   `ollama pull qwen3:8b` (5.2 GB) wrote fine, yet `list` stayed empty with
   `bad manifest ... "The system cannot find the path specified"` in server.log — the
   app's `db.sqlite` stored the models dir as the old `C:\Users\RLWB836\...` junction
   path, which its Go runtime cannot validate manifests through.
3. Fixed the Windows store (db.sqlite models path → real profile path, re-pulled
   qwen3:8b, recreated the nothink variant, pinned `OLLAMA_MODELS` in HKCU) — the
   Windows server then listed models. **But the UI's local send still streamed
   empty.**
4. The real topology: Dify's Ollama provider calls `http://172.17.0.1:11434`
   (docker bridge → **WSL host**). That endpoint is a **Linux Ollama server inside
   WSL** (v0.40.11, store `~/.ollama` with qwen3:8b *and* qwen3-8b-nothink from the
   original 2026-10-26 setup) — and it was simply **not running**: it had been
   started by hand back then and never survived the reboot.

## Root cause
The Windows Ollama app auto-starts from the user's Startup folder. In WSL mirrored
networking, **port numbers are shared between Windows and WSL**: after the reboot
the Windows app bound 127.0.0.1:11434 first, so the WSL server could not rebind
11434 on any address (`bind: address already in use` for both 0.0.0.0 and
172.17.0.1). With the WSL server dead, both the Dify local lane and the UI probe
lost their model backend. Secondary, independent defect: the Windows store's
configured models path pointed through the stale `rlwb836` junction and its blobs
had been wiped, so the Windows fallback server was also useless.
