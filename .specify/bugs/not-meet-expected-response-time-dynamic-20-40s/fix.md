# Bug Fix: Dynamic response time — routing flip (search-and-report -> v2) + relay hardening

- **Slug**: not-meet-expected-response-time-dynamic-20-40s
- **Fixed**: 2026-11-12T03:24:31Z
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Search-and-report intents now route to the v2 dynamic tools (navigate+read, deterministic, consent-free) instead of the scripted lane whose agent-turn delivery stalled 325s on USER_CONTROL; the skill_search round is skipped for this deterministic shape (one less LLM round); and the scripted relay directive now demands the script's COMPLETE JSON output (fixing the "emitted 1 of 2 steps" aborts for the flows that stay scripted).

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/browser_lanes/routing_gate.py` | the 5 search-and-report patterns removed from `_REPEATABLE` | search shapes fall through to the dynamic (v2) lane; real multi-step flows (login+download, scrapes) stay scripted |
| `dify/AGIAssistant/AGI_Assistant.yml` | the search-and-report rule now names the v2 path: derive URL -> browser_navigate_v2 -> browser_read_v2 -> report; SKILL-SEARCH SKIPPED for this shape; published | 2-3 tool calls total, no detours |
| `src/agentic_rag_mcp/server.py` | scripted relay directive hardened: "copy the COMPLETE output: EVERY JSON step line, in order, unchanged" | the 1-of-2-steps relay bug (2 aborts measured) |
| `tests/unit/test_browser_routing_gate.py` | 5 pins flipped: search shapes (incl. the verbatim weather prompt) -> dynamic | scripted pins remain for multi-step flows |

## Local Verification

- 573 unit tests green; ruff clean; 43 tools rebuilt; chatflow published.
- Gate behavior: search/news/weather/look-up -> dynamic; login+download -> scripted (verified live in the shell).
- Baseline for the re-benchmark: the previous turn measured skill_search 1.0s + scripted-detour 21.1s (always-failing) + navigate 1.3s + read 0.5s + ~5 kimi rounds ≈ 1.5-2.5 min. The flip removes the scripted detour AND one round (skill_search skip); expected ≈ 25-45s.

## Deviations from Assessment

None — the preferred remediation applied exactly (routing flip + relay hardening). The skill_search skip was flagged in the benchmark analysis as an optional round-cutter; included because the owner approved the benchmark expectation fix.

## Follow-ups

- Re-benchmark with the verbatim prompt in the Chat UI; the audit rows give the step timings.
- Watch the scripted lane's relay fix on its next real multi-step use (login+download class).
