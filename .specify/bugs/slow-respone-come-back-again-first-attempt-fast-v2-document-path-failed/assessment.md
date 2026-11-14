# Bug Assessment: slow response returned — "First attempt (fast v2 document path): failed" (CoInitialize)

- **Slug**: slow-respone-come-back-again-first-attempt-fast-v2-document-path-failed
- **Created**: 2026-11-14T05:02:30+00:00
- **Source**: pasted text ("slow respone come back again because First attempt (fast v2 document path): failed")
- **Verdict**: valid — reproduced in the audit trail; mechanism fully identified; intermittency confirmed by live probe
- **Severity**: medium — the fast office v2 path intermittently dies in ~0.1 s and the honest agent fallback re-runs the same work on the slow v1 office-task lane (70.3 s measured); no data loss, no fabrication — the turn completes correctly but the speed regression the v2 lane exists to fix returns whenever the failure window hits

## Report (verbatim or summarized)

> "slow respone come back again because First attempt (fast v2 document path): failed"

The user reports the slow-response problem is back, with the agent's own relay naming the cause: the first attempt over the fast v2 document path failed.

## Symptom

A simple "open Word and type X"-class request that should complete in ~0.5 s via `doc_write_v2` instead takes ~70 s: the v2 call fails instantly and the agent falls back to the v1 `hermes_office_task` lane (gateway OfficeMCP, multi-step) to complete the same work. Expected: the v2 fast path completes (as it did in yesterday's live re-tests at 0.5–0.6 s), or at worst retries the v2 path.

## Reproduction

1. 2026-11-14T04:55:12Z (12:55 HK) — conversation `472ce6c1…`: `doc-write-v2` call **fails in 0.1 s**; audit row `decision: error`, reason: `error:office-v2 malformed result — {"success":false,"error":"(-2147221008, 'CoInitialize has not been called.', None, None)"}`.
2. 2026-11-14T04:56:26Z — the same conversation's fallback `office-task` row: the v1 lane completes the identical work (create "abc test 123.docx" in C:\OfficeMCP, verify read-back, leave open+visible) in **70.3 s** over the direct :8888 SSE channel, explicitly initializing COM first ("COM initialized (CoInitialize OK)").
3. The same instant failure also appears on an `xls-write-v2` row (0.2 s, identical `-2147221008` error, conversation `2e385103…`) — so it is not Word-specific.
4. Live probe **now** (2026-11-14 ~05:00Z, conversation `bug-assess-com-init-probe`): `doc_write_v2("com init probe 2026-11-14")` → **ok, text_ok true, created** — the failure is intermittent by execution context, not deterministic.
5. Yesterday's rows show the healthy windows: `xls-write-v2` 0.5–0.6 s successes (`test1.xlsx`, `test2.xlsx`).

## Suspected Code Paths

- `src/agentic_rag_mcp/office_lanes/proxy.py:29-80` (`_WRITE_TEMPLATE`), `:82-97` (`_READ_TEMPLATE`), `:100+` (`_XLS_WRITE_TEMPLATE`), `:157+` (ppt template) — every v2 template starts `import win32com.client; …Dispatch('Word.Application')` **without calling `pythoncom.CoInitialize()` first**; they assume the OfficeMCP RunPython runner hands them a COM-initialized apartment.
- The OfficeMCP service's RunPython worker (Windows-side, out of this repo) — intermittently executes scripts on a thread without an initialized COM apartment (error `-2147221008`), likely after a service restart or worker-thread rotation; the same service in other windows runs the identical template fine (0.5–0.6 s).
- `src/agentic_rag_mcp/server.py:1790` (`doc_write_v2`) — the sidecar correctly surfaces the failure (audit `decision: error`), and the agent layer honestly relays "First attempt (fast v2 document path): failed" before falling back — the failure handling and honesty contracts all held.
- `.specify/bugs/officemcp-connection-error/` (prior lifecycle) — established that the gateway RunPython channel degrades; the v1 lane already carries an explicit CoInitialize + direct-channel fallback, which is why the 70 s path worked in the same window the v2 path failed.

## Root Cause Hypothesis

**High confidence, no new mechanism.** The office v2 RunPython templates are not COM-self-sufficient: they rely on the runner thread's apartment being initialized. The OfficeMCP service intermittently executes RunPython scripts on a COM-uninitialized thread, so within those windows every v2 office call (doc/xls/ppt alike) fails instantly with `-2147221008`, the agent honestly reports the failed fast attempt, and re-runs the work on the v1 lane — whose scripts DO initialize COM explicitly — at the v1 lane's multi-step cost (70.3 s measured). The intermittency (0.5 s successes yesterday and on today's live probe vs. instant failures at 04:55Z) matches a worker-thread/state condition in the service, not a template-logic bug.

## Proposed Remediation

**Preferred**: make every v2 template COM-self-sufficient — add a guarded `import pythoncom; pythoncom.CoInitialize()` (ignore already-initialized / failure-to-init is not possible to paper over — let real errors surface) as the first statements before `win32com.client.Dispatch(...)` in `_WRITE_TEMPLATE`, `_READ_TEMPLATE`, `_XLS_WRITE_TEMPLATE`, and the ppt template in `src/agentic_rag_mcp/office_lanes/proxy.py`. `CoInitialize` on an already-initialized thread returns S_FALSE harmlessly, so this is safe in the healthy windows and fixes the broken ones. Small, deterministic, and mirrors what the v1 lane's scripts already do.

**Alternatives**:
- Fix the worker threads in the Windows-side OfficeMCP service (initialize COM on every RunPython worker) — the deeper fix, but out of this repo's control and slower to ship; the templates being self-sufficient is the robust posture regardless.
- Have the sidecar retry the v2 call once on this specific error before surfacing it — rejected: a retry hides a real environment problem and adds latency; the template fix removes the failure instead.

**Files likely to change**:
- `src/agentic_rag_mcp/office_lanes/proxy.py` (4 templates: +2 lines each)
- `tests/unit/test_office_v2.py` (pins)

**Tests to add or update**:
- Unit pins in the existing style: each rendered template source contains a `CoInitialize()` call positioned before the `Dispatch(` call (the same string-level assertion pattern as the `.Text`-verify pin from still-little-bit-slow).
- Live re-probe after rebuild: `doc_write_v2` probe call returns ok (as today's probe did) — plus, if the broken window recurs, the row should now be a success instead of `-2147221008`.

## Risks & Considerations

- `pythoncom.CoInitialize()` must be guarded (`try/except` pass) so a genuinely broken COM environment still surfaces its real error rather than a new one from the init call itself.
- No API/contract change: tool signatures, DSL, and the honest-failure relay path all stay as-is; the agent's fallback behavior remains as the last line of defense.
- Sidecar rebuild required (the templates ship inside the sidecar image); no DSL change, no model change.
- The classification wording `office-v2 malformed result` for a structured `{"success":false,…}` payload is slightly misleading (it was a well-formed error, not a malformed result) — cosmetic; the full COM error was preserved in the reason field, so no observability data was lost.

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the mechanism is fully identified from the audit trail and live probe. The exact trigger of the service's uninitialized-worker windows (restart? rotation? concurrency?) is Windows-side and may be worth an upstream note to the OfficeMCP service owner, but the template fix is correct regardless.]
