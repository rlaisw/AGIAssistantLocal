# Bug Fix: "The local agent failed" — bounded attach marathon + live e2e compose verified

- **Slug**: `local-agent-failed`
- **Fixed**: 2026-11-05T08:20+00:00
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The attach marathon is bounded (one fast `GetActiveObject` + at most one `Dispatch`, then the ask-back), removing this lane's producer of 600 s+ turns that ended in gateway deaths. The live verification then produced the day's **first fully successful email compose**: with Outlook freshly closed, the task launched a clean Outlook instance, attached, composed the "hello test v3" draft into Drafts, and verified it by EntryID — routing around the still-stripped gateway channel via the agent's direct-SSE fallback.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | OUTLOOK ATTACH-FAILURE PROTOCOL is now **bounded**: at most ONE fast GetActiveObject, at most ONE Dispatch (each can hang 1–2 min), then the two-option ask-back — with the why recorded in the instruction text (the unbounded loop ran turns past the 600 s budget and the gateway died afterward) |
| `tests/unit/test_hermes_office_tool.py` | modified | Guard test pins "AT MOST ONE fast GetActiveObject" and "AT MOST ONE Dispatch attempt" |
| `.specify/bugs/only-one-version-of-outlook-can-run-at-a-time/upstream-comment-draft.md` | appended | New upstream data point: the gateway exited uncleanly with no log trace after completing a >600 s agent turn server-side |
| Live sidecar | redeployed | ok: 4 steps, 26 tools |

## Diff Highlights (optional)

```python
"...attach with AT MOST ONE fast GetActiveObject and, if that fails,
AT MOST ONE Dispatch attempt (a Dispatch on a broken Outlook can hang
1-2 minutes — never more than one; local-agent-failed 2026-11-05: an
unbounded attach loop ran turns past the 600 s client budget and the
gateway died afterward)..."
```

## Tests Added or Updated

- `tests/unit/test_hermes_office_tool.py::test_office_instructions_contain_attach_failure_protocol` — extended with the bounded-attach assertions (17 office-tool tests pass)

## Local Verification

- `pytest tests/unit/test_hermes_office_tool.py` → 17 passed; `ruff` clean; `deploy redeploy` → ok: 4 steps
- **Live e2e (08:15:42, the assessment's reproduction)**: email compose with Outlook closed — audit trail: gateway canary FAILED (7 echoes, strip persists) → direct-SSE canary OK → **Outlook launched fresh via COM Dispatch and attached** → **draft composed verbatim into Drafts** → **re-found by EntryID, recipient resolved to Raymond Lai (PR_SMTP_ADDRESS confirmed)** — `status: ok, draft_pending: True`. Outlook now runs as a clean, attachable instance; the "hello test v3" draft is in the user's Drafts folder.

## Deviations from Assessment

- **The time-window model (from `the-tool-call-failed`) is falsified.** The 07:53 gateway restart was still stripped at 08:13 (20 min) and at 08:15 (22 min, 7 echoes) — and a fresh `hermes mcp test` did **not** heal the channel (the discovery-heal hypothesis is also dead). Waiting is therefore **not** a reliable recovery; the wait-based instruction text is now known to be incomplete. The earlier ~14-minute heals must have had another trigger (unknown — not pure time, not `mcp test`).
- **What actually worked: the direct-SSE fallback.** The agent routed the compose around the stripped gateway channel over a direct SSE connection to OfficeMCP (the locally patched http/SSE transport), which delivered arguments correctly on the first try. This turn succeeded *because* of that fallback — it was the agent's own doing, not part of any instruction.
- The bounded-attach fix itself is unaffected by both findings and stands on its own evidence.

## Follow-ups

- **Re-assess the strip model** (`/speckit.bug.assess`) with today's new facts: the window is not time-bounded at ~15 min, `mcp test` doesn't heal it, and the direct-SSE fallback demonstrably bypasses it — the durable lane fix is likely to **promote the direct-SSE fallback into the official instructions** (detect strip → switch to direct-SSE for the task steps), making the lane independent of the upstream defect
- Update the wait-based instruction text once the model is re-assessed
- Add the falsification data points (22-min persistence, no mcp-test heal) to the hermes-agent #148459 evidence drafts
- The user's "hello test v3" draft is pending in Drafts (my probe conversation holds the pending state); the user can send it from Outlook or say "send it" in chat (the tool locates the draft by content)
