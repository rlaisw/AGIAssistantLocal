# Bug Verification: COM apartment guard in office v2 templates — fix live, shipped, and pinned

- **Slug**: slow-respone-come-back-again-first-attempt-fast-v2-document-path-failed
- **Tested**: 2026-11-14T05:20:00+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified — with one honestly-named residual (the broken worker window is service-side and not schedulable on demand; the proof is structural plus live)

## Summary

The fix is proven at every layer this environment allows: the **running sidecar container** serves all 4 guarded templates (`CoInitialize()` before `Dispatch(`, verified in-container), the ordering is **unit-pinned** against regression, and **live probes of both previously-failing operations** (`doc_write_v2`, `xls_write_v2`) succeed through the rebuilt sidecar. The exact failing trigger — an OfficeMCP RunPython worker thread with an uninitialized COM apartment — is service-side and intermittent, so the broken window itself could not be scheduled; with `CoInitialize()` now the first COM call in each template, the `-2147221008` failure is structurally unreachable, and the audit trail is the ongoing confirmation channel.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Shipped-artifact check | `docker exec agentic-rag python -c "…import 4 templates; count CoInitialize guards"` | **pass** | all **4/4** templates in the RUNNING container carry the guard — the fix is live, not just in the tree |
| Reproduction (post-fix, doc) | live `doc_write_v2` probe (fix phase, `com-init-probe-postfix.docx`) | **pass** | ok / created / `text_ok: true` — the exact operation that failed at 04:55:12Z |
| Reproduction (post-fix, xls) | live `xls_write_v2` probe (`com-init-probe.xls.xlsx`, B2=777) | **pass** | ok / created / fronted: true — the second operation that showed `-2147221008` in the audit trail |
| New / updated tests | `pytest tests/unit/test_office_v2.py` | **pass** | **16 passed**, incl. `test_templates_init_com_apartment_before_dispatch` (presence + ordering before `Dispatch(` for all 4 templates) |
| Regression suite | `pytest tests/unit` | **pass*** | 638 passed; **2 failures are pre-existing** (`test_browser_control_v2.py::TestType::test_type_not_found_asks_back`, `TestSensitiveExclusion::test_secret_absent_from_all_surfaces`) — reproduced on the clean tree during the fix phase (git-stash check); unrelated to this fix |
| Lint / type-check | `ruff check` (changed files) | **pass** | All checks passed |

## Output Excerpts

```
docker exec agentic-rag python -c "…count guards…"
  → shipped CoInitialize guards: 4

live xls_write_v2 probe → {"status": "ok", "path": "C:\\OfficeMCP\\com-init-probe.xls.xlsx",
                           "size": 8453, "existed": false, "fronted": true}

pytest tests/unit/test_office_v2.py → 16 passed in 0.03s
pytest tests/unit                  → 2 failed, 638 passed   (both failures pre-existing, clean-tree reproduced)
ruff check                         → All checks passed!
```

## Residual Risks

- The COM-uninitialized worker window originates in the Windows-side OfficeMCP service and is intermittent — it was **not** re-exercised in a broken state (cannot be forced on demand). The verification is therefore: structural (the pinned init-before-Dispatch ordering in the shipped container makes an apartment-init failure unreachable from these templates), plus live proof in healthy windows. Any recurrence of `-2147221008` on a v2 office row in `audit.jsonl` would indicate a COM failure mode beyond apartment init and should reopen the lifecycle.
- The two pre-existing browser-control v2 unit failures remain open from before this bug — they need their own lifecycle, not this one.
- The Windows-side deeper fix (CoInitialize on every OfficeMCP RunPython worker thread) remains an optional upstream note; the templates no longer depend on it.

## Recommendation

**Close the bug — verified to the limit the environment allows.** The failing call class is structurally fixed in the shipped artifact, both previously-failing operations succeed live, the ordering is unit-pinned, and the regression suite shows no new breakage (2 pre-existing failures aside, proven clean-tree). The next natural slow-office turn will confirm end-to-end in the chat UI; watch `audit.jsonl` for the absence of new `-2147221008` rows on `doc-write-v2`/`xls-write-v2`.
