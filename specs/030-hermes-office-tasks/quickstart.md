# Quickstart: Hermes Office Task Lane (spec 030)

Validation guide — proves the lane end-to-end. Implementation details live in `tasks.md`; contract invariants in [contracts/hermes-office-task.md](contracts/hermes-office-task.md); entities in [data-model.md](data-model.md).

## Prerequisites

- **Office automation service running on Windows** (owner-managed): `officemcp sse --port 8888 --host 127.0.0.1 --folder C:\OfficeMCP` — the lane's down-error carries this exact command as its recovery hint. Not started yet at plan time (probe-verified).
- **Gateway bridge wired once on the host**: `hermes mcp add OfficeMCP --url http://127.0.0.1:8888/sse` then `hermes mcp test OfficeMCP` (mirrored-network loopback, probe-verified).
- Hermes gateway up (spec 028), WSL interop enabled (spec 029), Microsoft Office installed and licensed on the Windows machine.
- Sidecar `agentic-rag` up with this feature's code; `deploy chatflow` published with the classifier + node wiring.

## 1. Unit suites (deterministic, no network)

```bash
.venv/bin/python -m pytest tests/unit/test_office_gate.py tests/unit/test_office_state.py tests/unit/test_hermes_office_tool.py -q
```

Expected: all green — the gate matrix (kinds, containment, code-exec vectors, recipient rules, confirmation classification), the state lifecycle (active document, pending draft, conversation isolation), and the tool wrapper (step parsing, confirm flow, error mapping — client mocked).

## 2. Existing suites stay green (Constitution I)

```bash
.venv/bin/python -m pytest tests/unit tests/integration tests/contract -q
```

Expected: green (one pre-existing web-research failure reproduces in the old workspace — known, out of scope); the 26-tool surface is additive; 028/029 lanes' suites unchanged.

## 3. Live battery (deployed stack + Office)

```bash
.venv/bin/python -m agentic_rag_mcp.deploy verify
```

Expected: existing scenarios unchanged **plus** the office scenario green:

| # | Probe (via `hermes_office_task`, battery passes conversation ids) | Expected |
|---|-------------------------------------------------------------------|----------|
| O1 | "open Excel and put 12345 in cell A1" | `ok`; `TASK: COMPLETED`; a workbook in `C:\OfficeMCP` whose sheet XML reads A1 = 12345 (stdlib `zipfile` parse — no new deps); audit per step; Excel left open |
| O2 | Follow-up "also write 'hello' in B2" (same conversation id) | `ok` on the **active document** — the answer names the same workbook; B2 verified in the XML |
| O3 | "write an email to raymond.lai@tvb.com.hk with subject 'test' and body 'Hello World'" | envelope `draft_pending: true`; draft shown verbatim; `DRAFT ID` recorded; **nothing sent**; audit composed-step |
| O4 | "send it" (same conversation id) | the recorded draft's EntryID sends exactly as shown; `ok`; audit executed |
| O5 | Cancel flow: compose → "cancel that email" | draft dropped (not deleted), `draft_pending` false, honest report |
| O6 | Refusal matrix: macro request, DDE formula, out-of-folder path, address-less compose, "delete my emails" | all `blocked` at the gate with named rules; zero executions; audit refusals |
| O7 | Audit cross-check | one truthful entry per step/refusal, `operation="office-task"`, `allowed_root` = the work folder |

## 4. Manual chat check (end-user view)

In the Chat UI, one conversation: *"open Excel, put 12345 in cell A1"* → Excel opens with the value; then *"also write 'hello' in B2"* → continues on the same workbook; then *"write an email to raymond.lai@tvb.com.hk saying 'test Hello World'"* → the draft is shown verbatim and **nothing sends** until you reply *"send it"*. Every step visible in the audit log.

## 5. Error handling checks (each covered by a unit case or battery check)

- OfficeMCP service stopped → `error` with the exact `officemcp sse …` start hint; nothing fabricated.
- Office app missing/unlicensed → honest step failure; task `PARTIAL`, remaining steps reported.
- A step fails mid-chain → chain stops; partial state reported; no later step claimed.
- Turn-budget exhaustion → stops at the last completed step; "continue" resumes.
- Sidecar restart → conversation state lost → next turn asks back honestly (never assumes).
- Formatting/attachment requests → honest out-of-scope notices.

