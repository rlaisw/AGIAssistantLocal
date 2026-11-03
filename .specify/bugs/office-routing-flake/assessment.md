# Bug Assessment: Office-task prompts intermittently misroute to the general lane on first try

- **Slug**: `office-routing-flake`
- **Created**: 2026-11-02
- **Source**: pasted text (chat transcript from the deployed Chat UI)
- **Verdict**: valid — intermittent, root cause identified with high confidence
- **Severity**: high

## Report (verbatim or summarized)

The user asked in chat: *"Insert a row at the top and add the header 'Height' in A1."* in the existing workbook `C:\OfficeMCP\Employee_Heights.xlsx` — and it **never executed** ("no response"/refusal). The transcript shows the failing turns answered by the **general** agent (labeled Deepseek-v4.1-flash), which honestly reported it had no Office tool ("I don't have a hermes_office_task tool… My tools are: current_time, amap_geocode, amap_weather, search, tavily_search, antv…" — a **confabulated** tool list; amap/tavily/mindmap are not in this stack's 26-tool surface). A later prompt in the same conversation — *"add a column B, generate 10 records for weight in Kg"* — **routed correctly** and executed via Excel COM; its agent report proves the earlier instruction never ran: *"column A has no header row — the 10 heights occupy A1:A10"*. The user's summary: "cannot modify a current file in FIRST-TIME try".

## Symptom

Office-edit prompts (especially terse ones like *"insert a row at the top and add the header 'Height' in A1"*) intermittently classify as **General** instead of **Hermes local task** on the first try, so the general agent — which has no Office tool — honestly refuses and the task never runs; rephrased retries sometimes route correctly and the task then succeeds. Expected: every Office-task prompt routes to the Hermes Local Agent's `hermes_office_task` and executes.

## Reproduction

1. In the Chat UI, send: *"Insert a row at the top and add the header 'Height' in A1."* (workbook context optional).
2. Observed (user's transcript): the answer comes from the general lane refusing for lack of the Office tool; no row is inserted; `Employee_Heights.xlsx` is unchanged (verified by the later agent report: A1 still holds `170`).
3. Live probes today (2026-11-02, bug-assessment session, fresh conversations): the **same phrasing routed correctly twice** (`PPT or General?` → *Hermes Local Agent* → `hermes_office_task` called) — the misroute is **intermittent**, not deterministic.
4. [NEEDS CLARIFICATION: how many first-try failures the user hit and at what times — needed to estimate the flake rate; the transcript shows two refusal turns.]

## Suspected Code Paths

- `dify/AGIAssistant/AGI_Assistant.yml` — the `intent_router` node ("PPT or General?"): its model is **deepseek/deepseek-v4.1-flash** and its Hermes-local topic/instruction examples cover writing cells ("put 12345 in cell A1") but **not row/sheet-structure edits** ("insert a row at the top", "add a header") — the exact phrasing that flaked.
- The same file's model fields: `intent_router`, `agentic_strategy`, and `hermes_agent` all currently specify `deepseek/deepseek-v4.1-flash` — an **uncommitted working-tree change**; at spec 029's commit (`77a5060`) these were `moonshotai/kimi-k3`, the model the lane routing was tuned and verified on.
- The general agent's honest refusal (correct behavior given its tool list) is what makes a misroute feel like "the feature is broken": no channel back to the Office lane exists once misrouted.

## Root Cause Hypothesis

**High confidence.** Two stacked causes: (1) the routing classifier was silently swapped from `kimi-k3` to the weaker `deepseek-v4.1-flash` in the uncommitted DSL working tree (present in the published live app since spec 030's deploys), raising classification variance on terse local-task phrasings; (2) the classifier prompt's Office examples never covered row/sheet-structure edits, leaving "insert a row at the top and add the header…" outside every example pattern. The result is an intermittent first-try misroute to General; spec 029 hit the identical failure mode for launch prompts until its classifier was hardened. The user's transcript also confirms the general model (deepseek-flash) confabulates tool lists in its reasoning, which made the refusals more confusing ("amap_geocode/tavily_search" do not exist in this stack).

## Proposed Remediation

**Preferred** (all three together; each is small):
1. **Harden the classifier prompt** (the proven 029 fix): extend the Hermes-local topic/instruction with structure-edit phrasing — "editing document structure — insert/delete rows or columns, add or rename headers (e.g. 'insert a row at the top', 'add the header Height in A1', 'add a column B')" and state that these are 'Hermes local task', NOT 'General'.
2. **Add automated routing probes** to `src/agentic_rag_mcp/deploy/battery.py`: a chat-level scenario asserting that Office-edit phrasings (insert-row, add-header, add-column) land on the Hermes branch — the only guard against this class of regression recurring (all routing checks so far were manual probes).
3. **Decide the classifier model** with the owner: either restore `moonshotai/kimi-k3` for the `intent_router` (the model the lanes were verified on) or keep `deepseek-v4.1-flash` and rely on the hardened prompt — and record the decision in the DSL's commit message so silent model swaps stop slipping in uncommitted.

**Alternatives**:
- Deterministic keyword pre-routing before the LLM classifier (DSL condition nodes): eliminates the flake class entirely but adds topology and maintenance; defer unless hardening proves insufficient.
- General-lane refusal UX: instruct the general agent to end refusals with "this looks like a local computer task — please resend it", turning misroutes into recoverable retries. Cheap, helpful, but does not fix the routing.

**Files likely to change**:
- `dify/AGIAssistant/AGI_Assistant.yml` (classifier topic/instruction; optionally the `intent_router` model field)
- `src/agentic_rag_mcp/deploy/battery.py` (routing-probe scenario)
- `specs/…` none required (this is a bug fix, not a spec change)

**Tests to add or update**:
- Battery routing probe: send the flaky phrasings through the chatflow API, assert the Hermes branch (and, where harmless, `hermes_office_task` invocation); register in the scenario list.
- Unit: none — the gate and tool are unaffected; the bug lives in the DSL layer the battery must now cover.

## Risks & Considerations

- Classifier prompt changes affect ALL routing (deck/file/launch/office/general) — the full battery must re-run green after republishing.
- The model fields sit in the **uncommitted working tree** together with the entire 030 feature — the commit (T022) will either bless the deepseek swap or revert it; that decision should be explicit, not accidental.
- Routing probes make the battery dependent on chatflow availability (it already is via chat-journey) and add ~1–2 min per run.
- Prompt bloat can degrade classification; keep the added examples tight.

## Open Questions

- [NEEDS CLARIFICATION: the model swap (kimi-k3 → deepseek-v4.1-flash on intent_router/agentic_strategy/hermes_agent) is an uncommitted working-tree change made outside this session — was it deliberate (cost/speed)? This decides remediation step 3.]
- [NEEDS CLARIFICATION: how often the first-try failure occurred for the user (transcript shows two refusals) and whether any were before spec 030's chatflow was first published today, when office prompts correctly had no office tool yet.]
