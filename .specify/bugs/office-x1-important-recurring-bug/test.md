# Bug Verification: Office X1 REPLACED: attestation

- **Slug**: office-x1-important-recurring-bug
- **Tested**: 2026-11-11T07:29:21Z
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: failed (at live reproduction; unit-level checks all pass)

## Summary

The fix's logic is correct and all four pins pass, and the full unit suite is green — but the **live reproduction shows the stamp still does not fire**: the sidecar container has **no `/mnt/c` mount**, so `_office_path_exists()` always returns False in production and the `REPLACED:` attestation never appears. The original X1 symptom would still reproduce in a battery run.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| New/updated tests | `pytest tests/unit/test_hermes_office_tool.py` | pass | 22/22 incl. the 4 X1 pins |
| Regression suite | `pytest tests/unit/` | pass | 550 passed |
| Container rebuild | `deploy redeploy` | pass | image rebuilt, 39 tools, health ok — fix IS in the container |
| **Reproduction (post-fix)** | live X1 probe: create + update `C:\OfficeMCP\overwrite_probe.docx` via the container's `hermes_office_task` | **fail** | update: `status=ok`, `v2` IS in `document.xml` (write leg ✓) but **no `REPLACED:` stamp** (report leg ✗) — identical to the pre-fix symptom |
| Root-cause probe | `docker inspect agentic-rag` mounts + in-container `Path('/mnt/c/...').exists()` | fail | **no `/mnt/c` mount**; exists()=False in the container — the pre-existence check cannot work from inside the sidecar |

## Output Excerpts

- Live create: `status: ok` — `REPLACED in create result: False` (correct for the create leg, but for the wrong reason — see below)
- Live update: `status: ok` — `REPLACED stamp present: False`; `v2 in document.xml: True`
- In-container probe: `mnt c exists in container: False`; mounts = rag-docs, ppt-master, config, huggingface — **no /mnt**

## Residual Risks / Deviations

The assessment's proposed remediation (pre-existence probe via the C:\→/mnt/c mapping) is **sound logic on a wrong assumption**: it assumed the sidecar can stat `/mnt/c` like WSL-side code (battery.py) can. The container cannot — the office lane never needed host-file visibility before, so no mount exists. The unit pins monkeypatched `_office_path_exists` (hermetic), which masked the environment gap until the live probe exposed it.

**Remediation for the next fix pass** (small, one candidate): mount the Windows drive **read-only** into the sidecar (`/mnt/c:/mnt/c:ro` in the compose definition) — the office lane never writes files itself (the agent does, host-side), so RO adds no write surface, and the probe then works for any `C:\…` target. Alternative (conversation-state signal) is weaker: it only knows files THIS conversation already touched, missing pre-existing files from earlier sessions — which is exactly X1's real case.

## Recommendation

**Do not close.** Re-run `/speckit.bug.fix slug=office-x1-important-recurring-bug` with this evidence: add the read-only `/mnt/c` mount (compose + redeploy path is already proven today), keep the existing pins but re-point one pin at the REAL container-visible mount (integration-level), then re-verify with the same live two-call probe used here. The X1 verdict will flip at that point — the battery needs no other change.
