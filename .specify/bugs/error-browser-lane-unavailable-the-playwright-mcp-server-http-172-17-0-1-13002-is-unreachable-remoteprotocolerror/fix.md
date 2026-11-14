# Bug Fix: Playwright engine durable again (UTF-16 task XML registered) + honest HTTP health probe

- **Slug**: error-browser-lane-unavailable-the-playwright-mcp-server-http-172-17-0-1-13002-is-unreachable-remoteprotocolerror
- **Fixed**: 2026-11-14T05:30:00+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — engine restarted and durable, recovery command real, health probe honest, E2E verified live

## Summary

The `playwright-mcp-server` Scheduled Task is now genuinely registered on the Windows host — the blocker was the task XML's encoding form: this host's `schtasks` rejects UTF-8-declared task XML ("unable to switch the encoding"), which is why every prior registration attempt silently failed; the repo XML is now UTF-16 (the accepted form) with `--isolated` restored in its action. The engine is live on `:3002`, the envelope's recovery command now actually works, and `probe_dynamic` now speaks HTTP through the bridge so `browser_status` can no longer report a fabricated `reachable: true`.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `windows/playwright-mcp-task.xml` | modified | `--isolated` restored in the action (the 2026-11-13 session-latch workaround was missing from the task's command line); file converted to **UTF-16 LE with BOM + `encoding="UTF-16"`** declaration — the form this host's `schtasks` accepts; header comment documents the encoding requirement |
| `src/agentic_rag_mcp/browser_lanes/dynamic_health.py` | modified | `probe_dynamic` now streams `GET /sse` through httpx with the 2 s never-hang budget: any HTTP response = alive, closed/reset/hang = the honest unavailable envelope (the old bare-TCP probe connected to the WSL bridge, which accepts unconditionally — reachable:true while the engine was dead) |
| `tests/unit/test_dynamic_health.py` | added | 3 pins (below) |

## Diff Highlights (optional)

```python
# dynamic_health.py — the honest probe
url = f"http://{host}:{port}/sse"
with httpx.Client(timeout=timeout_s) as client:
    with client.stream("GET", url):          # headers prove the engine; SSE may stay open
        return {"status": "ok", "dynamic": {"reachable": True, "url": url}}
# exception (httpx.HTTPError, OSError) -> the FR-011 unavailable envelope
```

```xml
<!-- task XML action, now registered live on the host -->
<Arguments>--headless cmd /c C:\Users\RLWC145\AppData\Roaming\npm\playwright-mcp.cmd --isolated --port 3002 --host 127.0.0.1</Arguments>
```

## Tests Added or Updated

- `tests/unit/test_dynamic_health.py::TestBridgeMaskMode::test_accept_then_close_reports_unavailable` — the exact bridge-mask failure mode (accept, then close before any HTTP response) must produce the unavailable envelope, not ok.
- `…::test_accept_never_speak_reports_unavailable` — accept-and-hang falls to the timeout honestly, never hangs the probe.
- `…::test_http_responder_reports_ok` — a live SSE responder (headers then held-open stream) reports ok without waiting for the stream to end; also pins the recovery text naming `playwright-mcp-server`.

## Local Verification

- Commands run: `pytest tests/unit/test_dynamic_health.py tests/unit/test_browser_scripted_run.py tests/unit/test_office_v2.py` → **36 passed**; `ruff check` on changed files → clean.
- Task registration (elevated, UAC consented): `schtasks /create /tn playwright-mcp-server /xml C:\temp\t-utf16.xml /f` → **SUCCESS**, `Get-ScheduledTask` → **Ready**; `schtasks /run` → **SUCCESS**; `netstat :3002` → **LISTENING (PID 30072)**.
- Sidecar: `deploy redeploy` → image rebuilt, container recreated, health ok, tools 53/53.
- Live E2E post-rebuild: `browser_status` → ok/`reachable: true` (now truthful — engine verified up); `browser_navigate_v2("https://example.com")` → **ok**, real page snapshot returned through the full container→bridge→engine→Chromium chain (the exact operation that failed at 05:12:28Z).
- Negative mode covered by unit pins (the bridge-mask case cannot be re-exercised live now that the engine is up).

## Deviations from Assessment

- The assessment's preferred registration path (`Register-ScheduledTask -Xml`, verify by export) was applied first and **silently no-oped** on this host (empty return object, no task, no error) — and strict `schtasks /create /xml` revealed why: `(1,40) ERROR: unable to switch the encoding`. The working path is `schtasks /create /xml` with a **UTF-16** copy of the XML; the repo file is now UTF-16 so the documented import command works as-is. Recorded here per the contract; no re-assessment needed (same root-cause family, same remediation shape).
- Scope addition: `--isolated` was restored to the task action — the assessment flagged the risk ("a re-registration with a stale action would trade this bug for the old one") and the XML indeed predated the workaround.

## Follow-ups

- On the next Windows logon, confirm the LogonTrigger auto-starts the engine (the task's `StartWhenAvailable`/`RestartOnFailure` settings now cover reboots and crashes).
- The health-probe change makes `browser_status` trustworthy; watch the audit trail for `error:browser-lane-unavailable` rows — each should now correspond to a genuinely down engine.
- Optional enhancement (assessment's alternative): teach the agent to offer running `schtasks /run /tn playwright-mcp-server` via the PowerShell lane (two-phase confirm) when the envelope fires — self-service recovery.
- The ephemeral helper files in `C:\temp` (`register-playwright-task.ps1`, `t-*.xml`, logs) can be deleted at will.
