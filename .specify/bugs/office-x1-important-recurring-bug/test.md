# Bug Verification: Office X1 REPLACED: attestation

- **Slug**: office-x1-important-recurring-bug
- **Tested**: 2026-11-11T07:29:21Z
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified (second pass, after the read-only /mnt/c mount remediation)

## Summary

**Second pass (2026-11-11T08:00Z): verified.** The first pass exposed that the sidecar container could not see `/mnt/c` (probe always False); the follow-up fix added a read-only `/mnt/c` mount to `deploy/docker_ops.py` MOUNTS (no new write surface — the office lane never writes files itself). After `deploy redeploy` (container 8716f491f92b, mount live, probe file visible in-container), the live two-call X1 probe now shows BOTH legs: `status=ok`, `v2` in `word/document.xml`, and the deterministic `REPLACED: the existing file at C:\OfficeMCP\overwrite_probe.docx was overwritten.` line in the returned result — the exact battery pin (report leg) that failed 3-for-3 pre-fix. The 4 unit pins (overwrite/create/failure/read) stay green (22 office + 550 full suite), and the mount pin in `tests/unit/test_deploy_docker_ops.py` asserts 5 mounts incl. `/mnt/c:/mnt/c:ro`.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| New/updated tests | `pytest tests/unit/test_hermes_office_tool.py` | pass | 22/22 incl. the 4 X1 pins |
| Regression suite | `pytest tests/unit/` | pass | 550 passed |
| Container rebuild | `deploy redeploy` | pass | image rebuilt, 39 tools, health ok — fix IS in the container |
| **Reproduction (post-fix, pass 1)** | live X1 probe | fail | no stamp — container could not see /mnt/c (root-caused below) |
| **Reproduction (post-fix, pass 2)** | live X1 update probe after the RO mount + redeploy | **pass** | `status=ok` + `REPLACED: the existing file at C:\OfficeMCP\overwrite_probe.docx was overwritten.` + `v2` in document.xml — both legs green |
| Root-cause probe | `docker inspect agentic-rag` mounts + in-container `Path('/mnt/c/...').exists()` | fail | **no `/mnt/c` mount**; exists()=False in the container — the pre-existence check cannot work from inside the sidecar |

## Output Excerpts

- Live create: `status: ok` — `REPLACED in create result: False` (correct for the create leg, but for the wrong reason — see below)
- Live update: `status: ok` — `REPLACED stamp present: False`; `v2 in document.xml: True`
- In-container probe: `mnt c exists in container: False`; mounts = rag-docs, ppt-master, config, huggingface — **no /mnt**

## Residual Risks / Deviations

The assessment's proposed remediation (pre-existence probe via the C:\→/mnt/c mapping) is **sound logic on a wrong assumption**: it assumed the sidecar can stat `/mnt/c` like WSL-side code (battery.py) can. The container cannot — the office lane never needed host-file visibility before, so no mount exists. The unit pins monkeypatched `_office_path_exists` (hermetic), which masked the environment gap until the live probe exposed it.

**Remediation for the next fix pass** (small, one candidate): mount the Windows drive **read-only** into the sidecar (`/mnt/c:/mnt/c:ro` in the compose definition) — the office lane never writes files itself (the agent does, host-side), so RO adds no write surface, and the probe then works for any `C:\…` target. Alternative (conversation-state signal) is weaker: it only knows files THIS conversation already touched, missing pre-existing files from earlier sessions — which is exactly X1's real case.

## Recommendation

**Close — verified.** The read-only `/mnt/c` mount landed (`deploy/docker_ops.py` MOUNTS + the mount-count pin), the redeploy proved the probe chain end-to-end in-container (verdict=document-write → regex match → norm → exists → stamp), and the live two-call probe shows both X1 legs green. The next `deploy all` battery should print `X1 overwrite-honesty ok` for the first time since 2026-11-11 04:05.
