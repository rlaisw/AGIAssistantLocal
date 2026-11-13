# Bug Assessment: "open excel … type 12345 at cell B1" misrouted to the knowledge-base branch

- **Slug**: excel-with-filename-misrouted-to-general
- **Created**: 2026-11-13T03:13:24Z
- **Source**: pasted text (the agent's two-turn trace, ~03:10 UTC)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim, summarized)

> "it doesn't work at all" — "open excel with file name test1.xlsx, type 12345 at cell B1" was answered by the **General knowledge-base branch**, which (a) *fabricated* an `xls_write_v2` offer it doesn't have, then honestly corrected itself and told the user to "resend as a local task". The task never reached the Hermes Local Agent lane.

## Symptom

A textbook Excel local task routed to the wrong branch entirely — the user is told "it doesn't work" while the working fast path (`xls_write_v2` with `name: "test1.xlsx"`) exists on the Hermes lane.

## Reproduction

1. Send "open excel with file name test1.xlsx, type 12345 at cell B1" in the Chat UI (~03:10 UTC).
2. The **intent_router misclassifies it as `general`** — the General branch answers (ask/search/web tools only), first fabricating a tool offer, then correcting honestly and refusing.
3. No `hermes_file` classification → no Hermes-lane turn → zero audit rows for the request (verified: no xls-write rows in the 03:10-03:13 window for this conversation; the only nearby office row is an unrelated ppt-write at 03:13:57 from a different conversation).

## Suspected Code Paths

- `dify/AGIAssistant/AGI_Assistant.yml` `intent_router` node — the classifier. Two contributing causes visible:
  - **Model**: the router now runs `deepseek/deepseek-v4.1-flash` — the owner's model switch (via apply-model) applies to `intent_router` and `agentic_strategy`; the lane was tuned and verified on kimi (the 2026-11-05 pin covered the LANE nodes, and the router was re-classifying correctly on kimi through this morning).
  - **Examples**: the `hermes_file` class topic has examples like 'open Excel' but **no example of the Excel/write-cell-with-filename phrasing** — "open excel with file name X, type Y at cell B1" gives the flash router little to anchor on, and "file name" vocabulary leans knowledge-base-ish.
- The General branch's honest self-correction (the fabrication + retraction) behaved exactly as the honesty law demands — not a defect, but it confirms the branch genuinely lacks the tool.

## Root Cause Hypothesis

A classifier miss under a changed model: the router's `hermes_file` topic/description supports the request, but with `deepseek-v4.1-flash` doing the classifying and no matching example for the "open <app> with file name X, type Y at cell Z" shape, the request fell into `general`. The same phrasing family routed correctly earlier on the pre-switch router. Confidence: **high** for the misclassification (the trace shows the wrong branch answering); **medium** on the model-vs-examples split (both levers are cheap to fix together).

## Proposed Remediation

**Preferred** — three parts, all cheap:
1. **Strengthen the router's `hermes_file` topic/examples** (the highest-leverage, model-independent fix): add explicit examples for the Office-write shapes — "open excel with file name test1.xlsx, type 12345 at cell B1", "open Excel and write X in cell Y", "open Word and type X", "make a slide titled X" — and add "type/write VALUE at/into cell …" to the topic description so cell-write vocabulary is anchored.
2. **Re-verify the router model**: the flash model was chosen for chat answers; classification is a different job. Either (a) keep flash and rely on the strengthened examples (test first), or (b) pin `intent_router` back to kimi while keeping flash on `agentic_strategy` (a per-node split — the pin infrastructure already supports per-node models; the 2026-11-05 pin guards only the desktop LANE nodes).
3. **Live verify**: replay the exact prompt + the Word/Excel/PPT shapes through the chat and confirm the Hermes lane + `xls_write_v2` turns.

**Alternatives**: accept occasional misroutes — the complaint shows that's not acceptable.

**Files likely to change**:
- `dify/AGIAssistant/AGI_Assistant.yml` (intent_router classes; publish)
- possibly `src/agentic_rag_mcp/deploy/model_apply.py` (if the per-node split is chosen — add intent_router to CHAT_NODE_IDS or a dedicated ROUTER_MODEL)

**Tests to add or update**:
- DSL pin: the hermes_file class topic contains cell-write vocabulary + the with-filename example
- Live: the verbatim prompt routes to Hermes and completes via xls_write_v2 (audit rows present)

## Risks & Considerations

- Classifier changes are empirical — the strengthened examples must be live-tested with several phrasings (including the ones that already worked, to avoid regression to over-eager Hermes routing of genuine questions).
- The General branch's fabricated-then-retracted turn is a separate honesty observation: the first reply offered a nonexistent tool. The anti-fabrication guard caught it in the same turn (self-correction) — acceptable, but worth noting the flash model fabricated before checking; a strengthened router makes this path less traveled.

## Open Questions

- [NEEDS CLARIFICATION: keep `deepseek-v4.1-flash` on the router (with strengthened examples) or pin the router back to kimi? — the fix can test option (a) first and fall back to (b) if the live phrasing battery still misroutes]