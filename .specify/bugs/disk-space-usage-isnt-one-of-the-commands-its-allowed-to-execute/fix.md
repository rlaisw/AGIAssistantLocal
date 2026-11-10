# Bug Fix: disk-space recipe — `Get-Volume` joins the allowlist (spec-033 amendment, owner-requested)

- **Slug**: `disk-space-usage-isnt-one-of-the-commands-its-allowed-to-execute`
- **Fixed**: 2026-11-09
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The spec-033 allowlist amendment landed: disk-space phrasings now map to the **fixed read-only cmdlet `Get-Volume`** as the lane's first *named recipe* — the user's words never become command syntax, `Get-Volume` is the only cmdlet exempt from the generic cmdlet refusal (the recipe table in gate code is the boundary), and flags, drive-letter arguments, and every unlisted cmdlet still refuse. Live-verified end-to-end on the exact reported ask: real `Get-Volume` output (C: 105.35 GB free of 951.65 GB, ≈89% full) relayed honestly, audited with timing.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_run_gate.py` | modified | `Get-Volume` recipe entry (phrases: disk space(s), hard disk/harddisk, disk usage, free space, drive/storage space, get-volume); `_RECIPE_CMDS` cmdlet exemption; `_ALLOWLIST` gains "Get-Volume (disk space)" in every refusal text; bare no-args check now also refuses **drive-letter tokens** (`C:`, `C:\…` — `_tokens` strips colons, so the check reads raw tokens) |
| `tests/unit/test_hermes_run_gate.py` | updated + added tests | allowlist constant synced; `test_disk_space_phrases_map_to_get_volume` (incl. the exact reported phrasings); `test_recipe_carveout_is_name_specific` (Get-NetIPAddress/Get-PSDrive/Get-Disk still refuse); `test_recipe_still_refuses_flags_and_args` (incl. the drive-letter case) |
| `src/agentic_rag_mcp/server.py` | modified | tool docstring allowlist mention synced (+ "unlisted" before PowerShell cmdlets) |
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | instruction bullet, tool description, and the honesty-check notice list all name disk spaces / Get-Volume |
| `specs/033-hermes-run-command/spec.md` | modified | the amendment recorded in Clarifications per constitution governance (owner request, recipe rationale, rejected alternatives) |

## Diff Highlights (optional)

```python
"Get-Volume": (r"\bget[-\s]?volume\b", r"\bdisk\s+space", r"\bhard\s?disks?\b",
               r"\bdisk\s+usage\b", r"\bfree\s+space\b", r"\bdrive\s+space\b",
               r"\bstorage\s+space\b"),
_RECIPE_CMDS = {"get-volume"}  # the ONLY cmdlet exempt from the generic refusal
```

## Tests Added or Updated

- `test_disk_space_phrases_map_to_get_volume` — the seven disk phrasings (including "show me harddisk disk spaces usage") resolve to `Get-Volume`.
- `test_recipe_carveout_is_name_specific` — lookalike cmdlets still refuse with the allowlist shown.
- `test_recipe_still_refuses_flags_and_args` — `Get-Volume -Thoroughly` → flags refusal; `Get-Volume C:` → no-arguments refusal (drive-letter smuggle closed during the fix; `_tokens` was stripping the colon).

## Local Verification

- Commands: `pytest tests/unit/test_hermes_run_gate.py tests/unit/test_hermes_run_tool.py tests/unit/test_hermes_launch_gate.py tests/unit/test_hermes_launch_tool.py -q` → **94 passed** (final targeted run: 32).
- Live: sidecar hot-patched (gate + server docstring), chatflow published; Postgres graph `09:43:06` carries the recipe (`t`).
- **Live end-to-end on the exact reported ask**: "show me harddisk disk spaces usage" → real tool call → gate mapped to `Get-Volume` → real command executed → honest relay: *C: **105.35 GB free** of 951.65 GB (≈89% full), F: CD-ROM empty, WinRE_DRV recovery partition 1.1 GB free* with usage advice; audit `executed run-command`, 23.6 s, 452 events.

## Deviations from Assessment

- One hardening found during testing, within the assessment's scope: the bare no-args check originally missed drive-letter arguments (`Get-Volume C:`) because the tokenizer strips colons — fixed by checking raw tokens for the drive shape while validating the recipe's no-args policy. No other departures.

## Follow-ups

- The C: drive is ≈89% full (from the live output) — a real-world housekeeping note for the owner, not a system issue.
- Future recipes follow this exact pattern (fixed command in the table + tests + DSL sync + spec-Clarifications record) — the amendment path is now proven.
- Fold this fix into the next lifecycle commit together with today's honesty/dispatch-guard docs.
