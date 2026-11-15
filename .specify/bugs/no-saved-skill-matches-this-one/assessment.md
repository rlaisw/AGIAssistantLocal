# Bug Assessment: "No saved skill matches this one" — the honest no-match relay, working as designed; the rough edge is the agent's phrasing, not the machinery

- **Slug**: no-saved-skill-matches-this-one
- **Created**: 2026-11-15T02:48:00+00:00
- **Source**: pasted text ("No saved skill matches this one")
- **Verdict**: invalid / not a bug — the skill loop behaved exactly per spec 036 (search ran, matches came back with `reusable: false` — the trust gate requires rate > 0.80 AND ≥ 3 successes — so the agent solved manually, as designed). The report is the agent's honest relay of that outcome; the only genuinely rough part is the phrasing, which reads like a failure when it is the designed fallback.
- **Severity**: low — no functional impact, no data risk; a cosmetic relay-quality note

## Report (verbatim or summarized)

> "No saved skill matches this one"

No URL was supplied with the report.

## Symptom

A chat turn relays "No saved skill matches this one", which reads like a search failure. What actually happens: the skill search DOES find a candidate, but its trust gate (spec 036: reusable = rate > 0.80 AND ≥ 3 successes) correctly marks it not-reusable — a fresh skill with 0 successes can never auto-apply — so the loop's designed "solve manually" path runs, and the agent's relay describes that as a no-match.

## Reproduction

From the live audit trail + fresh probes (2026-11-15 ~02:2x–02:40):

1. "open device manager" → `skill-search executed` (found `open_device_manager`) — the skill was saved by the replay earlier today (after the launch lane's fumbled 44 s attempt, hence `success_rate: 0.0`, `sample: 0` from its failed origin); not reusable → manual solve (the applet fast path, 0.8 s ✓).
2. "list all installed programs on windows" → `skill-search executed` (found `launch_application_by_name`, `success_rate: 0.0, sample: 0`) → manual solve via `run-powershell` (the genuine `Get-ItemProperty … Uninstall` listing ✓).
3. Both probes re-run live during this assessment return `found: true` with `reusable: false` — the machinery is correct; the trust gate is holding exactly as spec 036 requires (skills earn reusability through the feedback loop, they never start reusable).

## Suspected Code Paths

- `src/agentic_rag_mcp/skill_manager/{api,intent,store}.py` — the search/trust machinery: correct behavior confirmed live (found=true, reusable=false for unproven skills).
- `dify/AGIAssistant/AGI_Assistant.yml` — the SKILL LOOP instruction: "If no skill matches or none is reusable: solve manually…" — the instruction is correct; the agent's user-facing phrasing ("No saved skill matches this one") conflates "found but not yet reusable" with "no match".

## Root Cause Hypothesis

**High confidence: not a defect.** The reported sentence is the agent's paraphrase of the designed fallback (a search hit whose trust gate is not yet met). Two adjacent real observations from the same window are worth separating from this report: (a) the **skill-save schema thrash** (three blocked attempts before the save landed — the agent's first drafts omitted required fields; the validation worked, the retries cost seconds) and (b) the skill `open_device_manager` was **born from a failed attempt** (the launch-lane fumble), so it starts at 0.0 success — the feedback loop will either improve it through future uses or it stays non-reusable, both correct.

## Proposed Remediation

**Preferred**: none for the machinery — the loop is spec-correct. If the phrasing bothers you, a one-line DSL wording improvement ("When a skill is found but not yet reusable, say: 'I found a saved skill for this but it hasn't proven itself yet — solving manually'" instead of "no saved skill matches") would make the relay precise. The two genuine follow-ups: the skill-save schema-thrash note (a tool-description field hint could save the agent's first drafts) and letting the feedback loop run its course on the young skills.

**Alternatives**: lowering the trust gate — rejected (spec 036's whole point: skills earn reuse; a 0-success skill auto-applying would be the bug).

**Files likely to change** (only if the wording fix is wanted):
- `dify/AGIAssistant/AGI_Assistant.yml` (one sentence in the SKILL LOOP block)

**Tests to add or update**: none — no code behavior changes; the trust-gate pins already exist (`test_skill_trust.py`).

## Risks & Considerations

- None functional — this is relay phrasing. The trust gate, the honest no-match handling, and the manual-solve fallback are all live-proven and pinned.

## Open Questions

- [NEEDS CLARIFICATION: none blocking — verified live on both reported turns. If you want the one-line relay-wording improvement, say so at `/speckit.bug.fix`.]
