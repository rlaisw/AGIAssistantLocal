# Bug Fix: burst-retry rule replaces the falsified wait guidance — hypothesis partially falsified in live verification

- **Slug**: `say-the-local-agent-failed-and-include-the-recovery-hint`
- **Fixed**: 2026-11-05T09:25+00:00
- **Assessment**: ./assessment.md
- **Status**: partial — applied as specified, but the live verification **falsified the core hypothesis** (see Deviations); a re-assessment is recommended

## Summary

The falsified "WAIT about 15 minutes" guidance and the too-low 3-canary cap were replaced with a 15-canary burst-retry rule and retry-based recovery text, in the instructions, DEPLOY.md, the guard test, and the live sidecar. The live verification then ran the exact scenario: 15 consecutive canaries on a stripped channel — **and the channel did not flip**. The burst-recovery hypothesis is refuted as causation; the strip state oscillates on its own schedule.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_client.py` | modified | SESSION-DEGRADATION RULE rewritten: FLIPS framing, 15-canary cap, retry-based recovery text ("ask again — retrying the request flips the channel back"), reset commands still forbidden |
| `tests/unit/test_hermes_office_tool.py` | modified | Guard: "up to 15" + "15 consecutive" present; "WAIT about 15 minutes" **absent**; flips/71-minute evidence pinned |
| `DEPLOY.md` | modified | Known-defect row: flip model, burst-retry recovery, no restart, no wait |
| `.specify/bugs/the-tool-call-failed/test.md` | annotated | Time-window model falsification note pointing here |
| `.specify/bugs/local-agent-failed/test.md` | annotated | "direct-SSE fallback" was embellishment; superseding model lives here |
| `.specify/bugs/only-one-version-of-outlook-can-run-at-a-time/upstream-comment-draft.md` | appended | Flip/burst characterization for issue #148459 |
| Live sidecar | redeployed | ok: 4 steps, 26 tools |

## Diff Highlights (optional)

```python
"If a RunPython call returns only the default echo, keep retrying with
tiny canaries (code like 'output = data') — up to 15 attempts; the burst
itself is what flips the channel back. … Only if 15 consecutive canaries
all echo the default, STOP … recovery: ask again …"
```

## Tests Added or Updated

- `tests/unit/test_hermes_office_tool.py::test_office_instructions_contain_attach_failure_protocol` — burst-rule guard (49 office tests pass)

## Local Verification

- `pytest tests/unit/test_hermes_office_tool.py tests/unit/test_office_gate.py` → **49 passed**; `ruff` clean; `deploy redeploy` → ok
- **Live (09:16–09:18)**: the user's exact email task on the stripped channel — **15 consecutive canaries echoed the default, 0 delivered**; the honest error fired with the new retry-based text. The channel did NOT flip — **the assessment's core hypothesis (burst heals it) is refuted by this run**.

## Deviations from Assessment

- **The central claim failed live verification.** The assessment proposed the 15-canary cap on the evidence that breakthroughs followed bursts (~5–15 calls) — but 15 identical canaries produced no flip. Retrospectively, today's earlier "breakthrough" turns each spanned several minutes with mixed activity; the deliveries coincided with the channel's own state changes (delivered 08:15–08:20, stripped 09:04 and 09:16 — independent of call volume, restarts, or `mcp test`). The most consistent model now: the strip state **oscillates on its own schedule** (minutes to tens of minutes per phase), and nothing observed from the repo side reliably triggers the healthy phase. The deployed text's causal claim ("the burst itself flips the channel back") is unproven and should be softened in the follow-up; the practical advice it gives ("ask again; do not restart anything") remains the best available, since later asks demonstrably land in healthy phases.
- Per the workflow's guardrail, code changes stopped at this discovery; the recommended path is a fresh `/speckit.bug.assess` (below).

## Follow-ups

- **Re-assess with the oscillation model** — recommended next cycle: `/speckit.bug.assess` on the new facts (oscillating strip, no reliable trigger, 15-canary negative result). The candidate durable design, enabled by today's reachability probe: the sidecar container **cannot** reach OfficeMCP (`172.17.0.1:8888` and `host.docker.internal:8888` both refused — OfficeMCP binds Windows loopback only), so a **small WSL-side relay** (e.g. `172.17.0.1:8889 → 127.0.0.1:8888`) would let the sidecar talk to OfficeMCP directly — the foundation for a **gateway-independent office executor** immune to #148459 (the mechanical steps: probe → attach/launch → compose → verify, with the LLM retained only for planning).
- Soften the causal wording in the rule once the model settles
- Post the oscillation evidence (15-canary negative run, 71-minute persistence, phase timeline) to hermes-agent #148459
- The user-facing impact meanwhile: keep asking in the chat — healthy phases recur (08:15–08:20 delivered twice, composed the draft); never restart to "fix" it
