# Quickstart: Hermes Program Launch Lane (spec 029)

Validation guide — proves the lane end-to-end. Implementation details live in `tasks.md`; contract invariants in [contracts/hermes-launch-app.md](contracts/hermes-launch-app.md); entities in [data-model.md](data-model.md).

## Prerequisites

- Hermes gateway running on the host (`hermes gateway restart -y --detach`), `hermes.api_key` matching `API_SERVER_KEY` in `~/.hermes/.env`, reachable at `172.17.0.1:8642` from the sidecar container.
  - **Verified 2026-11-01 (T001)**: gateway was down, restarted via the documented command, `/v1/models` → HTTP 200 with `hermes-agent` advertised; sidecar `:28080` responds; `/mnt/c/temp` present.
- Sidecar `agentic-rag` up (:28080) with this feature's code hot-patched in (or rebuilt image); `deploy chatflow` published with the updated classifier prompt + Hermes node tool list.
- Windows `C:` mounted at `/mnt/c` (existing 028 assumption).
- **WSL interop enabled** (spec 029 prerequisite, discovered live): `/etc/wsl.conf` `[interop] enabled=true` and a healthy WSL–Windows vsock channel — without it the local agent cannot start Windows programs and every launch answers with an honest error + the `wsl --shutdown` recovery hint. Enable from Windows PowerShell: `wsl -u root sed -i 's/^enabled=false$/enabled=true/' /etc/wsl.conf` then `wsl --shutdown`, reopen WSL, restart the Hermes gateway (`hermes gateway restart -y --detach`) and verify the stack (docker containers up, sidecar :28080, Dify answering).

## 1. Unit suites (deterministic, no network)

```bash
.venv/bin/python -m pytest tests/unit/test_hermes_launch_gate.py tests/unit/test_hermes_launch_tool.py -q
```

Expected: all green — the gate matrix (targets, `.exe`-only, no-args, shell phrasing, one-target, ask-backs, reasons) and the tool wrapper (blocked/error/ok envelopes + audit entries, client mocked).

## 2. Existing suites stay green (Constitution I)

```bash
.venv/bin/python -m pytest tests/unit tests/integration tests/contract -q
```

Expected: 100% — the 24 existing tool schemas and the file-lane gate/audit suites unchanged.

## 3. Live battery (deployed stack)

```bash
.venv/bin/python -m agentic_rag_mcp.deploy verify
```

Expected: existing scenarios unchanged **plus** the new launch scenario green:

| # | Probe (through `hermes_launch_app` / chat) | Expected |
|---|---------------------------------------------|----------|
| L1 | "open notepad" | `ok` within the Hermes call timeout (300 s — SC-001 amended, measured); Notepad running on the Windows desktop; audit `executed` (optionally corroborated via `tasklist.exe`) |
| L2 | "run C:\Windows\System32\notepad.exe" (full `.exe` path) | `ok`; that exact program; audit `executed` |
| L3 | "run a PowerShell command that lists processes" | `blocked`, no-arguments/shell rule named; audit `blocked` |
| L4 | "launch outlook --dangerous-flag" | `blocked`, no-arguments rule; no process with the flag |
| L5 | "run C:\temp\setup.bat" | `blocked`, executables-only rule (file may exist — still refused) |
| L6 | "launch C:\nope\missing.exe" | `error` naming the path; nothing started; audit `error` |
| L7 | "open it" (no target) | `blocked` ask-back asking which application |
| L8 | "open notepad and calculator" | `blocked` ask-back — one target per request |
| L9 | audit cross-check | exactly one `operation:"launch-app"` entry per L1–L8 attempt, decisions in order, none fabricated |

028 regression (FR-010 mapping): B5's direct `hermes_file_task` probes ("open notepad", PowerShell) **still `blocked`**; classifier routing check: a chat "open notepad" lands on the Hermes branch and launches.

## 4. Manual chat check (end-user view)

Type in the chat UI: *"can you open Excel?"* → Excel starts in the same turn, the answer confirms the launch. Then: *"launch chrome with incognito"* → the answer refuses verbatim (no-arguments rule). Both attempts appear in the audit log with truthful decisions.

## 5. Error handling checks (each already covered by a unit or battery case)

- Gateway stopped → `error` + "start it with 'hermes gateway restart -y --detach'" hint (retry after starting).
- Key mismatch → `error` naming the config pair to fix.
- Timeout (300 s) → `error` suggesting a smaller task.
- Unresolvable name → `error` naming the app, never a substitute launch.
- Already-running app → the answer relays what the agent actually observed (activated / second instance) — never a fabricated "started fresh".

## 6. Cleanup

The lane launches real programs — close whatever L1/L2 started (Notepad, etc.). The battery cleans its own audit expectations; the audit log itself is never pruned (FR-006).

## Recorded outcomes (implementation, 2026-11-01)

