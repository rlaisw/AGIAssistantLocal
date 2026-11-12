# Bug Assessment: skill_save drip-feed retries + mislabeled audit

- **Slug**: no-reusable-skill-on-file-do-not-open-word
- **Created**: 2026-11-12T06:28:52Z
- **Source**: pasted text (the Dify agent's full trace for "open MS Word, type Hello")
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim, condensed)

> "No reusable skill on file, so I'll do it directly — launching Word with the typing follow-up in one task."
> …then, after the task succeeded: *skill_save rejected (needs "tier")* → retry → *rejected (wants "workflow" not "steps")* → retry → *rejected (workflow step missing "tool")* → retry → *rejected (wants "service")* → retry.

## Symptom

The operational task itself succeeded (Word launched, "Hello" typed — correct lane choice, correct honesty). But the skill-loop's learning half cost **5 skill_save attempts in 10 seconds** (audit 06:25:11–21), each rejection surfacing a single missing field. The skill eventually saved (`launch_app_and_type_text` v1 in the store) — the end state is right, the path is wasteful and the audit trail lies about it.

## Reproduction

1. Ask for an operational task with no matching skill ("open MS Word, type Hello").
2. The agent solves it, then calls `skill_save` with a hand-built record.
3. Observed: 4 rejections, one field each, then a successful 5th attempt. Audit rows for the 4 rejections read `decision:"executed"` with `outcome` = the skill name and **no reason** (verified raw rows at 06:25:11/13/16/19/21).

## Suspected Code Paths

- `src/agentic_rag_mcp/skill_manager/store.py` `validate_skill()` — returns the **first** violation only (`return "rejected: tier …"` at each check) → every rejection teaches the agent exactly one field → drip-feed N round-trips per save.
- `src/agentic_rag_mcp/server.py` `skill_save` docstring + `dify/AGIAssistant/AGI_Assistant.yml` tool_description — the schema IS listed in prose, but with **no literal example record**; the agent's first attempt used wrong key names ("steps") — LLMs copy examples far more reliably than prose field lists.
- `src/agentic_rag_mcp/skill_manager/api.py` `_timed()` — always audits `decision="executed"` on return and drops the envelope's `reason` for blocked saves → rejections are recorded as executed with no cause; the audit contradicts the tool's own answer.

## Root Cause Hypothesis

Three compounding defects: (1) first-fail-only validation makes each rejection a one-bit lesson; (2) prose-only schema invites wrong key names on the first attempt; (3) the audit wrapper records a rejection as `executed` and discards its reason, so the trail cannot explain the retry storm. Confidence: **high** — the rejections, the timings, and the raw audit rows are all in hand.

## Proposed Remediation

**Preferred** — three small changes:
1. **Aggregate validation**: `validate_skill()` returns **all** violations as a list; the tool joins them into one message (capped, e.g. 6 items) — one round-trip to a correct record.
2. **Show the shape**: append a copy-paste EXAMPLE to the `skill_save` description (server docstring + DSL tool_description): `{"name":"launch_and_type","description":"…","tier":1,"workflow":[{"step":1,"tool":"hermes_launch_app","service":"hermes","params_template":{"task":"open {{application}} and type {{text}}"},"expect":"launched and typed"}]}`.
3. **Honest audit for saves**: blocked saves write `decision="blocked"` with the rejection reason (the envelope already carries it — `_timed` must pass it through instead of flattening to `executed`).

**Alternatives**: accept common aliases (`steps` → `workflow`) — rejected: loosening the boundary hides schema drift instead of teaching it.

**Files likely to change**:
- `src/agentic_rag_mcp/skill_manager/store.py` (validate_skill → list)
- `src/agentic_rag_mcp/skill_manager/api.py` (join reasons; audit decision/reason pass-through)
- `src/agentic_rag_mcp/server.py` (docstring example)
- `dify/AGIAssistant/AGI_Assistant.yml` (tool_description example; publish)
- `tests/unit/test_skill_store.py` (multi-violation pin)

**Tests to add or update**:
- A record with 4 violations returns **one** message naming all 4
- A rejected save writes an audit row with `decision="blocked"` and the reason present
- The tool description (both surfaces) contains the example record

## Risks & Considerations

- Aggregating violations must keep each message single-line and bounded (the answer relay pipes them).
- The audit change touches shared `_timed` (used by search/get/feedback too) — keep the change per-call (saves are the only data-validating op) or make `_timed` decision-aware everywhere (preferable: all tools audit the true decision).
- No schema loosening; existing stored skills stay valid (validation only becomes more informative).

## Open Questions

- None blocking. (The skill did save — no data repair needed.)