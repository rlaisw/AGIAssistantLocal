# Bug Verification: "Failed to invoke tool" — wait-based strip-window guidance

- **Slug**: `the-tool-call-failed`
- **Tested**: 2026-11-05T07:36+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

This bug's two failure modes no longer reproduce: the strip window is confirmed **time-based** (0 stripped / 5 and 0 stripped / 7 delivered across two live email turns), the channel survives a full `./reboot.sh` run because the gateway is no longer restarted and OfficeMCP no longer re-registered (PID unchanged, arguments still delivered immediately after), and the launch guard prevented any Outlook Launch on the broken instance. What still blocks the user-visible compose: Outlook's COM server remains unattachable (owner declined the restart — cross-bug), and a **new finding**: the attach-failure protocol's Dispatch attempts hang long enough to hit the sidecar's 600 s Hermes timeout, so some turns end in `error: Hermes did not finish within 600s` instead of the intended ask-back.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix): email task through the lane | `hermes_office_task` email compose (07:14–07:20) | **pass** | 0 stripped / 5 delivered; no Launch on broken Outlook; ended in the attach-failure protocol's consent ask-back |
| No-re-arm: full `./reboot.sh` run | gateway PID before/after + skip-path output | **pass** | `Gateway: already up — NOT restarting`, `already registered — NOT re-registering`; gateway PID 19144 unchanged; all 7 health checks ok |
| Channel health immediately after reboot.sh | second email task + args log (07:24) | **pass (channel)** | 0 stripped / 7 delivered — the run did not re-arm the window; however the turn exceeded the sidecar's 600 s Hermes budget (see Residual Risks) |
| Incomplete-chunked-read reproduction (deploy mid-request) | not re-performed | **skipped** | Destructive: requires stopping the sidecar during an in-flight request; cause fully evidenced in the assessment (06:56:54 shutdown severed the stream); stream draining remains a follow-up |
| New / updated tests | `pytest tests/unit/test_hermes_office_tool.py tests/unit/test_office_gate.py` | **pass** | 49 passed, incl. the time-window/launch-guard guard |
| Regression suite | `pytest tests/unit` | **pass** | 332 passed |
| Lint / type-check | `ruff check src/agentic_rag_mcp/hermes_client.py`; `bash -n reboot.sh` | **pass** | clean / clean |

## Output Excerpts

```
./reboot.sh:
  [2/6] Hermes gateway...   Gateway: already up on :8642 — NOT restarting
  [3/6] MCP connection...    OfficeMCP: already registered — NOT re-registering
  (all 7 health checks ok; gateway pid 19144 → 19144)

args log after reboot.sh (second email turn): stripped: 0, delivered: 7
audit 07:34:52 → error: Hermes did not finish within 600s — try a smaller task…
pytest tests/unit → 332 passed
```

## Residual Risks

- **New finding — attach marathon can outlast the budget**: on the broken Outlook, `GetActiveObject` fails fast but the Dispatch/EnsureDispatch attempts hang (~1–2 min each); the second live turn burned the full 600 s sidecar budget and ended in `Hermes did not finish within 600s` instead of the designed ask-back. The protocol should bound itself: fast probe → ONE Dispatch attempt → ask-back. (Follow-up for the `only-one-version-of-outlook` lifecycle, which owns that protocol.)
- **Deploy-mid-request severing is still possible**: nothing drains in-flight MCP streams before a sidecar shutdown — the original attempt-1 symptom can recur whenever a deploy runs during active chat use (follow-up, ops).
- **Email compose remains blocked end-to-end**: Outlook's COM server is unattachable and the owner chose to leave it alone; when the owner consents (chat reply "2" or a manual full exit + reopen), the compose should complete — re-run this verification then.
- The ~10–15-minute window is measured from today's three restarts; treat the duration as approximate.

## Recommendation

**Hold as partial** — everything this fix changed is verified live (time-window model, no-re-arm, launch guard, tests, lint), and the bug's original failure modes did not reproduce. Two honest gaps remain outside this fix's scope: the 600 s attach-marathon timeout (needs a bounded-attach tweak in the sibling lifecycle) and the end-to-end compose (needs the owner's Outlook decision). Re-run the compose verification after the owner resolves Outlook; if the draft lands in Drafts, close this bug.

---
**Annotation (2026-11-05, 09:15 UTC)**: the "time-window" model verified above was falsified hours later — the channel stayed stripped for 71 idle minutes (08:20→09:04) while canary bursts of ~5–15 calls demonstrably flipped it back. The superseding model, cap, and guidance live in `say-the-local-agent-failed-and-include-the-recovery-hint` (assessment + fix).