Verified live (interop-independent):
- Unit suites: 28 launch tests (gate matrix + tool wrapper) + 23 file-lane regression tests + tool-sync payload gate (1.18 widened after live schema verification) — all green.
- Gate probes through the running sidecar: L3 PowerShell / L4 arguments / L5 script path / L7 no-target / L8 two-target — all `blocked` with the correct reasons; audit entries truthful.
- Gateway-down probe: `error` envelope + `hermes gateway restart -y --detach` recovery hint; audit `error`. Gateway restored after.
- B5 defense-in-depth: direct `hermes_file_task` decline probes still `blocked` (FR-010 mapping holds).
- Chat-level routing: "launch Excel on my Windows computer" → classifier "Hermes local task" → Hermes Local Agent → `hermes_launch_app` → honest interop error relayed verbatim with the recovery hint.
- Deploy findings fixed live: (1) TWO "AGI Assistant" Dify apps existed — `deploy chatflow` published to the orphan duplicate while the chat key belonged to the live app; published to the live app (and both now carry the DSL). (2) Dify 1.18 was version-gated out of the tool-cache db-resync; the schema was verified live and the gate widened (`tool_sync.SUPPORTED_DB_RESYNC`), cache synced 24 → 25 tools.
- Honest-envelope fix found live: the first probe stamped `ok/executed` for a launch the agent could not perform (interop disabled) — fixed with the required `LAUNCH: SUCCESS` / `LAUNCH: FAILED: <reason>` attestation; a failure report or missing marker is now `error`. Measured verdict latency: 71 s cold, 230 s warm (agent-turn dominated) — SC-001 amended to the Hermes-timeout bound (300 s).

- Full sweep (2026-11-01): pytest unit+integration+contract = 405→409 green after amending three stale snapshot tests the new 25th tool surfaced (antv/ppt `EXISTING_TOOLS` sets missing the 028 file tool entirely — red since 028; `CONTRACT_SCENARIOS` missing the 027/028 scenarios); frontend `pnpm typecheck && lint && test` green (136/136, one pre-existing lint warning in `scripts/stop-button-check.mjs`). One remaining failure — `test_web_research_limit_capped_at_max_pages` — reproduces identically in the OLD workspace (SearXNG result-shape drift, pre-existing, out of 029 scope).

Pending WSL interop — **RESOLVED 2026-11-01 10:19** (owner flipped `[interop] enabled=true` and restarted WSL; Docker auto-started; gateway restarted). Post-interop live verification:
- L1 "open notepad" → `ok` in 41.3 s — agent honestly relayed "already running (PID 17124), activated" — notepad.exe corroborated via tasklist.
- L2 full-path launch (`C:\Windows\System32\notepad.exe`) → `ok` in 9.6 s, same honest already-running relay.
- L6 `launch C:\nope\missing.exe` → `error` in 3.3 s naming the absent path — nothing started.
- Unresolvable name ("definitelynotarealapplicationxyz") → `error` in 3.0 s naming the app and everywhere it looked.
- Chat "can you open Excel?" → routed to the Hermes Local Agent → `hermes_launch_app` → **Excel started fresh ("Book1 - Excel")**, corroborated: EXCEL.EXE in tasklist. Chat total 24.6 s.
- Already-running relay: exercised by L1/L2 (activated, never claimed "started fresh").
- Full battery: final run 12/13 with the launch scenario green on immediate re-run — the only failure was L2 hitting an honest 300 s Hermes timeout (agent-turn variance; 10.5–38 s in passing runs), and chat-journey flaked once mid-day then passed twice. Every scenario green: health, tools-surface (25), deck-roundtrip, completion-page, honest-errors, chat-ui-liveness (dev server up), stop-generation, hermes-file-task (B1–B5 incl. defense-in-depth declines), hermes-launch-app (L1–L9 all ok), antv-chart, antv-infographic, chart-in-deck, chat-journey.

Final launch-scenario matrix (recorded 2026-11-01):
`L1 name-launch ok (ok, 18.0s); L2 full-path launch ok (ok, 38.1s); L3 powershell refused ok; L4 arguments refused ok; L5 script path refused ok; L6 missing-path honest error ok (error, 15.6s); L7 no-target ask-back ok; L8 two-target ask-back ok; L9 audit cross-check ok (got == expected: executed, executed, blocked, blocked, blocked, error, blocked, blocked)`

Two live fixes found while hardening the L9 check:
1. The long-running sidecar serving process (started before the second hot-patch) stopped writing blocked-verdict audit entries — a container restart restored correct behavior; fresh in-container processes were always correct.
2. The battery's L9 audit filter matched `operation == "launch-app"`, which excludes blocked entries (they carry `ask-back`/`unsupported` per the file-lane convention) — fixed to filter by `allowed_root == ""`, the launch lane's actual discriminator.
