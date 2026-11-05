# Bug Fix: direct browser MCP channel codified — canaries demoted to detector; window dedup added

- **Slug**: `the-local-agent-hit-a-transient-channel-error`
- **Fixed**: 2026-11-05T09:45+00:00
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The agent's improvised browser-based direct MCP channel (proven live at 09:30:54, when it delivered full arguments through `http://127.0.0.1:8888/sse` while the gateway client stayed stripped) is now the sanctioned recovery path: 2 canary echoes = detection, then the task finishes over the direct channel. The display rule gained window-dedup so consecutive turns stop opening extra Drafts windows (the "two Outlook instances" the user saw — one process, many windows). DEPLOY.md, the guard test, an earlier wrong annotation, and the upstream evidence were all brought in line.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | SESSION-DEGRADATION RULE: canaries are the **detector** (2 consecutive echoes → stripped; "do NOT keep canary-retrying"), recovery = **DIRECT OFFICEMCP CHANNEL** via browser/fetch (`http://127.0.0.1:8888/sse`, read `event: endpoint`, POST MCP JSON-RPC to `/messages/?session_id=…`, full arguments; every remaining step runs there, marked "via direct channel"); honest failure only if the direct channel is also unreachable; resets still forbidden. Display rule: "if the app already displays it, do NOT open another folder window" |
| `tests/unit/test_hermes_office_tool.py` | modified | Guard: 2-canary detection, direct-channel step + endpoint + "via direct channel" marker present; "up to 15" and "WAIT about 15 minutes" **absent**; window-dedup pinned; oscillation evidence ("71 idle minutes") kept |
| `DEPLOY.md` | modified | Known-defect row: oscillation model + the proven browser bypass (isolates the defect to the gateway's MCP client serialization); recovery = direct channel, never restart |
| `.specify/bugs/local-agent-failed/test.md` | appended | Correction: the direct-SSE fallback is real (browser tool, 09:30 evidence) — the earlier "embellishment" annotation was partially wrong |
| `.specify/bugs/only-one-version-of-outlook-can-run-at-a-time/upstream-comment-draft.md` | appended | Conclusive isolation for #148459: an ordinary HTTP client on the same host delivers full arguments during the stripped phase |
| Live sidecar | redeployed | ok: 4 steps, 26 tools |

## Diff Highlights (optional)

```python
"Recovery (reliable, proven live 2026-11-05): switch to the DIRECT
OFFICEMCP CHANNEL with your browser or fetch tool — open
http://127.0.0.1:8888/sse, read the 'event: endpoint' line for the
session POST URL (/messages/?session_id=...), then send MCP JSON-RPC
there (initialize, then tools/call) with full arguments; … every
remaining task step … can run through it. Mark those steps 'via direct
channel' in your step reports."
```

## Tests Added or Updated

- `tests/unit/test_hermes_office_tool.py::test_office_instructions_contain_attach_failure_protocol` — the direct-channel contract and window-dedup are pinned; the falsified burst/wait models must stay out

## Local Verification

- `pytest tests/unit` → **332 passed** (office suites 49); `ruff` clean; `deploy redeploy` → ok: 4 steps
- **Live (09:42:36)**: fresh email compose with the new rule — `status ok, draft_pending True`, **84 s total**, canary first (delivered — healthy phase), attach without second instance, draft composed and verified, Sent Items 0, full audit trail. The direct-channel path itself was exercised and proven by the 09:30:54 user turn (browser canaries `canary-direct-sse-browser-20261105-01` / `canary-sse-77` plus the real COM code, all delivered with arguments during a stripped phase); this turn confirms the new rule does not disturb healthy-path turns.

## Deviations from Assessment

- None. The assessment's preferred remediation was applied as specified.

## Follow-ups

- Run `/speckit.bug.test` after the next naturally-stripped email turn to observe the codified direct-channel path in production (the 09:42 turn hit a healthy phase, so the fallback step ran zero times)
- Post the updated upstream drafts (browser-channel isolation) to hermes-agent #148459 when a write-capable token is available — the isolation evidence is now conclusive
- The user now has **four** draft copies in Outlook's Drafts from today's verifications ("hello test v3" ×2, "Outlook hello test version 11" ×1, "direct-channel-verify" ×1) — delete the unwanted ones; the verification drafts are safe to remove
- If the browser channel ever proves flaky in battery runs, the WSL-side relay remains the fallback architecture (see `say-the-local-agent-failed…` fix.md)
