# Bug Assessment: "The local agent failed" — gateway died after the attach-marathon, restart re-armed the strip window

- **Slug**: `local-agent-failed`
- **Created**: 2026-11-05T08:03+00:00
- **Source**: pasted text ("The tool returned an error. Per the spec: status error -> say the local agent failed and include the recovery")
- **Verdict**: valid — a fully evidenced four-link chain; the honest-error envelope is the designed mitigation working, not the defect
- **Severity**: medium — one failed turn with correct honest handling; but the chain reveals a new upstream fragility (silent gateway death) and an unbounded attach path that keeps re-triggering the whole cascade

## Report (verbatim or summarized)

> "The tool returned an error. Per the spec: status error -> say the local agent failed and include the recovery"

The user re-asked the email draft (body "test abc v3", subject "hello test v3") at 07:57:40; the chat replied that the local agent failed and included the recovery — the strip window had been re-armed minutes earlier.

## Symptom

The email task fails with the honest "local agent failed" error because the gateway's MCP channel strips RunPython arguments — the gateway had been restarted 4.5 minutes before the attempt (recovering an uncleanly-exited predecessor), and the ~10–15-minute post-restart strip window (hermes-agent #148459, documented in `the-tool-call-failed`) was open. Expected: the task composes the draft.

## Reproduction (all steps evidenced, 2026-11-05 UTC)

1. 07:24–07:34 — the previous email turn exceeded the sidecar's 600 s Hermes budget on the COM-broken Outlook (the attach-marathon); the sidecar timed out honestly at 07:34:52
2. 07:39:10 — the gateway **completed** that marathon turn server-side (gateway.log: "response ready"), five minutes after the client gave up
3. 07:39–07:53 — **the gateway exited uncleanly** (the next start logged `gateway.previous_unclean_exit`, prior PID 19144) — **no traceback in errors.log, no OOM in dmesg**: a silent death
4. 07:53:09–07:53:18 — `./reboot.sh` ran: OfficeMCP restarted, and the gateway — found **down**, so the skip-when-healthy guard correctly did not apply — was restarted (PID 19277), arming the strip window
5. 07:57:40 — the user's email attempt hit the 4.5-minute-old window: `STEP 1: Outlook process probe via RunPython FAILED — arguments stripped, default echo 'OfficeMCP' returned (3 canaries attempted, none delivered)` (07:58:04 audit) → honest "local agent failed" with the wait/recovery guidance
6. Current state: Outlook is now **fully closed** (the broken instance is gone — the fresh-state Launch path is available), and the window opened at 07:53:18, so delivery should resume ~08:08

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_client.py` — `OFFICE_INSTRUCTIONS`: the OUTLOOK ATTACH-FAILURE PROTOCOL does not bound its attach attempts — `GetActiveObject` fails fast, but each `Dispatch`/`EnsureDispatch` on a broken Outlook hangs ~1–2 min, letting turns run 600 s+ (the marathon that preceded today's gateway death)
- `src/agentic_rag_mcp/config.py` — `[hermes] timeout_s = 600` — the sidecar budget; the gateway kept running past it and died afterward
- Upstream (`~/.hermes/hermes-agent`) — two defects now: the argument-strip window (#148459) and the **newly observed silent unclean gateway exit after a >600 s agent turn** (no log trace; `gateway.previous_unclean_exit` is only recorded by the *next* start)
- `reboot.sh` — worked as designed (restarted a dead gateway); its fresh-start branch already prints the strip-window warning

## Root Cause Hypothesis

**High confidence.** The immediate cause is the strip window re-armed by a gateway restart that was itself correct recovery from a silent gateway death — and the chain's origin is the unbounded attach-marathon on the COM-broken Outlook: marathon turn → server-side completion 5 min past the client budget → silent gateway death → reboot.sh restart → window → failed turn. Three of the four links are known/documented; the new links this bug adds are the **unbounded attach path** (repo-fixable) and the **silent gateway death** (upstream evidence).

## Proposed Remediation

**Preferred**: bound the attach marathon — the one repo-side link that breaks the whole cascade. In the OUTLOOK ATTACH-FAILURE PROTOCOL, cap attach attempts explicitly: ONE fast `GetActiveObject` probe, then AT MOST ONE `Dispatch` attempt (each can hang ~1–2 min), then stop and produce the two-option ask-back. This keeps attach-failure turns inside the client budget, prevents gateway-strangling marathon turns, and preserves every honest-reporting property. Additionally, append the silent-death data point to the hermes-agent #148459 upstream evidence file (drafts already exist in two sibling bug dirs).

**Alternatives**:
- Raise `[hermes] timeout_s` — rejected: it makes every real failure slower and feeds the marathon
- Sidecar-side gateway-ETA reporting in the strip error — deferred: the container cannot see the host gateway's start time; reboot.sh already prints the warning at the moment of restart

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_client.py` — bounded attach text in the OUTLOOK ATTACH-FAILURE PROTOCOL
- `tests/unit/test_hermes_office_tool.py` — guard for the bounded-attach wording

**Tests to add or update**:
- Extend the instruction-guard test: the protocol must contain the one-Dispatch cap and the fast-probe-first ordering

## Risks & Considerations

- Bounding attach attempts trades a (tiny) chance of a false "not attachable" verdict on a very slow COM startup for certainty that turns finish inside the budget — the right trade for an unattended lane
- The gateway's silent death remains upstream; until hermes-agent fixes it, any >600 s turn is a mortality risk for the gateway — the bounded attach removes this lane's main producer of such turns
- The strip window is unavoidable after any gateway restart (including correct recoveries); the wait guidance is already deployed and reboot.sh prints the warning — user patience of ~15 min after restarts is the standing operating reality

## Open Questions

- [NEEDS CLARIFICATION: what triggered the reboot.sh run at 07:53 — the user, or something scheduled? If the user, nothing to change; if scheduled, the scheduler should respect the strip-window cost]
- The gateway's unclean exit had no log trace — its cause (crash in cleanup after the long turn? SIGKILL from a supervisor?) is unknown upstream-side; the evidence line is `gateway.previous_unclean_exit` recorded at 07:53:18 by the successor
