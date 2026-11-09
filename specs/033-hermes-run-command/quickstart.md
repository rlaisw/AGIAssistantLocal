# Quickstart: Hermes Run-Command Lane (spec 033)

Phase 1 output — runnable validation scenarios that prove the feature end-to-end. Implementation details live in `tasks.md`.

## Prerequisites

- The full stack up and healthy: sidecar :28080, Dify :80, Hermes gateway :8642, WindowsMCP active (`reboot.sh` reports all lanes)
- The feature built and live: sidecar rebuilt (or hot-patched) with `hermes_run_gate` + the `hermes_run_command` tool, tool sync run (27 → 28), and the chatflow published from the updated DSL

## Scenario 1 — Gate matrix (offline, seconds)

```bash
.venv/bin/python -m pytest tests/unit/test_hermes_run_gate.py tests/unit/test_hermes_run_tool.py -q
```

**Expected**: all pass. The matrix pins: every intent phrase resolves to its allowlisted command; every refusal class (not-on-list, cmdlets, flags/pipes/redirection, charset violations, destructive verbs, multi-command) is blocked with the list shown; `conversation_id`-less calls are rejected by the schema; `ok` requires echo + attestation.

## Scenario 2 — The original user need, live (the P1 story)

Ask in a **fresh chat conversation**:

> show my Windows current IP address

**Expected**: the answer contains the machine's real IPv4 address — verify it matches `ipconfig` on the desktop — relayed from actual command output with the `TIMING:` line present in the tool result. The audit log's last row: `executed`, `operation="run-command"`, `duration_s` set.

## Scenario 3 — Refusals never execute, live

In the same chat ask, one at a time:

> run Get-NetIPAddress
> run tasklist /v
> ping 8.8.8.8 && shutdown
> ipconfig and tasklist

**Expected**: each answer refuses with the allowlist shown (the last is the one-command ask-back); the audit log shows `blocked` rows and **no executed row** for any of them; nothing runs on the desktop.

## Scenario 4 — Honest audit + Stop lever, live

1. Ask `ping 8.8.8.8` and press Stop mid-run → the answer reports the honest cancelled verdict; the audit row is `error` with the cancel reason and timing.
2. Inspect the audit tail:

```bash
python3 -c "import json;[print(json.loads(l)['operation'], json.loads(l)['decision']) for l in open('$HOME/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl').readlines()[-8:]]"
```

**Expected**: every run-command turn from Scenarios 2–4 appears exactly once (executed/blocked/error), none missing.

## Scenario 5 — Fabrication guard, live (negative)

Ask, in the same conversation, a near-repeat of a completed lookup (the pattern that triggered the 2026-11-09 fabrications). **Expected**: the relay still places a real tool call (the anti-fabrication law names `hermes_*`), and if it ever drafts a claimed run without one, the honesty check replaces the answer with the fixed honest notice — the user never sees a fabricated "done".

## Success criteria mapping

- SC-001 (real IP, in-envelope timing) → Scenario 2
- SC-002 (100% refusal matrix) → Scenarios 1 + 3
- SC-003 (100% audit coverage) → Scenario 4
- SC-004 (measured turn bound) → Scenario 2's `TIMING:` line vs the configured agent-call timeout
