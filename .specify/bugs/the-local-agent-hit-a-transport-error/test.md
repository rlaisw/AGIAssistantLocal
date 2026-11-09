# Bug Verification: cycle 3 — every env-configurable ceiling verified live; the 300.000 s cut is a confirmed Dify-daemon hard limit

- **Slug**: `the-local-agent-hit-a-transport-error`
- **Tested**: 2026-11-09T02:05+00:00 (cycle 3 test; supersedes cycle 2's failed report — git preserves it)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial — matches the fix's own status; the achievable remediation is complete and verified; the binding constant is compiled into the Dify plugin-daemon

## Summary

The full configuration chain is verified live end-to-end (provider row 600, plugin-process env 600, daemon backwards-invocation knobs 600000 after the empirically-proven millisecond correction), the stack is healthy (a chat-side launch completed with PID-verified success in 57 s), and the >300 s reproduction — exercised repeatedly during the fix cycle — cuts at exactly **300.03 s** under the fully-corrected daemon. The symptom survives all configuration; it is a hard limit of the compiled Dify plugin-daemon, and every occurrence ends honestly (accurate relay + re-ask, no silent kills).

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix), sub-300 s path | live chat turn "open task manager" (this phase) | **pass** | 57 s, `status=normal`-equivalent, audit `executed` (PID 21280, window snapshot-confirmed), no transport error — the healthy path works through the fully-corrected chain |
| Reproduction (post-fix), >300 s path | the decisive wallpaper/device-manager samples (fix phase, under the 600000-corrected daemon) | **fail — known limit** | Sidecar stream 01:48:50.278 → 01:53:50.307 = **300.03 s** — the identical cut with every knob raised; the binding constant is compiled into the Dify daemon's invoke path |
| Full env chain live | row query; daemon `env` grep; plugin `/proc` (fix phase) | **pass** | Row 600/600 · daemon env: MAX_REQUEST/MAX_INVOCATION=600, BACKWARDS_*=600000 (grep count 4) · plugin process `/proc` verified in the fix phase |
| Unit correction proof | 600 → all-LLM-reads-fail → 600000 → recovery (fix phase) | **pass** | The millisecond unit is empirically pinned; the misstep was caught and corrected within the cycle |
| Regression suite | `pytest tests/unit` | **pass** | **354 passed** |
| Stack health | Chat UI :3000 → 200; simple cloud turn streamed reasoning (fix phase) | **pass** | The transient gunicorn keep-alive flakiness after daemon restarts recovered on its own |

## Output Excerpts

```
env chain: row=600 | daemon MAX_* = 600 ×2, BACKWARDS_* = 600000 ×2 (grep count 4)
health turn: "Task Manager … started fresh with PID 21280, no arguments.
  Snapshot confirms the 'Task Manager' window" → executed — 57 s, no cut
>300s samples (fix phase): cut at 300.03s (01:48:50.278 → 01:53:50.307)
pytest tests/unit → 354 passed
```

## Residual Risks

- **The known limit**: chat-side `hermes_*` tool calls cap at ~300 s until the Dify plugin-daemon changes upstream — file the issue (the fix.md follow-ups contain the complete evidence file: five verified config changes, two recreates, the cut invariant at 300.000 s)
- The failure UX is verified good: honest relay, re-ask hint, no silent kills, no data risk; fastest-path guidance keeps most turns far below the cap; split-request posture covers heavy navigation
- The transient post-restart LLM-read flakiness (gunicorn 2 s keep-alive default) may recur after daemon recreates; it self-recovers — no action needed unless it persists
- All raised values (600/600/600/600000) must survive Dify upgrades — DEPLOY.md carries the re-check commands

## Recommendation

**Close as a documented known limit** — the partial verdict is the terminal state for this lifecycle: everything configuration could do is done, verified live, and correctly valued (including the ms-unit discovery); the remainder belongs upstream. Next actions: (1) file the Dify plugin-daemon issue with the ready evidence file, (2) keep the split-request habit for >300 s navigation, (3) re-test opportunistically after any future Dify upgrade — if a daemon version honors the backwards-invocation knobs or adds an invoke-path timeout env, the >300 s sample should be re-run to close the limit entirely.
