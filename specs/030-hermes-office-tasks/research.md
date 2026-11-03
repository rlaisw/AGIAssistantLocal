# Research: Hermes Office Task Lane (Phase 0)

**Date**: 2026-11-02 · Every R1 fact below is **live-probed on this host** (mirrored-networking check, OfficeMCP source read from `C:\Users\RLWC145\AppData\Roaming\uv\tools\officemcp\...` via `/mnt/c`, Hermes gateway `--help` surfaces) — the 028 house rule: verified, not assumed.

## R1 — The three deferred probes, resolved live

- **Networking mode: `mirrored`** (`wslinfo --networking-mode`). Consequence: an OfficeMCP SSE server bound to Windows `127.0.0.1:8888` is reachable from WSL-side processes (the Hermes gateway) at the same address. Docker containers cannot use mirrored loopback (separate netns) — noted for R2.
- **OfficeMCP service is not currently running** (port 8888 unreachable, no `officemcp` process on Windows). It is a user-managed Windows-side service, started with the owner's own command: `officemcp sse --port 8888 --host 127.0.0.1 --folder C:\OfficeMCP`. The lane treats it like the Hermes gateway: a prerequisite with an honest down-error carrying the exact start command (T001-class task; the recovery hint mirrors 028/029's gateway hint).
- **The Hermes gateway has native MCP-client support**: `hermes mcp {add,remove,list,test,configure,...}`; `hermes mcp add <name> --url <endpoint>` accepts HTTP/SSE URLs, `hermes mcp test` verifies the connection, and the agent runtime dispatches MCP tools (source-verified: `agent/tool_dispatch_helpers.py`, `agent/agent_runtime_helpers.py`). The owner's stated architecture ("Hermes agent → Office MCP") is natively supported by the installed gateway.
- **OfficeMCP v1.0.5's actual tool surface** (read from source — 266-line `OfficeMCP.py`, 503-line `Officer.py`): `AvailableApps`, `RunningApps`, `IsAppAvailable`, `RootFolder`, `IsFileExists`, `Visible`, `Launch`, `ScreenShot`, `RunPython(code, data)`, `Quit`, `Speak`, `Beep`, `Demonstrate`. **There are no typed cell/email tools** — the workhorse is `RunPython`, which `exec`s agent-written Python on the Windows host with `Officer` in the namespace; `Officer.Excel/Word/PowerPoint/Outlook` return **raw COM Application objects** (the docstring's own example writes `sheet.Cells(1,1).Value`). File-scoped defaults via `RootFolder`/`IsFileExists` (the `--folder C:\OfficeMCP` root).

## R2 — Bridge decision: the gateway's native MCP client

- **Decision**: wire OfficeMCP to the Hermes gateway once, on the host: `hermes mcp add OfficeMCP --url http://127.0.0.1:8888/sse` (exact endpoint path confirmed at connect with `hermes mcp test OfficeMCP`). The agent then calls OfficeMCP tools natively during its turns; the sidecar **never** talks to OfficeMCP.
- **Rationale**: (a) probe-verified native support — zero bridge code; (b) mirrored loopback is reachable from the WSL-host-side gateway but **not** from the docker sidecar (separate network namespace), so a sidecar proxy would require re-binding the service beyond loopback — a worse security posture; (c) it keeps the 028/029 shape: the sidecar is the gated, audited broker; the agent is the executor.
- **Alternatives considered**: sidecar proxy to OfficeMCP SSE (blocked by the loopback/netns mismatch; would force `--host 0.0.0.0` — rejected); registering OfficeMCP as a second Dify MCP provider (simplest wiring but bypasses the sidecar gate and audit entirely — violates the architecture every Hermes lane is built on; rejected).

## R3 — The trust model, stated honestly (RunPython reality)

- **Finding**: the executor mechanism is a host-side Python REPL over COM. Any caller of OfficeMCP can execute arbitrary code on Windows — not just Office operations. There is no typed surface to structurally restrict to "write cell A1".
- **Decision**: accept it inside the existing trusted-owner boundary — the Hermes agent already executes host commands for file tasks (028) and launches (029); OfficeMCP extends the same boundary to Office via COM. The lane's defenses are layered and honest about what each layer does:
  1. **Gate (sidecar, structural)**: governs *tasks* — work-folder containment for prompt-named paths, prompt-borne code-execution bans (macro/DDE/external-link formula requests blocked), recipient rules, confirm-before-send resolution. Unchanged in spirit from 028/029: nothing the gate blocks ever reaches the agent.
  2. **Agent instructions (behavioral)**: `OFFICE_INSTRUCTIONS` pins the allowed tool set (Launch, RunPython for document/email steps, the availability/file queries, `Visible` make-visible) and forbids `Quit`, `ScreenShot`, `Speak`, `Beep`, `DownloadImage`, `Demonstrate` for lane tasks; requires work-folder-only files, literal content only (no formulas/macros/DDE stored), never sends email without the sidecar's explicit send instruction, and never writes outside the task.
  3. **Reporting (audited)**: the STEP/TASK marker protocol (R6); the sidecar audits one entry per reported step and stamps `ok` only on `TASK: COMPLETED`.
- **Residual risk, documented**: an agent could under- or over-report its actions. Mitigations: the same trust boundary as the existing lanes, the append-only audit, the honest-envelope contract, and the user seeing the Office app left open on their desktop (the visible end state is itself a check). The spec's FR-004 governs *prompt→document* content and holds as written.

## R4 — Conversation state: PendingDraft + ActiveDocument

