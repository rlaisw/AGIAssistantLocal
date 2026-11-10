# Bug Verification: disk-space recipe — the reported ask and alternate phrasings complete live with real Get-Volume output

- **Slug**: `disk-space-usage-isnt-one-of-the-commands-its-allowed-to-execute`
- **Tested**: 2026-11-09
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The capability gap is closed and verified live twice: the exact reported ask ("show me harddisk disk spaces usage", 09:43:39) and an alternate phrasing ("how much free space do I have on my drives") both dispatched real `hermes_run_command` calls, mapped through the `Get-Volume` recipe, executed on the Windows host, and relayed genuine output (C: ~105.35–105.36 GB free of 951.65 GB, ≈89% full; WinRE_DRV; F: CD-ROM) — audited with timing both times. The refusal integrity held: lookalike cmdlets, flags, and drive-letter arguments still refuse (pinned in the suite). No regressions: 94/94 suites.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix, LIVE — exact reported ask) | "show me harddisk disk spaces usage" via chat | **pass** | Real call → gate recipe → `Get-Volume` executed → honest relay with the drive table and usage advice; audit `executed run-command`, 23.6 s, 452 events (fix-phase probe, re-confirmed in the audit tail). |
| Reproduction (post-fix, LIVE — alternate phrasing) | "how much free space do I have on my drives" | **pass** | Same end-to-end path via the "free space"/"drive space" phrases — the recipe generalizes beyond the reported wording; live readings consistent across runs. |
| New / updated tests | `pytest tests/unit/test_hermes_run_gate.py tests/unit/test_hermes_run_tool.py -q` | **pass** | Mapping matrix (7 phrasings → `Get-Volume`), name-specific carveout (`Get-NetIPAddress`/`Get-PSDrive`/`Get-Disk` still refuse), flags + drive-letter argument refusals. |
| Regression suite | `pytest …test_hermes_launch_gate.py …test_hermes_launch_tool.py -q` | **pass** | 94 passed total — the launch lane, honesty/dispatch guards, and the full run-command matrix are unaffected. |
| Lint / type-check | `ruff check src/agentic_rag_mcp/hermes_run_gate.py src/agentic_rag_mcp/server.py` | **pass** | Gate source: all checks passed (the recipe code is clean); server.py's 10 findings are the day's pre-existing set (docstring-only change there). |
| Live graph state | Postgres `workflows` latest | **pass** | 09:43:06 carries `Get-Volume` (`t`) — recipe, instruction, tool description, and honesty-notice text all live. |

## Output Excerpts

```
Live (exact reported ask):   C: 105.35 GB free / 951.65 GB (≈89% full), F: 0 B,
                              WinRE_DRV 1.1 GB free — audit executed, 23.6s
Live (alternate phrasing):   C: 105.36 GB free / 951.65 GB — consistent reading
pytest: 94 passed | ruff (hermes_run_gate.py): All checks passed!
```

## Residual Risks

- The recipe list is deliberately narrow ("disk space", "hard disk", "harddisk", "disk usage", "free space", "drive/storage space", "get-volume") — exotic phrasings fall to the honest ask-back with the allowlist shown; extending is a one-line table entry plus tests.
- `Get-Volume`'s health/operational columns are volume metadata only — no state change; output is short and already bounded.
- The cmdlet carve-out is name-exact (`get-volume`); lookalikes refuse — pinned by test.
- Real-world note from the live output: the C: drive is ≈89% full — owner housekeeping, not a system defect.

## Recommendation

Close the bug — verified live end-to-end twice (the exact reported phrasing and an alternate), with refusal integrity pinned by the suite, the amendment recorded in spec 033's Clarifications, and the gate source lint-clean. Future allowlist extensions should follow this exact recipe pattern (fixed command in the gate table + mapping/integrity tests + DSL text sync + spec-Clarifications record).
