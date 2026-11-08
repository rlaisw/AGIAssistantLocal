# Research: AI Control Dialog Timeout (Spec 032)

Date: 2026-11-08 · Scope: how the "AI is controlling this computer" notice works and what controls its duration.

## R1: What the "dialog" actually is (installed windows-mcp 0.8.8)

- **Decision**: The notice is not a separate message box — it is a bitmap (`_NOTICE_TITLE = "AI is controlling this computer"` in `desktop/control_overlay_art.py:16`) rendered inside the **control overlay**, the always-on-top border/glow window that is visible while the AI holds the desktop-control lease.
- **Rationale**: Direct source inspection of the installed package (`windows_mcp/desktop/control_overlay.py`, `control_overlay_art.py`).
- **Alternatives considered**: a Windows toast/dialog with its own timer — ruled out; no such code path exists in 0.8.8.

## R2: What timing constants exist in 0.8.8 (and which one the user sees)

- **Decision**: There is **no configurable dialog-duration setting** in 0.8.8. The hardcoded constants in `desktop/control.py` are: the **AI-lease tail** `_lease_until = time.monotonic() + 15.0` (line 317 — the overlay stays up to 15 s after the last AI action ends), and the **user-revert window** `10.0` (lines 151/207/214/226-228 — how long control stays in "user" state after physical input before reverting to "ready"). The ~10 s the user perceives is the overlay's post-action persistence governed by these constants.
- **Rationale**: `ControlConfig` in 0.8.8 holds only `mouse_takeover_units/pixels` (verified); `10.0` appears only as the user-revert/wait countdown; `ControlStatus.wait_seconds` derives from it.
- **Alternatives considered**: `~/.windows-mcp/config.toml [control] idle_timeout_seconds` — does **not exist** in 0.8.8 (that is a newer-version feature, and it gates the AI's wait-for-idle, which the owner decision A explicitly keeps at 10 s).

## R3: The change mechanism — local patch (primary), upgrade (fallback, per owner decision B)

- **Decision**: **Locally patch the installed package** (the house pattern — hermes-agent and OfficeMCP already carry documented local patches): reduce the overlay's post-action persistence so the notice clears within ~3 s of the last AI action, leaving every `10.0` user-revert constant untouched (owner decision A: idle/revert behavior unchanged) and leaving takeover mechanics untouched.
- **Rationale**: A config-only edit is impossible in 0.8.8 (R2); an upgrade would not provide a dialog-duration knob either — the newer `idle_timeout_seconds` is the *gate* timer, not the notice duration (owner decision A forbids changing it). The patch is ~2 constants on the lease tail (`15.0 → 3.0` in `control.py:317`) plus verification that `set_active(False)` fires on lease expiry (it does — state machine transitions at `_tick_locked`).
- **Alternatives considered**: (1) upgrade windows-mcp — rejected as primary: adds version churn and does not expose the needed knob; kept as fallback only if the patch proves unworkable (owner decision B, with full desktop-lane re-verification). (2) disable the overlay entirely (`WINDOWS_MCP_CONTROL=false`-equivalent) — rejected: owner wants the notice shortened, and FR-004 keeps the indicator visible during AI actions.

## R4: Restart and persistence vehicle

- **Decision**: The patch applies to the installed tool at `C:\Users\RLWC145\AppData\Roaming\uv\tools\windows-mcp\...`; the service restarts via the existing `windows-mcp-server` scheduled task (login auto-start + `./reboot.sh` health check). Persistence across reboots is inherent (the file edit survives; the task relaunches it).
- **Rationale**: established operational path (DEPLOY.md WindowsMCP section; reboot.sh step 1b).
- **Alternatives considered**: per-run CLI flags — none exist for this in 0.8.8.
