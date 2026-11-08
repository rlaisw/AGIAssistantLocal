# Feature Specification: Shorten the AI-Control Dialog Display to 3 Seconds

**Feature Branch**: `[032-ai-control-dialog-timeout]`

**Created**: 2026-11-08

**Status**: Draft

**Input**: User description: "help to reduce 'AI is controlling this computer' dialog message box from 10 sec. to 3 sec."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Dialog auto-dismisses in 3 seconds (Priority: P1)

When the desktop automation agent begins controlling the user's Windows computer, a dialog/indicator appears stating "AI is controlling this computer" (with its visible edge and cursor-glow indicator). Today it stays for about 10 seconds, sitting over the user's work. The user wants it to auto-dismiss within about 3 seconds, so the screen returns to normal quickly while automation continues in the background.

**Why this priority**: This is the entire feature request — the dialog duration is the user-visible pain. Everything else preserves existing safety behavior.

**Independent Test**: Trigger any desktop followup (e.g., "open chrome and type www.google.com" in the chat) while seated at the machine; time the dialog from appearance to auto-dismiss; assert it disappears within ~3 seconds and the automation still completes.

**Acceptance Scenarios**:

1. **Given** the agent begins a desktop-control action, **When** the control dialog appears, **Then** it auto-dismisses within approximately 3 seconds (not the previous ~10).
2. **Given** the dialog has auto-dismissed, **When** the agent continues the desktop task, **Then** the task proceeds unaffected (typing/clicking still complete and verify).
3. **Given** a fresh machine/session start, **When** desktop control begins for the first time, **Then** the shortened duration applies without per-task reconfiguration (the setting persists across restarts).

---

### User Story 2 - Safety behavior unchanged (Priority: P2)

The dialog duration shrinks, but every existing safety mechanism must keep working exactly as before: the user's physical take-over (big mouse move or the Ctrl+Alt+Shift+Backspace shortcut) must still interrupt AI control instantly, the indicator/glow must still be visible while the AI acts, and no security gating may be relaxed.

**Why this priority**: Protects the user's ability to seize control — non-negotiable; the feature is purely cosmetic duration, not a safety reduction.

**Independent Test**: During an active AI desktop action, press Ctrl+Alt+Shift+Backspace (or move the mouse firmly); assert control returns to the user immediately and the AI stops gated actions.

**Acceptance Scenarios**:

1. **Given** the AI is performing a desktop action, **When** the user presses the take-over shortcut, **Then** control returns to the user immediately (unchanged from today).
2. **Given** the shortened dialog has dismissed, **When** the AI continues acting, **Then** the screen-edge/cursor AI indicator remains visible for the duration of AI control.
3. **Given** the setting is applied, **When** any gated desktop action runs, **Then** the same consent/idle rules apply as before — only the dialog's display duration changes.

---

## Requirements *(mandatory)*

### Functional Requirements

1. **FR-001 — Shortened dialog duration**: The "AI is controlling this computer" control dialog must auto-dismiss within approximately 3 seconds of appearing (previously ~10 seconds).
2. **FR-002 — Persistent configuration**: The shortened duration must be the default for every subsequent launch of the desktop automation service (configured once, survives service restarts and machine reboots — no per-run flags required in normal operation).
3. **FR-003 — Take-over unaffected**: The user's physical take-over (substantial mouse movement or the keyboard shortcut) must stop gated AI actions immediately, exactly as before.
4. **FR-004 — Indicator visibility preserved**: The visual AI indicator (edge/cursor glow) must remain present while the AI owns the desktop, independent of the dialog's shorter display.
5. **FR-005 — Honest failure reporting**: If the duration setting cannot be applied (e.g., the running service rejects it), the chat must report that the dialog duration is unchanged rather than silently keeping the old value.

### Success Criteria

1. **SC-001**: The control dialog auto-dismisses within ~3 seconds on every observed AI-control episode (measured on at least two consecutive desktop tasks).
2. **SC-002**: Desktop tasks that were working before (launch+typing followups, search followups) still complete and verify end-to-end with the new setting.
3. **SC-003**: User take-over during an AI action still interrupts immediately (shortcut or mouse move) — no regression in responsiveness.
4. **SC-004**: After a service restart (scheduled task or machine reboot), the ~3-second duration still applies.

### Key Entities *(optional)*

- **Control dialog/indicator**: the on-screen notice shown while the AI controls the desktop ("AI is controlling this computer").
- **Desktop automation service**: the Windows-side service (WindowsMCP) that owns the dialog and the desktop-control policy; configured via its config file, restarted via its login task.
- **Take-over shortcut**: the keyboard/mouse action that instantly returns control to the user.

## Implementation Notes *(optional)*

The setting lives in the Windows-side desktop automation service's control configuration (its config file's `[control]` section — the `idle_timeout_seconds`/dialog display value, default 10). The service requires a restart after the config change (no hot reload); its login scheduled task is the restart vehicle. The WSL-side stack (Hermes registration, health checks) is unaffected.

## Assumptions

- The dialog the user refers to is the desktop-control notice shown by the Windows-side automation service (WindowsMCP) when the AI begins gated desktop actions; its display/timeout is governed by the service's control configuration, default 10 seconds.
- "10 sec. to 3 sec." means shortening the existing default, not adding a new dialog.
- The change is a configuration edit on the Windows side plus a service restart; no code changes in the WSL repo are expected (documentation of the change may land in DEPLOY.md per house convention).

## Out of Scope

- Removing the dialog entirely (the user asked to shorten it, not remove it).
- Changing the desktop-control policy (relaxed/balanced/strict), take-over mechanics, or consent gating.
- Modifying the WSL-side Hermes lanes, gates, or chatflow prompts.
