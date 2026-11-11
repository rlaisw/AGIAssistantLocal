# Bug Assessment: Office X1 overwrite-honesty — report never says "replaced"

- **Slug**: office-x1-important-recurring-bug
- **Created**: 2026-11-11T07:23:51Z
- **Source**: pasted text (owner's residual-issues review) + live battery/audit evidence from this session's three deploy windows
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim)

> "Office X1 — IMPORTANT (recurring bug) 3-for-3 battery failures"

Three consecutive `deploy all` batteries (036 run 04:05, 037 run 05:21, 038 run 06:30 UTC, all 2026-11-11) report:
`X1 overwrite-honesty FAILED (create=ok, update=ok, verified=False)`.

## Symptom

The X1 probe (spec 031: "overwrites … of user-named files with honest 'replaced' reports") creates a Word doc, updates it in place, and verifies two legs: the saved docx contains 'v2' AND the update's report says the existing file was replaced. The **file-write leg passes** (live evidence: `/mnt/c/OfficeMCP/overwrite_probe.docx` currently contains 'v2', no 'v1'; the 06:30 audit row reads "saved in place; read-back returned 'v2'"), but the **report leg fails every time** — all three runs' reports phrase the operation as "opened … wrote … saved (in place)" with no "replac*" wording, so the spec-031 pin `'"replac" in result'` never passes.

## Reproduction

1. Run `deploy all` (or the office battery section) — observe `X1 overwrite-honesty FAILED (create=ok, update=ok, verified=False)` every time.
2. Contrast: the update's audit outcome (e.g. 2026-11-11T06:30:09) says "wrote literal text 'v2', saved in place; read-back through Word returned 'v2'" — the overwrite itself is honest and works.
3. Inspect `C:\OfficeMCP\overwrite_probe.docx` post-run: `word/document.xml` contains 'v2' — the probe's xml leg passes; only the report-phrasing leg fails.

## Suspected Code Paths

- `src/agentic_rag_mcp/deploy/battery.py:516-539` — the X1 probe itself; CORRECT per spec 031 (not the bug).
- `src/agentic_rag_mcp/server.py` (`hermes_office_task` handler) — returns the agent's free-form step report verbatim; nothing enforces the spec-031 "replaced" wording on an overwrite of a pre-existing user-named file.
- `src/agentic_rag_mcp/hermes_office_gate.py` / office-lane DSL instructions — the step-report protocol does not mandate the "replaced the existing file" attestation when the target pre-exists.

## Root Cause Hypothesis

The spec-031 honesty requirement ("replaced" reports for overwrites) is enforced only as an LLM prompt-level convention; the office lane's returned report is free-form and — reliably — describes overwrites as "opened/wrote/saved", never "replaced". The battery pin is deterministic; the behavior it pins is not, so X1 fails ~always. This is a real contract bug, not a flake: the report the spec demands is never produced. Confidence: **high** (3-for-3 failures with consistent missing wording, while the underlying write verifies clean).

## Proposed Remediation

**Preferred**: make the "replaced" attestation **deterministic** — the 034 echo-and-attest pattern. In `server.py`'s `hermes_office_task` handler: before dispatching, check whether the verdict's target path exists (the same C:\→/mnt/c mapping the office lane already uses for step verification); after a successful write/save kind, append a standard attestation line to the returned result: `REPLACED: the existing file at <path> was overwritten` — stamped ONLY when the file pre-existed and the operation reported success (never fabricated for a fresh create; the create path gets no stamp, preserving the create/overwrite honesty distinction the probe also checks via the xml legs).

**Alternatives**:
- Strengthen the DSL office-lane instructions to require the word "replaced" — cheap but still LLM-dependent; X1 would pass/fail with model phrasing (the current bug's cause).
- Relax the battery probe — WRONG: the probe pins a spec-031 product requirement.

**Files likely to change**:
- `src/agentic_rag_mcp/server.py` (the `hermes_office_task` handler: pre-existence check + attestation stamp)
- `tests/unit/test_hermes_office_tool.py` (new pins)

**Tests to add or update**:
- Pre-existing target + successful write → result contains `REPLACED:` with the path (X1's report leg now deterministic).
- Fresh create → result contains NO `REPLACED:` stamp (honesty both ways).
- Unsuccessful write on pre-existing target → no stamp (never a fabricated replaced-claim).

## Risks & Considerations

- The pre-existence check must use the same path mapping the lane already trusts (`C:\OfficeMCP\…` ↔ `/mnt/c/OfficeMCP/…`); a mismatch would mislabel creates as replaces (or vice versa) — pinned by the tests above.
- The stamp must be appended to the result the agent relays, not an audit-only field (the probe reads the tool's returned result).
- Keep it additive: no schema change, no DSL republish required beyond the next regular deploy window.

## Open Questions

- None blocking — the evidence is complete from this session's three runs and the live file.
