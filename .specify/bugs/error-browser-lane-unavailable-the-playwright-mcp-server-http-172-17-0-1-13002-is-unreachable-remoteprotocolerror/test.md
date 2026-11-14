# Bug Verification: full down→envelope→recovery→up cycle proven live; health probe honest in the real failure state

- **Slug**: error-browser-lane-unavailable-the-playwright-mcp-server-http-172-17-0-1-13002-is-unreachable-remoteprotocolerror
- **Tested**: 2026-11-14T05:45:00+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified — the original failure state was forced live, the honest envelopes were observed in it, the recovery command was executed exactly as the hint prescribes, and the lane was restored end-to-end

## Summary

The bug does not reproduce post-fix, and — stronger — the verification **forced the genuine failure state live** (task stopped + engine process tree-killed → `:3002` empty), observed the fixed behavior in it (`browser_status` now reports `reachable: false` with the envelope — the exact state where the old code fabricated `reachable: true`), then ran the envelope's own recovery command (`schtasks /run /tn playwright-mcp-server` — the command that did not exist at assessment time) and watched the lane come back (`:3002` LISTENING, `browser_status` ok, `browser_navigate_v2` ok with a real page snapshot). No regressions: the full unit suite is green, including two browser-control tests that were failing pre-fix for environment reasons (below).

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Task durability | `schtasks /query /tn playwright-mcp-server /fo list /v` | **pass** | task **Ready**, action live with `--isolated` ("Task To Run: …playwright-mcp.cmd --isolated --port 3002…"), LogonTrigger + RestartOnFailure registered |
| Reproduction, forced down state | stop task (`schtasks /end`) + ordered engine kill (`taskkill /PID … /T /F` — the CRLF-in-PID interop gotcha noted) until `netstat :3002` = 0 listeners | **pass** | the genuine failure state the user hit at 05:12:28Z, now schedulable on demand |
| Health probe honesty in the down state | `browser_status` (sidecar, live) | **pass** | `reachable: false` + the unavailable envelope + recovery text — the old bare-TCP probe reported `reachable: true` in this exact state (the false positive from the assessment) |
| Envelope honesty in the down state | `browser_navigate_v2("https://example.com")` | **pass** | honest `error:browser-lane-unavailable … (RemoteProtocolError)` envelope, 0.0 s, audit row written |
| Recovery command works | `schtasks /run /tn playwright-mcp-server` (the envelope's own hint, verbatim) | **pass** | SUCCESS → `:3002` LISTENING (~15 s) — at assessment time this command failed with "cannot find the file specified" |
| Full restoration E2E | `browser_status` + `browser_navigate_v2` after recovery | **pass** | status ok/`reachable: true` (truthful — engine verified up); navigate ok, real snapshot ("Example Domain") through container→bridge→engine→Chromium |
| New / updated tests | `pytest tests/unit/test_dynamic_health.py tests/unit/test_browser_scripted_run.py` | **pass** | 20 passed — the bridge-mask mode (accept-then-close), the never-hang mode, and the live-SSE-responder mode all pinned |
| Regression suite | `pytest tests/unit` (full) | **pass** | **643 passed, 0 failed** — including `test_browser_control_v2.py::TestType::test_type_not_found_asks_back` and `TestSensitiveExclusion::test_secret_absent_from_all_surfaces`, which were failing earlier today on the clean tree: both resolve fields through the proxy and ran when the engine was **down** — the very condition this lifecycle repaired; they pass with the engine up. Not claimed as fixed by the code change, but the suite is fully green post-fix. |
| Lint / type-check | `ruff check` (changed files) | **pass** | All checks passed |

## Output Excerpts

```
forced down:   netstat :3002 → 0 listeners
browser_status (down)  → {"status":"error","dynamic":{"reachable":false},
                          "reason":"error:browser-lane-unavailable — … (RemoteProtocolError);
                          recover with start the Scheduled Task: schtasks /run /tn playwright-mcp-server"}
recovery:      schtasks /run /tn playwright-mcp-server → SUCCESS; :3002 → LISTENING
browser_status (up)    → {"status":"ok","dynamic":{"reachable":true,…}}
browser_navigate_v2    → {"status":"ok","page":"… Page Title: Example Domain …"}
pytest tests/unit → 643 passed, 0 failed
```

## Residual Risks

- The engine's long-run durability (LogonTrigger auto-start on next reboot, RestartOnFailure after a crash) is configured and registered but only the manual start path was exercised today; the next natural Windows logon is the confirmation point.
- `schtasks /end` kills the task wrapper but not the node engine's listening process — a forced-down procedure must kill the engine process itself (this verification used the ordered `taskkill /T /F`, same as the owner's watchdog path). Worth remembering for any future stuck-engine routine; no repo change required.
- The health probe reports the engine's HTTP liveness, not Chromium health — a wedged browser *inside* a live engine is out of this bug's scope (the separate watchdog/iso-restart runbook covers that).

## Recommendation

**Close the bug — verified end-to-end, including the failure state itself.** Every element of the assessment's contract was exercised live: the recovery command exists and works, the health probe is honest in the exact state that previously produced a false positive, the envelope text matches reality, and the lane is restored through the documented one-command recovery. The next natural browser task in the chat UI will confirm the user-facing path; the audit trail should stay free of new `browser-lane-unavailable` rows unless the engine genuinely dies — and if it does, the recovery now works.