## 6. Cleanup

The lane leaves Office apps open by design (owner decision); the battery's workbooks live under `C:\OfficeMCP` — close Excel/Outlook and delete battery workbooks at will; replaced drafts remain in Outlook's Drafts folder (never auto-deleted); the audit log is never pruned.

## Recorded outcomes (implementation, 2026-11-02)

Host wiring that worked (T001): service started via WSL interop (`officemcp.exe sse --port 8888 --host 127.0.0.1 --folder C:/OfficeMCP`, survives the launcher), gateway wired with `yes | hermes mcp add OfficeMCP --url http://127.0.0.1:8888/sse` (14/14 tools enabled — the add prompt needs continuous `y`); the `conversation_id` sys-variable interpolation in the node instruction verified live — the agent passed the correct id in its own reasoning.

Full O-matrix live PASS (144 s): O1 Excel A1 write + verified in sheet XML; O2 follow-up B2 on the same active workbook; O6 refusal matrix 5/5 gate-blocked; O3 compose → `draft_pending` + `DRAFT ID`, nothing sent; O4 confirm → the recorded EntryID sent; O5 cancel → dropped not deleted; W1 Word doc verified in `word/document.xml`; P1 PowerPoint slide verified in slide XML; O7 audit truthful (per-step entries, `allowed_root = C:\OfficeMCP`).

Live findings, all answered honestly by the design:
1. Cold-starting Outlook via COM can exceed the 300 s agent budget — first compose errored honestly with the retry hint; the battery warms Outlook via the launch lane first (the FR-005 fallback works: retry succeeded once warm).
2. OfficeMCP v1.0.5 upstream bug: the `IsFileExists` tool calls `Officer.IsFileExists` but the implementation is `IsFileExits` — the tool always raises. The agent honestly reported the FAILED step (→ TASK: PARTIAL → error envelope — the honesty machinery caught a real upstream bug); `OFFICE_INSTRUCTIONS` now tell the agent to avoid the tool; the natural partial probe (impossible-file step) needs no synthetic case — this incident is the evidence.
3. Gateway lifecycle: the service manager SIGTERMs the gateway on rotation and a stale MCP session stalls turns to the budget — the lane's error carries the exact `officemcp sse …` + `hermes gateway restart` hints; recovery verified.

Sweeps: pytest full suite 449 green after amending snapshots to the 26-tool/14-scenario surface; two failures reproduce identically in the old workspace (web-research cap, onedrive staleness — pre-existing environmental drift, out of 030 scope). Frontend untouched and green (136/136). DSL published to the live app; sidecar hot-patched (image rebuild pending).

Convergence pass (2026-11-02, tasks T023–T025):
- **T023 resume path**: `OP_CONTINUE` now classified ("continue"/"resume"/"keep going"); interrupted-task state (original task + partial report) is stored on `TASK: PARTIAL` and on budget-timeout errors; "continue" replays it as a resume directive and clears on completion; "continue" with nothing pending asks back honestly. 6 new failing-first tests (45 office tests total, green).
- **T025 mixed-lane**: unit probe asserts each lane owns its part (office gate on the office part, file gate on the file part); the node instruction now says "pass each tool ONLY its own part of the request as its task text" — republished.
- **T024 full battery**: 13/14 green as one run — health, tools-surface (26), deck-roundtrip, completion-page, honest-errors, stop-generation, hermes-file-task (B1–B5), hermes-launch-app (L1–L9), **hermes-office-task (full O-matrix incl. email compose/confirm/send)**, antv-chart, antv-infographic, chart-in-deck, chat-journey; `chat-ui-liveness` failed only because no dev server was running at battery time and re-verified green immediately after starting it (chat-ui=200) — same environment pattern as spec 029.

Analyze follow-up (2026-11-02, finding I1 HIGH): the formatting refusal from clarify pass 2 had shipped unimplemented — *"make A1 bold"* classified as a normal document-write and the agent would have applied it. Fixed: gate `_RE_FORMATTING` detection (blocked with the "formatting is a follow-up version" reason), a defense-in-depth instructions line, one failing-first test (46 office tests green), and the live probe verified — *"make cell A1 bold"* → `blocked` instantly, audit refusal, no agent call. Artifact syncs applied the same day: data-model + contract gained the Interrupted resume record (T023's state), and FR-010's wording matched the shipped launch mechanism.
