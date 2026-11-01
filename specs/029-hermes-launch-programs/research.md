# Research: Hermes Program Launch Lane (Phase 0)

**Date**: 2026-11-01 · Stack facts verified from this repository's source (`hermes_client.py`, `hermes_gate.py`, `hermes_audit.py`, `config.py`, `deploy/battery.py`, `dify/AGIAssistant/AGI_Assistant.yml`) and spec 028's verified gateway research (R1 there remains the authority on the Hermes API surface).

## R1 — Execution pathway: reuse the file-lane client

- **Decision**: execute launches through the existing `hermes_client.run_task(cfg, task, instructions=...)` — same `POST /v1/responses`, bearer key, `store:false`, stateless — with a new `LAUNCH_INSTRUCTIONS` system prompt: launch exactly the stated target (name or full path), **no arguments, no command line, never a script or shortcut**; if the target cannot be found or fails to start, report that honestly; report exactly what was observed (started fresh / already running-activated / failed with reason).
- **Rationale**: the lane is deliberately LLM-in-the-loop exactly like the file lane — the host Hermes agent owns Windows access (the sidecar container cannot start Windows processes), and `run_task` already maps timeout / unreachable / key-rejected / non-200 / empty-output to honest error envelopes with recovery hints. The launch gate (R2) strips everything the prompt must never contribute (arguments, shell phrasing, script/shortcut targets), so the agent receives a clean, single-target instruction.
- **Alternatives considered**: a structured non-LLM launch endpoint on the gateway (does not exist in the verified API surface; adding one expands Hermes scope); the sidecar launching via WSL interop itself (impossible from the container, and it would move Windows access out of the single gateway trust path); passing the raw prompt through (rejected — prompt content is the attack surface the gate exists for).

## R2 — Launch gate rules (pure module `hermes_launch_gate.py`)

