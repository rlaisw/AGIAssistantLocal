# Data Model: AI Control Dialog Timeout (Spec 032)

Date: 2026-11-08

No application data entities are created or modified by this feature — it is a behavior timing change inside the Windows-side desktop automation service. The relevant "model" is the third-party control state machine and the two timing surfaces the spec distinguishes:

## Control state machine (third-party, read-only reference)

States: `ready → user → ai → (takeover) → user/ready` (generation counter increments per monitor restart).

| Timing surface | Constant (0.8.8) | Owner decision (Spec 032) | Change? |
|----------------|-------------------|---------------------------|---------|
| Overlay/notice persistence after the last AI action (`_lease_until` tail) | `15.0 s` (`control.py:317`) | Notice clears within ~3 s | **Yes → 3.0** |
| User-revert window / wait-for-idle countdown (`10.0` at `control.py:151/207/214/226`) | `10.0 s` | Must stay 10 s (FR-003, Clarifications Q1) | **No** |
| Physical takeover (mouse ≥ threshold units, Ctrl+Alt+Shift+Backspace) | immediate | Must stay immediate (FR-003) | **No** |

## Validation rules (from requirements)

- FR-001: notice auto-dismiss ≤ ~3 s after AI control ends (measured, SC-001, ≥2 consecutive tasks).
- FR-003: `ControlStatus.wait_seconds` countdown after physical input still reflects the unchanged 10 s window.
- FR-005: if the patched file is replaced/reverted (tool upgrade/reinstall), the service must not silently misreport — the honest signal is the observed notice duration reverting to ~15 s, caught by the quickstart check.
