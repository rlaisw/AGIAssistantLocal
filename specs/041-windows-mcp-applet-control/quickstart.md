# Quickstart: the 041 test plan (unit + end-to-end + error handling)

The owner's explicit requirement: this feature ships with a test plan covering **unit tests, end-to-end cases, and error handling**. This document is that plan — runnable validation per tier.

## Prerequisites

- Sidecar rebuilt with the tier wrappers; bridge active; the Windows-MCP service running with its full surface (21 tools — verify: `tools/list` shows `App, PowerShell, Snapshot, Screenshot, Click, Type, …`).
- An active interactive desktop (the service requires it); the owner present for confirm-gated cases.
- `.venv/bin/python` for harnesses; `pytest` for units.

## A. Unit battery (deterministic; run first, expect red before implementation)

```
.venv/bin/python -m pytest tests/unit/test_windows_mcp_applets.py -q
.venv/bin/python -m pytest tests/unit/test_powershell_gate.py -q      # never-list extension
.venv/bin/python -m pytest tests/unit -q                               # full suite stays green
```

Pinned classes:
1. **Tier 1 launcher**: target-list membership; unknown/ambiguous → ask-back envelope naming the list; one-target rule; identifier-only execution (no extra args).
2. **Tier 2 read gate**: allowlist match → fixed command shape executed; unmapped → refusal with the list; write-shaped ("change/set/disable") → refusal; one-query rule.
3. **Tier 3 never-list extension**: adapter enable/disable, IP/gateway, firewall-profile disable, remote-access/account changes → refused at draft AND confirm; firewall-rule additions/changes → NOT refused (confirmed-only boundary).
4. **Tier 4 UI gate**: sequence draft text shape (control + effect per step); credential/password field → refused before any call, value absent from audit; UAC → stop + honest text; dialog cascade → stop + re-confirm; never-list-via-click → refused verbatim.
5. **Audit + loop-gate**: per-tier operation classes and decisions; open/read tools loop-exempt (the spec-040 precedent); GUI steps audit individually.

## B. End-to-end cases (live; the acceptance battery)

| # | Case | Expected |
|---|---|---|
| E2E-1 | "open device manager" (and one settings page: "open display settings") | window opens < 15 s; audit `windows-mcp-open-*` executed |
| E2E-2 | "what's my current power plan?" + "which network adapters do I have?" | genuine values < 30 s, no confirmation; system state provably unchanged (before/after config snapshot) |
| E2E-3 | a benign confirmed write (e.g. "set my power plan to high performance" → confirm) | draft verbatim → confirm → stored text runs; result relayed; < 60 s post-confirm |
| E2E-4 | a GUI flow on the safe starter set (e.g. uninstall a throwaway app from Programs and Features) | plain-word sequence → confirm → steps execute; final state relayed; per-step audit |
| E2E-5 | the full 21-tool surface check | `tools/list` count = 21 (the FR-001 pin) |

## C. Error-handling cases (live or harness-forced; first-class)

| # | Case | Expected |
|---|---|---|
| EH-1 | unknown applet ("open the flux capacitor panel") | ask-back with the target list; nothing launched |
| EH-2 | read request outside the allowlist ("change my DNS") | refusal with the list; no execution |
| EH-3 | write never-list attempt, confirmed twice ("disable my ethernet adapter" → draft refused; "yes" anyway) | refused at both phases, reason verbatim, 0% execution |
| EH-4 | unconfirmed write (draft shown, owner stays silent / asks a modification) | nothing runs; modification re-drafts |
| EH-5 | GUI: typing into a password field | refused before the call; value absent from every audit row |
| EH-6 | GUI: a UAC prompt appears mid-sequence | honest stop; no success claim; owner approves by hand |
| EH-7 | GUI: an unexpected dialog beyond the sequence | stop, describe, re-confirm |
| EH-8 | service down (task ended + port killed) / desktop disconnected | the honest unavailable envelope + real recovery hint, < 5 s |
| EH-9 | USER_CONTROL deferral during any tier | the named deferral; ask again shortly; GUI reports completed steps |
| EH-10 | credential content anywhere in relays/audit | masked (the sensitive rule) |

## D. Verification flow

1. Units red → implement → green; full suite green (house gate).
2. `deploy all` (tool count changes; DSL publish).
3. Run B and C in order (E2E-1/2 need no owner interaction; 3-4 and EH-3/4/6 need the owner confirming or declining).
4. Audit cross-check: every B/C case leaves the expected row (`grep windows-mcp ~/.config/…/audit.jsonl`).

## Post-reboot note

After the next natural reboot: rerun E2E-1/2/5 — the LogonTrigger auto-start must restore the full surface (21 tools) with zero manual configuration (spec SC durable-lane expectation, spec 040 T020 precedent).