- **Decision**: in-memory sidecar state keyed by `conversation_id`, which the DSL binds to the tool (`{{#sys.conversation_id#}}` — a Dify sys variable, passed as a tool argument). `office_state.py` holds per-conversation `ActiveDocument` (path, per FR-013) and `PendingDraft` (per FR-009). Container restart loses it → the honest fallback is an ask-back again (documented, acceptable).
- **Rationale**: the hermes agent node is deliberately memory-light (query-only, stateless agent calls — 028 R4); the gate needs *deterministic* state to resolve "send it" against the exact recorded draft. Prompt-context state would be guesswork; sidecar state is testable (the battery passes conversation ids itself and asserts both entities' lifecycles).
- **Alternatives considered**: enabling the Dify node's memory window and parsing context (fragile, window-limited, untestable); persisting to the sidecar state DB (over-engineering for conversation-scoped scratch state).

## R5 — The email draft handle: COM EntryID

- **Decision**: turn 1 composes into Outlook's Drafts folder via COM and reports the draft's **EntryID** (stable across sessions); the sidecar records `PendingDraft(entry_id, displayed recipient/subject/body)`. A later confirmation resolves to the instruction "send the Outlook draft with EntryID `<id>` exactly as composed; do not modify it" — the agent fetches by ID and sends.
- **Rationale**: stateless agent turns need a durable, unambiguous handle; EntryID is it. Replaced/cancelled drafts are *not* deleted (mailbox-destructive ops are out of scope v1) — a replaced draft simply loses pending status and stays in the Drafts folder, reported honestly.
- **Alternatives considered**: re-composing on the confirm turn (two drafts, drift risk — rejected); the sidecar storing full content and re-sending (the sidecar cannot reach Outlook — rejected with R2).

## R6 — Step protocol: the 029 marker pattern, extended

- **Decision**: `OFFICE_INSTRUCTIONS` requires the agent to end each executed step with `STEP <n>: <operation> OK — <detail>` or `STEP <n>: <operation> FAILED — <detail>`, report the active file with `ACTIVE FILE: <windows-path>` and composed drafts with `DRAFT ID: <entryID>`, and end with exactly `TASK: COMPLETED` / `TASK: PARTIAL` / `TASK: FAILED`. The sidecar parses: per-step audit entries, state updates from `ACTIVE FILE`/`DRAFT ID`, envelope `ok` only on `COMPLETED`.
- **Rationale**: proven live in 029 (the LAUNCH marker caught a fabricated success on its first day); the step extension keeps FR-005's partial-state honesty machine-checkable.

## R7 — Configuration

- **Decision**: one new sidecar config field, `hermes_office_root` (default `"C:\\OfficeMCP"`, Windows-style — the gate checks prompt-named paths against it and the audit carries it as `allowed_root`). **No URL in sidecar config** — the bridge lives in the gateway's `hermes mcp` configuration, not in the sidecar (R2).
- **Rationale**: the sidecar never connects to OfficeMCP, so it must not configure it; the work folder is the gate's containment root and needs exactly one knob.

## R8 — Test strategy + error handling (per plan input)

- **Unit, failing-first** — `test_office_gate.py`: app/kind classification (excel/word/powerpoint/outlook; write/read/compose/confirm/cancel), work-folder containment (inside ok; `C:\Other\...` blocked naming the root), code-exec vectors (macro/DDE/`=X!` formula requests blocked), recipient rules (no-address compose → ask-back; confirmation classified only with pending state), reason strings. `test_office_state.py`: active-document switch/loss, pending-draft lifecycle (create → confirm/cancel/replace), conversation isolation, restart-loss semantics. `test_hermes_office_tool.py` (client mocked): gate-blocked never calls the agent + audits; step parse → per-step audit + envelope; `TASK: PARTIAL/FAILED` → honest partial/error envelope; confirm turn sends the recorded draft ID; service-down error mapping to the exact start-command hint; budget/timeout mapping.
- **Contract**: existing suites stay green; the 26th tool is additive; snapshot tests amended (25→26, scenario registry).
- **Battery** — `scenario_hermes_office_task` O-matrix: O1 Excel A1 write (verify the xlsx's A1 via stdlib `zipfile`+sheet XML — zero new deps); O2 follow-up B2 on the **active document** (same conversation id, second tool call); O3 email compose (pending draft recorded, `DRAFT ID` in report); O4 confirm-send turn (envelope `ok`, audit `executed`); O5 cancel flow; O6 refusal matrix (macro, DDE, out-of-folder, address-less compose, mailbox-delete → all gate-blocked, zero executions); O7 audit cross-check (one entry per step, truthful).
- **Error handling matrix** (each a unit case or battery check): OfficeMCP service down → `error` + the exact `officemcp sse …` start hint; gateway down → existing gateway hint; Office app missing/unlicensed → honest step failure, task PARTIAL; step failure mid-chain → stops, partial state reported; turn-budget exhaustion → stop at last completed step, remaining reported, "continue" resumes; state lost on restart → honest ask-back; formatting/attachment requests → honest out-of-scope notices.

## R9 — Host wiring (one-time, T001-class)

1. Windows: start the service — `officemcp sse --port 8888 --host 127.0.0.1 --folder C:\OfficeMCP` (user-managed; the lane's recovery hint repeats it).
2. WSL host: `hermes mcp add OfficeMCP --url http://127.0.0.1:8888/sse` then `hermes mcp test OfficeMCP` (confirm the exact SSE path at connect; adjust if FastMCP serves `/mcp` instead).
3. Office installed/licensed on Windows; WSL interop enabled (029 prerequisite still applies).
