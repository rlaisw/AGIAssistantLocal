# Bug Verification: 540-second honest envelope — verdicts always precede the daemon kill; healthy turns unaffected

- **Slug**: `desktop-followup-timeout-600s`
- **Tested**: 2026-11-08T09:05+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original symptom — a desktop-followup turn killed silently at ~600 s by the Dify plugin-daemon (no verdict, no audit entry) — no longer reproduces: the exact failing request now ends at 540 s with the honest "Hermes did not finish within 540s — try a smaller task" verdict and a full audit entry (verified live in the fix phase), and a fresh quick launch confirms healthy turns pass through the new budget untouched (16 s, `status ok`). No regressions appeared.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) — the exact failing request | live `hermes_launch_app("open windows control panel , display my network adapter")` (fix phase, 08:47–08:56) | **pass** | At **540 s**: `status: error`, verdict *"Hermes did not finish within 540s — try a smaller task"*, **full audit entry** (08:56:55, decision=error). Pre-fix, this identical request died at 601.9 s with `PluginDaemonInternalServerError`, an empty answer, and no audit — the honest envelope now closes first, as designed |
| Healthy-turn non-interference | live `hermes_launch_app("open notepad")` (this phase) | **pass** | `status ok` in **16 s** — PID-verified fresh launch; the 540 s budget adds no overhead or behavior change to normal-speed turns |
| New / updated tests | `pytest tests/unit/test_hermes_launch_tool.py tests/unit/test_hermes_launch_gate.py` | **pass** | 51 passed — incl. budget-under-kill-timer source pin, `run_task` timeout override reaching the honest error message, fastest-path instruction guard |
| Regression suite | `pytest tests/unit` | **pass** | **354 passed** |
| Lint | `ruff check` on the two changed files | **pass** | 0 findings on changed hunks (5 pre-existing I001s elsewhere, unchanged) |

## Output Excerpts

```
exact request (fix phase): "error:Hermes did not finish within 540s — try a
  smaller task" → status error, AUDIT 08:56:55 decision=error
healthy turn (this phase): "Notepad started fresh… PID 1088" → status ok — 16 s
pytest tests/unit → 354 passed
```

## Residual Risks

- A 540 s verdict means the followup did not complete — by design, honest failure replaces silent death; the fastest-path guidance aims to pull most turns under the cap, but its observed effect needs natural turns (the verification run still ground to the cap; navigation-quality findings, if any recur, are follow-ups, not budget defects)
- The same daemon-kill race exists for the office/file lanes (600 s Hermes budget); no kills observed there yet — the `timeout_s` override mechanism now exists and is a two-line extension per lane if needed
- WindowsMCP's slow UIA captures (20–26 s snapshots observed) remain the dominant time sink on navigation turns; `WINDOWS_MCP_EXCLUDE_PROCESSES` is the documented knob
- The user-visible answer on a 540 s failure now flows through the chat honestly — users should expect "try a smaller task" as the actionable hint, and request-splitting ("open control panel", then "display my adapter") remains the practical route for heavy navigation

## Recommendation

**Close the bug — verified end-to-end at the envelope level.** The silent kill is gone: every long launch-followup turn now ends with an honest, auditable verdict inside the daemon's ceiling, healthy turns are provably unaffected, and the full suite holds. The navigation-speed guidance and office-lane extension are documented follow-ups, not open items for this bug.
