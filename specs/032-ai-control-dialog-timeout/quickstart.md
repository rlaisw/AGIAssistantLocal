# Quickstart: AI Control Dialog Timeout (Spec 032)

Date: 2026-11-08 · Validation guide for the ~3-second AI-control notice.

## Prerequisites

- The full stack is up (`./reboot.sh` all-green; WindowsMCP `:8800` healthy, `ControlStatus: ready`).
- You are physically at (or RDP-connected to) the Windows desktop — the notice is visual.

## Validation scenarios

### V1 — Notice clears in ~3 seconds (FR-001 / SC-001)

1. Restart the desktop automation service after the patch: `Start-ScheduledTask windows-mcp-server` (PowerShell) or `./reboot.sh` from WSL.
2. In the chat, send: `open chrome, type www.google.com` (or any launch + typing followup).
3. **Watch the screen**: when the AI begins typing, the "AI is controlling this computer" notice appears.
4. **Expected**: the notice clears within ~3 seconds after the AI's last action (previously it lingered up to ~15 s); typing still completes and verifies.

Repeat on a second desktop task — SC-001 requires two consecutive episodes.

### V2 — Wait-for-idle window unchanged (FR-003 / owner decision A)

1. Move the mouse or press a key while the AI is acting — control reverts to you and gated actions pause.
2. Query the control status (from WSL, via the agent or a raw probe): after your last physical input, `ControlStatus` reports `wait_seconds` counting down from **10**, unchanged.
3. **Expected**: takeover is instant; the 10-second revert countdown is exactly as before the patch.

### V3 — Takeover shortcut instant (FR-003 / SC-003)

1. During an active AI desktop action, press `Ctrl+Alt+Shift+Backspace`.
2. **Expected**: control returns to you immediately (AI stops gated actions).

### V4 — Persistence across restart (FR-002 / SC-004)

1. Restart the service (scheduled task) or reboot the machine; run `./reboot.sh`.
2. Re-run V1.
3. **Expected**: the ~3-second notice behavior still applies — the patch lives in the installed service files, which the login task relaunches.

### V5 — Honest failure surface (FR-005)

1. If the installed tool is ever upgraded/reinstalled (patch lost), re-run V1.
2. **Expected**: the notice visibly reverts to its old longer persistence — the quickstart check itself is the honest signal; the deployment doc must note the patch (re-apply step) so this is detectable.

## Notes

- Reference: `research.md` (which constants the patch touches), `data-model.md` (the two timing surfaces and what must NOT change).
- No repo-side tests are affected; the WSL suite (346 tests) must remain green.
