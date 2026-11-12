# Bug Assessment: "open MS Word, type hello" — whole process slow (~2 min)

- **Slug**: whole-process-is-slow-take-long-time-to-finish
- **Created**: 2026-11-12T07:07:30Z
- **Source**: pasted text (the agent's trace, conversation `a98c943d…`)
- **Verdict**: valid (performance + one design defect discovered)
- **Severity**: medium

## Report (verbatim, summarized)

> "whole process is slow, take long time to finish" — the user's "open ms word, then type hello" took ~2 minutes end-to-end. The trace shows: skill_search first (found `launch_app_and_type_text`, reusable=false) → manual solve via `hermes_launch_app` → 4 `skill_save` attempts (still fixing fields one at a time).

## Symptom

A simple launch-and-type request takes ~2 minutes. Expected: tens of seconds. The turn is correct (honest, gated, successful) — it is the **time** that is the complaint.

## Reproduction (measured, conversation `a98c943d…`, 2026-11-12)

| Step | Time | Cost |
|------|------|------|
| skill_search | 07:02:29 (1.0 s) | + 1 LLM reasoning round |
| **hermes_launch_app turn (launch Word + desktop typing)** | 07:02:31 → 07:04:20 = **109 s** | **the dominant cost — 85%+ of the turn** |
| skill_save ×4 (1 aggregated rejection, then 2 thrash rounds, then ok) | 07:04:22–29 (7 s wall) | + 4 LLM reasoning rounds |
| classifier + final-answer rounds | spread across | ~2 more rounds |

Total ≈ 2 minutes, of which the desktop-automation agent turn is ~109 s.

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_client.py` LAUNCH instructions + the launch lane (spec 029) — the typing followup rides the FULL Hermes-agent turn: LLM steps + WindowsMCP focus checks + **USER_CONTROL consent waits while the desktop is in use** + verification narration. This is the same double-LLM structure the browser lanes had before dynamic-lane v2 removed the middle hop (37–230 s → ~20–40 s).
- `src/agentic_rag_mcp/skill_manager/api.py` save/feedback — **design defect discovered: the trust loop can never bootstrap.** `reusable` requires success_count ≥ 3; success_count grows ONLY via `skill_feedback`, which the DSL calls only AFTER a replay; replay requires `reusable=true`. A fresh skill (0 successes) can never be auto-reused, so it never gains feedback, so it never becomes reusable — **deadlock**. Evidence: `launch_app_and_type_text` saved twice (yesterday + today), still `success_count=0`, every turn re-searches and re-solves manually, then re-saves.
- `hermes_launch_app` audit writes — **second finding: launch-app audit rows carry no `conversation_id`** (today's 07:04:20 row has empty cid), which is why the turn's audit looked missing in per-conversation queries.
- skill_save thrash: the aggregation fix works (attempt 1 reported tier+workflow together), but the agent still swapped fields between attempts (added `service`, dropped `tool`) — 3 extra rounds.

## Root Cause Hypothesis

The slowness is architectural, not a bug in a line: the desktop typing followup pays the full agent-in-the-loop price (~109 s measured), exactly the class the browser v2 revision eliminated for browsing. Secondary: the skill-trust bootstrap deadlock guarantees a wasted search round every turn (the loop can never learn), and the save thrash adds ~3 rounds. Confidence: **high** — every number is from the audit + gateway logs of the reported turn.

## Proposed Remediation

**Preferred** — tiered:
1. **The structural fix (own lifecycle, not this bug)**: a **single-hop desktop proxy** for the common followup primitives (focus window, send text/keys) — the v2 pattern applied to WindowsMCP: the Dify agent steers directly through sidecar proxy tools; consent (USER_CONTROL) still applies at WindowsMCP. Expected: the 109 s turn → ~20–40 s. Propose as its own spec (it is the "desktop v2", mirroring dynamic-lane v2).
2. **Fix the trust bootstrap deadlock (this bug's code fix)**: a same-name `skill_save` after a successful manual solve of the same intent increments `success_count` (a repeated manual solve IS evidence) — 3 repeats → reusable → the search round becomes useful instead of dead weight, and replays get honest feedback.
3. **Quick trims (same change window)**: skill_save description wording — "COPY the example record; do not build fields one at a time" (kills the thrash); `hermes_launch_app` audit rows carry `conversation_id` (the observability gap found twice today).

**Alternatives**: accept the 109 s desktop turns as designed (spec 029 consent-gated) and only fix the deadlock + trims — leaves the dominant cost untouched.

**Files likely to change** (items 2–3):
- `src/agentic_rag_mcp/skill_manager/api.py` (bootstrap increment)
- `src/agentic_rag_mcp/server.py` (launch audit cid; save-description wording)
- `tests/unit/test_skill_feedback.py`, `tests/unit/test_hermes_launch_gate.py` or the launch-tool tests (pins)

**Tests to add or update**:
- Same-name save after success increments success_count; 3rd repeat → reusable=true
- launch-app audit row carries the conversation_id
- (desktop v2 proxy: its own lifecycle's tests)

## Risks & Considerations

- The bootstrap increment must count only GENUINE repeats (the DSL's manual-solve-then-save flow) — a same-name save from a different intent must not inflate trust; guard by requiring the save to follow a successful solve in the same conversation (as the DSL already mandates).
- The desktop v2 proxy touches the consent surface — needs the same adversarial care as the browser v2 (untrusted-content posture, honest envelopes).
- Timing expectations: even after v2, launch+typing stays consent-gated (~tens of seconds while the desktop is in use).

## Open Questions

- None blocking. The desktop v2 proxy is a scope decision for the owner (say "start the desktop v2 spec" separately).