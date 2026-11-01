# Contract: hermes_launch_app MCP Tool (spec 029)

Adds **one** MCP tool to the sidecar's tool surface (tool count 24 → 25). All existing tool schemas stay byte-identical (Constitution I). The chatflow consumes it from the **existing** Hermes agent node (no new nodes); spec 028's file-lane contract is untouched.

## 1. Tool schema

```ts
hermes_launch_app(task: str) -> {
  status: "ok" | "blocked" | "error"
, decision?: "executed" | "blocked"           // present for ok/blocked
, result?: string                              // the agent's report, present when ok
, reason?: string                              // blocked/error explanation (names the rule or the failure + recovery hint)
, target?: string                              // the launch target as normalized
}
```

## 2. Gate pipeline (invariants, in order)

1. **Classify** the launch verb (open/launch/start/run) and strip filler phrasing ("on my computer", "the … program/app", "please").
2. **Extract one target**: a path token (Windows or host style, normalized — reusing the file lane's normalization semantics: mixed separators, drive-letter case, `..` clamping) or a bare application name.
3. **No target** → `blocked` with an ask-back reason asking which application to launch; nothing is assumed or started (FR-011).
4. **Executables-only** (FR-004): path targets must end `.exe` after normalization; script (`.bat/.cmd/.ps1/...`) and shortcut (`.lnk`) paths → `blocked` with the executables-only rule named — even when the file exists.
5. **No arguments, no shell** (FR-005): argument patterns (`--x`, `/x`, `key=value`, quoted argument strings, `;`/`|`/`&` chaining) or shell/PowerShell phrasing anywhere in the task → `blocked` with the no-arguments rule named. A smuggled second instruction leaves at most the clean launch runnable; the smuggled part is refused and reported.
6. **One target per request**: two launch targets named → `blocked` with an ask-back asking which one; never both from a single prompt.
7. **Audit**: exactly one `AuditEntry` per attempt at the verdict point (FR-006) — `operation` mirrors the verdict (`launch-app` allowed · `ask-back`/`unsupported` blocked, like the file lane); `allowed_root:""` on every launch-lane entry (the empty root is the lane's audit discriminator); executed entries post-completion with the agent's report, blocked/error entries with the reason. Blocked verdicts never produce a client call.

## 3. Execution contract (allowed verdicts only)

- `POST {hermes.api_url}/v1/responses` (existing `hermes_client.run_task`), Bearer key, `store:false`, `model:"hermes-agent"`, timeout `hermes.timeout_s` (300 s default) — **stateless**, no session chaining.
- `instructions` = `LAUNCH_INSTRUCTIONS`: launch exactly the stated target with **no arguments and no command line**; never launch a script or shortcut; if the target cannot be found or fails to start, report that honestly; report exactly what was observed (started fresh / already running-activated / failed with reason); **end the report with exactly `LAUNCH: SUCCESS` or `LAUNCH: FAILED: <reason>`** — the caller parses that line for the verdict, so the agent must never emit SUCCESS unless the program is really running.
- Non-200 / timeout / connection failure / key rejection / empty response → `status:"error"` with the established recovery hints (gateway down → start command; key rejected → config mismatch; timeout → retry smaller task); errors still write their audit entry; never a fabricated launch.

## 4. Honest-envelope invariants (Constitution IV)

- `ok` implies the agent's report ended with an explicit `LAUNCH: SUCCESS` attestation and the audit entry holds that report; a `LAUNCH: FAILED` report or a report with no attestation line is `status:"error"` — never `ok`.
- `blocked` implies nothing reached Hermes and no process was started by the lane.
- `error` implies no fabricated success; the reason names the likely cause and recovery.
- The chatflow node relays the verdict verbatim, never claims direct desktop access, and never re-attempts a blocked launch with rephrased targets (anti-smuggling, 028 FR-009 spirit).

## 5. Chatflow wiring

- `intent_router` "Hermes file task" class becomes the local-machine class: its prompt gains launch phrasing (launch/start/open/run a program or app on the user's Windows computer, by name or full path).
- The existing `hermes_agent` node gains `hermes_launch_app` alongside `hermes_file_task`; instructions extended additively (file rules verbatim + launch rules + tool selection: file operations → `hermes_file_task`, program launches → `hermes_launch_app`, mixed prompts may use each tool for its part).
- Answers merge through the existing answer nodes — no edge changes.

## 6. 028 decline-probe mapping (FR-010)

- Direct `hermes_file_task` probes from 028's battery B5 ("open notepad", "run a PowerShell command…") **keep expecting `blocked`** — the file tool stays file-only (FR-009, defense in depth).
- The user-facing flip ("open notepad" → launches) is asserted by the **new** battery scenario through `hermes_launch_app` and the classifier routing regression ("open notepad" lands on the Hermes branch); the PowerShell decline remains at every layer.

## 7. Tool description (DSL sync source)

"Launch a DESKTOP APPLICATION on the user's Windows computer via the Hermes agent (e.g. open Outlook/Excel/Notepad, or run C:\tools\mytool.exe). ANY executable by name or full .exe path — there is no allowlist. EVERY task is security-gated BEFORE execution: launch arguments, command lines, and shell/PowerShell phrasing are BLOCKED with a reason and never executed; script (.bat/.cmd/.ps1) and shortcut (.lnk) targets are BLOCKED (executables only); a task naming NO application is BLOCKED with an ask-back — relay that question to the user verbatim; two applications in one prompt is an ask-back too. Returns {status: ok|blocked|error, result?, reason?, target?} — relay the verdict honestly: on 'ok' report what the agent observed; on 'blocked' give the reason verbatim; on 'error' say the local agent failed and include the recovery hint. Never claim a launch happened when the status is not ok."
