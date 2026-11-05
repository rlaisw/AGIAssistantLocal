# Bug Fix: STEP BATCHING — well-formed tasks now run as one combined script; live compose 84–89 s → 41 s

- **Slug**: `a-little-bit-slow-to-create-email`
- **Fixed**: 2026-11-05T10:05+00:00
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`OFFICE_INSTRUCTIONS` gained the STEP BATCHING speed rule: well-formed single-application tasks execute ONE combined RunPython script (probe + operation + read-back, per-sub-step try/except) and report it as one STEP block, instead of spending a slow LLM round trip per mechanical step. Consent-gated steps (channel detection, email send-confirmation, Outlook restart) remain separate. Live verification: a stripped-channel email compose completed in **41 s** versus this morning's 84–89 s baseline.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | STEP BATCHING rule added ahead of the display rule: one combined script per well-formed task; per-sub-step try/except so failures never hide each other; one STEP block naming every sub-operation verbatim; the three never-batch cases pinned (channel detection, send-confirmation, Outlook restart) |
| `tests/unit/test_hermes_office_tool.py` | modified | Guard: "STEP BATCHING", "ONE combined RunPython script", the try/except requirement, and the transport-detection exception are pinned |
| Live sidecar | redeployed | ok: 4 steps, 26 tools |

## Diff Highlights (optional)

```python
"STEP BATCHING (speed rule): … Run ONE combined RunPython script that
performs the whole flow in a single execution: the process/attach probe,
the operation, and the read-back verification; wrap each sub-step in its
own try/except so one failure never hides the others; report the results
as ONE STEP block whose detail names every sub-operation and its outcome
verbatim. Keep SEPARATE steps only where a step must not batch: the
channel-degradation detection (it picks the transport), an email
send-confirmation, and an Outlook restart…"
```

## Tests Added or Updated

- `tests/unit/test_hermes_office_tool.py::test_office_instructions_contain_attach_failure_protocol` — batching-rule guard added (49 office tests pass)

## Local Verification

- `pytest tests/unit/test_hermes_office_tool.py tests/unit/test_office_gate.py` → **49 passed**; `ruff` clean; `deploy redeploy` → ok: 4 steps
- **Live timed compose (10:03:17)**: stripped gateway channel detected in 2 canaries → direct channel → **STEP 2 "Compose + verify OK (via direct channel)" as one combined execution** (attach, CreateItem, save, read-back in a single script) → `status ok, draft_pending True` in **41 s** — versus the 84 s (healthy) / 89 s (stripped) baselines from this morning. A healthy-phase turn should be faster still (no detection overhead).

## Deviations from Assessment

- None. The preferred remediation (step batching with consent-gate exceptions) was applied exactly; the instruction-slimming alternative was deliberately skipped per the assessment's regression risk, and the deterministic executor remains a follow-up.

## Follow-ups

- The deterministic sidecar executor (~10–20 s, no gateway LLM loop for well-formed tasks) remains the durable architectural fix — a spec-sized effort, owner to prioritize; the batching rule halves the pain meanwhile
- Two LLM layers still remain (Dify agent + gateway agent); a user-visible compose now ≈ 1–1.5 min total from send to answer, dominated by those hops
- The verification draft "batching-speed-verify" joined the Drafts folder — delete unwanted copies
- Observe a few natural user turns: if the batching rule is ever skipped by the model on a well-formed task, the guard test still pins the instruction; prompt-adherence is probabilistic as always