- **Decision**: a pure module, pipeline in order:
  1. **Classify** the launch verb (open/launch/start/run + program/app/exe phrasing) and strip fillers ("on my computer", "please", "the … program/app").
  2. **Extract the target**: a path token (reuse `hermes_gate`'s `_RE_PATH_TOKEN` + `normalize_path` — Windows/host style, mixed separators, case-insensitive drive letters) or a bare application name.
  3. **No target → ask-back** (FR-011): "which application should I launch?" — never guess.
  4. **Executables-only**: path targets MUST end in `.exe` (after normalization); bare names with no extension pass to the host resolver. Paths ending in `.bat/.cmd/.ps1/.lnk/.vbs/.js/.msi/...` are **blocked** with the executables-only rule named (FR-004).
  5. **No arguments, no shell**: any argument pattern (`--x`, `/x` flags, `key=value` tails, quoted argument strings, `;`/`|`/`&` command chaining) or shell phrasing (powershell, cmd, bash, "command line", "terminal") anywhere in the task → **blocked** with the no-arguments rule named (FR-005). Multi-instruction prompts ("open notepad and also run powershell") → the clean launch MAY run, the smuggled part is refused and reported.
  6. **One target per request**: two launch targets named → ask-back asking which one (spec Edge Cases); never launch both from one prompt.
  7. Output a `LaunchVerdict` — allowed (target, kind name|path, sanitized task) or blocked (reason).
- **Rationale**: mirrors the proven file-gate shape (normalize → check → verdict) so the test matrix carries over; the three owner decisions from the clarify session (name-or-path, executables-only, no-args) each map to one checkable rule; pure functions → full pytest coverage (Constitution II).
- **Alternatives considered**: asking the Hermes agent to self-police arguments (weaker — the gate must be the enforcement point, R2-of-028 precedent); an allowlist of extensions including `.lnk` (owner refused); regex-stripping arguments then launching (rejected — refuse, don't sanitize, keeps verdicts honest and testable).

## R3 — Tool wrapper, config, and audit

- **Decision**: new MCP tool `hermes_launch_app(task: str) -> dict` in `server.py`, mirroring `hermes_file_task`'s honest envelope: gate → **one audit entry at the verdict point** → (allowed only) `run_task` with `LAUNCH_INSTRUCTIONS` → envelope `{status: ok|blocked|error, decision?, result?, reason?, target?}`. Audit entries reuse `HermesAudit` unchanged: `operation="launch-app"`, `normalized_path=<target>` (name or canonical path), `allowed_root=""` (launches have no containment root), `decision` executed/blocked/error with reason or outcome. **No new config fields** — `hermes_api_url/key/timeout_s/audit_path` already exist; the launch tool needs no allowed-root.
- **Rationale**: `HermesAudit.write_attempt`'s signature already carries the launch case (generic `operation`/`normalized_path`/`allowed_root` fields — empty root is honest: no root applies); one writer keeps FR-006's single-trail guarantee; zero config surface (no allowlist per the clarify session).
- **Alternatives considered**: a separate audit file for launches (splits the single append-only trail for no benefit); a `target` audit field (would modify the writer — `normalized_path` already carries the target).

## R4 — Chatflow routing (FR-001) and node wiring

- **Decision**: extend the **existing** `intent_router` "Hermes file task" class into the local-machine class — its prompt gains launch phrasing ("…or wants a program/app launched, started, or run on their Windows computer, by name or full path") — and the **existing** `hermes_agent` node gains the second tool. Node instructions updated additively: file rules verbatim from 028 + launch rules (pick `hermes_launch_app` for launches; mixed prompts may call each tool for its part; relay verdicts verbatim; PowerShell/shell requests are still declined per the tool verdict; never claim direct desktop access). Answer merge already carries `hermes_agent.text` — no edge changes.
- **Rationale**: one local-machine agent with two gated tools matches how the user experiences the lane ("my computer's agent"); a 4th classifier class + new node would double the DSL surface for zero user value. Tool descriptions sync via the established `tool_description` → `deploy chatflow` pipeline; tool count 24 → 25, `DEPLOY.md`/AGENTS.md tool-count lines updated with the doc-sync task (028 T019 precedent).
- **Alternatives considered**: a separate launch classifier class + second node (rejected — more routing edges to test, same outcome); adding the launch tool to the Q&A agent's toolset (muddies the Q&A lane, 028 R7 precedent).

## R5 — Battery + the 028 decline-probe mapping (FR-010)

- **Decision**: 028's `scenario_hermes_file_task` **B5 probes stay as-is** — they call `hermes_file_task` *directly* with "open notepad" / "run a PowerShell command…" and must keep getting blocked (FR-009 defense in depth: the file tool stays file-only). The FR-010 flip lives in a **new** `scenario_hermes_launch_app`: "open notepad" through `hermes_launch_app` → `ok` + audit executed entry (optionally corroborated by a `tasklist.exe` process check from the host); "run a PowerShell command that lists processes" → `blocked`; argument and script-path probes → `blocked`; nonexistent path → `error` naming the path; audit cross-check for launch entries. The chatflow-level flip is asserted by the routing regression (launch prompt lands on the Hermes branch).
- **Rationale**: keeps 028's contract tests literally green (Constitution I) while the *user-facing* behavior flips exactly as FR-010 requires — the spec statement ("open notepad" → launch) is about the chat experience, which the new scenario + routing check cover; direct-to-file-tool smuggling still declines.
- **Alternatives considered**: rewriting B5 to expect launches (would break the file lane's contract tests and its defense-in-depth guarantee); deleting B5 (loses the smuggling regression).

## R6 — Test strategy (per plan input "create test cases and add error handling")

- **Unit, failing-first** — `tests/unit/test_hermes_launch_gate.py`: target extraction (names, quoted names, fillers), path targets (`.exe` ok after Windows/host normalization; `.bat/.cmd/.ps1/.lnk` blocked), argument matrix (`--flag`, `/flag`, `k=v`, quoted strings, `;`/`|` chaining → blocked), shell phrasing → blocked, multi-target → ask-back, no-target → ask-back, smuggled second instruction, reason strings naming the rules. `tests/unit/test_hermes_launch_tool.py` (client mocked at the trust boundary — respx is installed): blocked verdicts never call the client and write audit `blocked`; client failure → `error` envelope + audit `error`; success → `ok` + audit `executed`; envelope field shapes.
- **Contract**: existing suites stay green (tool schemas additive — the `ask`-field set and all 24 tool schemas byte-identical).
- **Live battery**: `scenario_hermes_launch_app` per R5; classifier routing regression; existing scenarios unchanged.
- **Error handling matrix** (each an explicit test or battery check): gateway down → `error` + "start it with 'hermes gateway restart -y --detach'" hint; key rejected → `error` naming the config mismatch; timeout → `error` suggesting a smaller task; unresolvable name → `error` naming the app; nonexistent/non-executable path → `error` naming the path; script/shortcut → `blocked`; arguments/shell → `blocked`; no/multiple targets → ask-back `blocked`; already-running → honest relay of what the agent observed.

## R7 — Name resolution honesty (FR-003/FR-007)

- **Decision**: the sidecar does **not** pre-verify that a named application exists — name resolution happens on the Windows host inside the Hermes agent's launch (Start-menu/PATH style). The tool's `ok` verdict therefore means "the agent launched and reported success"; unresolvable names come back as the agent's honest failure → `error` envelope naming the app, never a guessed substitute launch.
- **Rationale**: the sidecar container has no view of the Windows Start menu; duplicating resolution logic host-side would fork the truth (Constitution IV — one reporter: the agent that actually ran it).
- **Alternatives considered**: pre-flight `tasklist`/registry probes from the sidecar (no Windows visibility from the container; double-source-of-truth); refusing all bare names (contradicts the owner's no-allowlist decision).
