# Bug Assessment: minutes of post-task wait for the final report — loop rounds the rules exempt, at ~60–100 s per agent round

- **Slug**: after-the-task-was-done-final-report-result-wait-long-time
- **Created**: 2026-11-14T05:55:00+00:00
- **Source**: pasted text ("after the task was done, final report result wait long time")
- **Verdict**: valid — measured live from today's audit trail; both components confirmed with numbers
- **Severity**: medium — honest, correct results, no data risk; but every v2 task turn ends in a user-visible multi-minute wait after seconds-long tool work, on the exact class of turns the fast-path work was built to make instant

## Report (verbatim or summarized)

> "after the task was done, final report result wait long time"

No URL was supplied with the report.

## Symptom

The task's visible work completes in seconds (browser reads 2.1 s, PPT write 1.8 s — both measured today), but the final answer text takes minutes to arrive in the chat: the audit trail shows the conversation continuing to run loop rounds more than 2½ minutes after the tool work was done. Expected: the turn reports within a few seconds of tool completion on the v2 fast path.

## Reproduction

Measured from today's live turns (audit.jsonl, 2026-11-14 UTC):

1. **05:36:33–05:36:36** (conv `9402426f`): the turn's actual work — `browser_read_v2` ×2 — completes in **2.1 s** total.
2. **05:38:16**: `skill_search` fires — **100 s** of agent deliberation after the reads finished. The v2 fast-path exemption ("browser v2 single-hop tools … SKIP the skill loop ENTIRELY: no skill_search before, no skill_save after", published 2026-11-13) says this round must not exist.
3. **05:39:17**: `skill_save` fires — another **~60 s** round later. The exemption's "no skill_save after" clause violated too. The turn's final answer can only come after at least one more relay round plus the answer node.
4. **05:11:21–05:11:28** (conv `aa4fd730`): same shape on the office lane — `skill_search` (1.2 s tool) + `ppt_write_v2` (1.8 s tool); the search round again precedes an exempt v2 op.
5. **Per-round model cost baseline (live replay, this assessment)**: a trivial General-lane question ("hello, just say hi back") → first visible answer text at **11.3 s**, message_end 11.7 s — ~5–6 s per LLM node on a small instruction set. The Hermes-lane agent rounds measured above cost **~60–100 s each** (thinking model + the now-large lane instruction set), and the office-task row from 04:56 shows the same scale (18.2 s single gap inside one tool call's stream).
6. Net: on a fully-working v2 turn the user watches the desktop effect at ~2 s, then waits through one-or-more ~60–100 s relay/loop rounds plus the answer node — minutes of "task done, no report" — exactly the reported symptom.

## Suspected Code Paths

- `dify/AGIAssistant/AGI_Assistant.yml:1422-1425` — the `hermes_agent` node prompt: the V2 FAST-PATH EXEMPTION rule and the BROWSER LANES "no detours" rule are instruction-level only; today's turns prove the agent does not reliably obey them (the same instruction-vs-behavior gap class as the browser-action routing bug and the pre-router decision).
- `src/agentic_rag_mcp/skill_manager/api.py` / `server.py` (`skill_search`, `skill_save` tools) — the loop tools execute unconditionally: nothing structural stops them during a v2-exempt turn; the gate style for structural enforcement (FR-005, never-lists, followup refusals) already exists in this codebase.
- `src/agentic_rag_mcp/office_lanes/proxy.py`, `browser_lanes/proxy.py`, `server.py` (the 7 exempt v2 tools) — the natural place to stamp a conversation-scoped "v2-exempt turn" marker on completion.
- The parked workstream items this measured evidence feeds: "lighter steering model for Hermes lane node" and the "deterministic sidecar executor" (owner's call, `.specify` work state) — the ~60–100 s/round cost is the steering-model + instruction-payload cost, not tool cost.

## Root Cause Hypothesis

**High confidence, two stacked components.** (1) *Behavioral*: the v2 fast-path exemption is a prompt rule, and the agent overrides it — today it ran skill_search + skill_save around exempt v2 ops, adding ~2 rounds the rule forbids; instruction-level rules of this shape have repeatedly needed structural enforcement in this project (launch gate, run gate, honesty check, pre-router pending). (2) *Economic*: each hermes_agent iteration costs ~60–100 s with the current UI-selected thinking model over the large lane instruction set (vs ~5–6 s/node measured on the General path), so every post-tool round the turn takes — exempt or not, relay plus answer — lands as a minute-scale wait after the work is visibly done. The exemption violations multiply the wait; the per-round cost sets its floor.

## Proposed Remediation

**Preferred** (two parts, the first is code, the second is the parked owner decision now backed by data):
1. *Structural loop exemption (sidecar)*: stamp a conversation-scoped **v2-exempt-turn** marker when any of the 7 exempt v2 tools completes; `skill_search` and `skill_save`, when called with that marker active, return an honest advisory envelope — `loop-exempt turn (v2 fast path): skip the skill loop and report` — instead of executing. The agent receives the structural answer in the tool result and proceeds to the report; the two forbidden rounds disappear regardless of instruction adherence. The DSL rule stays as documentation of intent.
2. *Steering-model cost (owner's parked call)*: adopt the lighter steering model for the `hermes_agent` node (non-reasoning or smaller model for lane iterations). Today's measurements are the case: ~60–100 s/round × (relay + any loop + answer-path rounds) is the entire symptom; the General-path baseline (11.3 s for a full trivial turn) shows the platform is not the bottleneck.

**Alternatives**:
- Deterministic sidecar executor for mechanical flows (the owner offered to draft the spec) — the structural endgame, removes the LLM from the mechanical loop entirely; bigger scope than this bug.
- Tighten the DSL wording again — rejected as the sole fix: this is the second wording round for the same clause and today's turns show wording alone does not hold.

**Files likely to change**:
- `src/agentic_rag_mcp/server.py` and/or `src/agentic_rag_mcp/skill_manager/api.py` (exempt-marker stamp + advisory refusal in the two loop tools)
- the 7 v2 tool completion paths (office_lanes/proxy.py, browser_lanes/proxy.py, server.py wrappers) to set the marker
- `tests/unit/` (pins: marker set by each exempt tool; both loop tools honor it; non-exempt lanes unaffected)

**Tests to add or update**:
- exempt tool completes → conversation marked; `skill_search`/`skill_save` during the marker → the advisory envelope, no store read/write, audit row with the refusal decision.
- non-exempt flows (hermes_* lanes, scripted runs) keep the full loop — the marker only comes from the 7 v2 tools.
- envelope text pin (the honest skip note).

## Risks & Considerations

- The marker must be conversation-scoped and turn-fresh (a later non-v2 task in the same conversation must keep its loop) — a simple per-conversation "last-exempt-op" timestamp or per-turn reset on the first non-exempt tool is enough.
- Learning loss: exempt turns no longer record skills — that is the published intent (they are deterministic flows), already accepted with the 2026-11-13 exemption; the advisory envelope keeps the agent informed rather than silently blocked.
- The steering-model change is an owner decision with quality trade-offs (deliberation depth vs latency) — this assessment supplies the numbers, not the decision.
- Sidecar rebuild + DSL publish not conflicting: part 1 is sidecar-only (no tool count change); part 2 is a Dify model-apply change.

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the mechanism is fully measured. The one owner-input item: whether to take the lighter steering-model decision now (part 2) or keep it parked while part 1 lands.]
