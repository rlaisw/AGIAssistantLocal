# Contract: hermes_office_task MCP Tool (spec 030)

Adds **one** MCP tool to the sidecar's tool surface (tool count 25 → 26). All existing tool schemas stay byte-identical (Constitution I). Consumed from the **existing** Hermes Local Agent node (no new Dify nodes); the file and launch lanes are untouched.

## 1. Tool schema

```ts
hermes_office_task(task: str, conversation_id: str) -> {
  status: "ok" | "blocked" | "error"
, decision?: "executed" | "blocked"
, result?: string          // the parsed step reports, present when ok
, reason?: string          // blocked/error (names the rule or the failing step + recovery hint)
, active_file?: string     // the conversation's active document (Windows path)
, draft_pending?: boolean  // true after a compose turn awaiting user confirmation
}
```

`conversation_id` is bound in the DSL to `{{#sys.conversation_id#}}` — never user-typed.

## 2. Gate pipeline (pure `office_gate.py`, invariants in order)

1. **Classify** the task: kind (document-write / document-read / compose-email / send-confirmation / cancel / continue) and app (excel / word / powerpoint / outlook).
2. **Work-folder containment** (FR-003): every path the prompt names must normalize inside the active Office work folder (`hermes_office_root`, default `C:\OfficeMCP`); anything else → `blocked` with the root named.
3. **Prompt-borne code execution** (FR-004): macro/script/DDE/external-link-formula requests → `blocked` with the rule named; document content is written as literal values only.
4. **Email rules** (FR-008/FR-009): compose requires an explicit recipient address in the prompt — none → ask-back (never guessed from contacts); the address and content are relayed verbatim.
5. **Confirmation resolution** (FR-009): a send-confirmation/cancel resolves against the conversation's `PendingDraft`; no pending draft → ask-back ("no email is waiting to be sent"). A confirmation **only** sends the recorded draft EntryID — never a new or modified one; a modification request re-composes and re-displays a fresh draft.
6. **Resume resolution** (FR-005): a "continue" phrase resolves against the conversation's **Interrupted** record (original task + partial report, stored on `TASK: PARTIAL` and budget-timeout attempts); no record → honest ask-back; the resume directive replays the original task plus the partial context and clears the record on resumed completion.
7. **Audit**: exactly one `AuditEntry` per gate refusal (`operation="office-task"`, `allowed_root` = the work folder). Blocked verdicts never produce an agent call.

## 3. Execution contract (allowed verdicts only)

- `POST {hermes.api_url}/v1/responses` via the existing `hermes_client.run_task` with `OFFICE_INSTRUCTIONS` plus a per-task directive. The agent executes Office steps through **its own MCP connection to OfficeMCP** (host-wired once: `hermes mcp add OfficeMCP --url http://127.0.0.1:8888/sse`); the sidecar never talks to OfficeMCP.
- **Step protocol** (machine-checkable honesty, extends the 029 LAUNCH marker): each executed step ends with `STEP <n>: <operation> OK — <detail>` or `STEP <n>: <operation> FAILED — <detail>`; the report carries `ACTIVE FILE: <windows-path>` after document work and `DRAFT ID: <entryID>` after a compose; it ends with exactly `TASK: COMPLETED` | `TASK: PARTIAL` | `TASK: FAILED`. A FAILED step stops the chain; no step cap — budget exhaustion stops at the last completed step and the remaining steps are reported for resume.
- **Agent tool rules** (in `OFFICE_INSTRUCTIONS`): allowed — `Launch`, `RunPython` (document/email steps), availability/file queries, `Visible`(true). Forbidden for lane tasks — `Quit`, `ScreenShot`, `Speak`, `Beep`, `DownloadImage`, `Demonstrate`. Files only inside the work folder; literal content only; never send email unless the directive says `SEND PENDING DRAFT <entryID> exactly as composed`; the Office app is left open showing the result.
- Failures (service down / app missing / step failure / timeout) → honest `error` or `PARTIAL` envelope with the exact recovery hint (service down → the owner's `officemcp sse --port 8888 --host 127.0.0.1 --folder C:\OfficeMCP` start command); every step still audits.

## 4. Honest-envelope invariants (Constitution IV)

- `ok` requires the agent's `TASK: COMPLETED` marker; `PARTIAL`/`FAILED`/missing markers → honest error/partial, never fabricated success.
- Compose turns never send: the envelope returns `draft_pending: true` with the draft shown verbatim; only a later user confirmation (resolved against the recorded PendingDraft) produces a send directive.
- Per-step audit entries hold the `STEP` line text; the audit trail is append-only.

## 5. Chatflow wiring

- Classifier: the "Hermes local task" class gains Office-control phrasing (open/edit/write Word/Excel/PowerPoint/Outlook documents, cells, slides, emails).
- The existing Hermes Local Agent node gains `hermes_office_task` (with `conversation_id` bound to `{{#sys.conversation_id#}}`); its instructions add the office rules additively — file and launch rules verbatim; mixed prompts may call each lane's tool for its part.

## 6. 028/029 regression mapping

- The file and launch lanes' contract tests and battery probes stay byte-identical (FR-012 of the spec).
- "open Excel" with no task → still the launch lane (029), launch-only behavior unchanged; the classifier distinguishes control-from-launch by the task content.

## 7. Tool description (DSL sync source)

"Execute a Microsoft Office task on the user's Windows computer via the Hermes agent and the Office automation service — Word, Excel, PowerPoint, Outlook (e.g. 'open Excel and put 12345 in cell A1', 'create a Word doc with …', 'write an email to a@b.com saying …'). EVERY task is gated BEFORE execution: document work is confined to the Office work folder (default C:\OfficeMCP); macro/script/DDE or executable cell content is BLOCKED; email is COMPOSED first and shown verbatim — it is sent ONLY after the user confirms in chat (send the draft shown, unchanged); recipients come only from the user, never from contacts. Follow-ups continue on the conversation's active document (named in every answer). Multi-step tasks report each step honestly; failures stop at the failing step with the partial state. Returns {status, result?, reason?, active_file?, draft_pending?} — relay honestly: on 'ok' report the steps; on 'blocked' give the reason verbatim; on 'error' include the recovery hint. Never claim a step that did not run."
