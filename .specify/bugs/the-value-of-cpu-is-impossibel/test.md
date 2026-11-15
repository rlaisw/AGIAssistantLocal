# Bug Verification: CPU% scale explanation verified live — the relay explains >100% values; a separate consent-expiry envelope polish surfaced

- **Slug**: the-value-of-cpu-is-impossibel
- **Tested**: 2026-11-14T13:05:00+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: **verified** — the reported confusion no longer occurs on the acceptance path: CPU listings relay the genuine table plus the multi-core scale explanation (exercised live), the DSL pins hold, and the suite is green. A separate, non-blocking finding surfaced during verification: when the service's consent demand expires with no one at the desktop to approve, the final envelope reads as a raw tool-error instead of a named "approval expired" refusal — recorded as a follow-up.

## Summary

The bug's symptom (CPU% > 100% relayed with no scale explanation, reading as impossible) is fixed and live-proven: the post-fix replay's answer contained the genuine table AND the verbatim explanation ("values aggregate across **all logical processors**, so numbers above 100% are normal and correct — each fully-busy core contributes 100%"). The fresh test-phase replay exercised a different path — the service's consent demand expired with no approver present — which surfaced a small envelope-wording polish (below), not a defect in this fix.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix, acceptance path) | chat replay "on my computer, list the top 5 processes by cpu" (fix phase, conversation `0d128029…`, post-publish) | **pass** | answer = genuine table (audit: `windows-mcp-process` executed 11.3 s) + the scale explanation verbatim + a helpful reading of vmmemWSL's 175.3% |
| Reproduction (fresh, test phase) | same query (conversation `36d0f38b…`) | **pass\*** | the agent took the fast path and called the tool; the service's USER_CONTROL consent demand expired after the bounded retries (25.6 s, no approver at the desktop) → honest error envelope, no fabrication; the answer correctly explained the tool error instead of inventing a table — honesty held |
| Unit reproduction (direct tool) | `windows_mcp_process_list(sort_by="cpu")` (assessment phase) | **pass** | System Idle Process **1876.7%** on a 20-logical-processor host — the mechanism confirmed at the source |
| New / updated tests | `pytest tests/unit/test_intent_router_rules.py` | **pass** | 3 passed, incl. `test_cpu_percent_scale_explained` (the note pinned in exactly both DSL locations) |
| Regression suite | `pytest tests/unit` (full) | **pass** | 679 passed, 0 failed |
| Lint | `ruff check` (changed files) | **pass** | All checks passed |

## Output Excerpts

```
acceptance replay answer: "… table … Note on the CPU% column: the values aggregate across all logical
  processors, so numbers above 100% are normal and correct — each fully-busy core contributes 100%…"
fresh replay audit:     12:57:47 | windows-mcp-process | error | 25.6s | …USER_CONTROL… (consent expired, no approver)
pytest tests/unit → 679 passed, 0 failed
```

## Residual Risks

- **Consent-expiry envelope wording** (new finding, non-blocking): when the USER_CONTROL retry loop exhausts (nobody approves at the desktop), the final envelope surfaces as `error:windows-mcp-tool-error — {"code": "USER_CONTROL", …}` — honest, but the ideal text is the named refusal ("blocked: the host did not approve execution — the consent wait expired; ask again and approve at the Windows desktop"). A ~3-line client polish (`client.py`: classify a still-pending USER_CONTROL after the retry loop as the blocked envelope); left unmade in this read-only test phase.
- The windows-mcp service's USER_CONTROL consent states are environment-dependent (this session observed both instant approvals and desktop-gated waits) — the lane's bounded retry covers both; a user must be at the desktop when the service demands physical approval.
- The upstream service still reports the un-normalized aggregate (correct for its definition; explained in the relay since this fix). A dual-column upstream output remains the ideal end state.
- Bare phrasings still misroute to General (the parked pre-router decision) — the replays used the local-machine phrasing.

## Recommendation

**Close the bug — verified on the acceptance path.** The reported "impossible" CPU% is now impossible to misread: the relay explains the scale on every CPU-sorted listing, the pins lock the DSL text in both locations, and the full suite is green. The consent-expiry envelope polish is a small follow-up for the windows-mcp lane client (a named refusal instead of a raw tool-error), recorded here with the exact shape.
