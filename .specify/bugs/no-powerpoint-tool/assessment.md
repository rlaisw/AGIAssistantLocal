# Bug Assessment: "No PowerPoint tool available" — misroute at the time; a lane-root mismatch remains

- **Slug**: `no-powerpoint-tool`
- **Created**: 2026-11-03
- **Source**: pasted text (chat transcript from the deployed Chat UI)
- **Verdict**: valid — but the acute component (the misroute) is **already fixed** by the `office-routing-flake` remediation; the remaining defect is a product/expectation gap (the lane-root mismatch), plus a locked-in-by-test gap
- **Severity**: low

## Report (verbatim or summarized)

The user asked: *"create a powerpoint write 'Hello' — plain text, file name is test1, save to c:\temp\test"*. The answer came from the **general** branch: *"this branch of the chat has no PowerPoint/Office tool available to me, so I can't create test1.pptx or save it to c:\temp\test… To get it done, please send it as a local task on the branch that has the Hermes desktop/Office agent."* The agent's reasoning shows its genuine tool list (ask/search/sources/OneDrive/antv — no Hermes tools) and, notably, **no fabrication this time** — it honestly declined and redirected, exactly the behavior the `ppt-fail-change-background` anti-fabrication fix prescribes. The user's summary: "no PowerPoint tool available".

## Symptom

Observed (at the time of the transcript): a PowerPoint-file creation request with an explicit Windows save path was classified as **General**, where the general agent honestly reported having no Office tool — reading to the user as "the system has no PowerPoint capability". Expected: the prompt routes to the **Hermes Local Agent** and receives a real, actionable verdict. A second, deeper expectation gap: even correctly routed, the request's save location (`c:\temp\test`) sits **outside the Office work folder** (`C:\OfficeMCP`), so the honest outcome is always a containment refusal — the request as phrased can never succeed on any branch today.

## Reproduction

1. Send: *"create a powerpoint write 'Hello' — plain text, file name is test1, save to c:\temp\test"*
2. Live probes (2026-11-03, this assessment, two phrasing variants incl. the exact original): **both route to the Hermes Local Agent** — `User Input → AI LLM Router → PPT or General? → Hermes Local Agent`, and the agent proceeds to call `hermes_office_task`. **The transcript's misroute does not reproduce today.**
3. The subsequent office-gate containment block for `c:\temp\test` (outside the work folder) is deterministic and unit-covered (`tests/unit/test_office_gate.py::test_outside_work_folder_blocked`, and the "open C:\Other\book.xlsx" case) — no agent call is made for such tasks.
4. [NEEDS CLARIFICATION: whether the transcript's failing turn predates the classifier model restoration (2026-11-03 03:20 UTC, bug `office-routing-flake` fix) — its reasoning style matches the pre-restoration deepseek classifier era; if it postdates, the misroute was kimi variance that the probes didn't hit.]

## Suspected Code Paths

- `dify/AGIAssistant/AGI_Assistant.yml` — the `intent_router` classifier: at transcript time (deepseek-era or variance) "create a powerpoint … save to c:\temp\test" fell to General, between the `ppt_request` class (deck generation from a topic — rightly not matched) and the Hermes-local class (C:\ paths + Office writes — should have matched). Restored kimi-k3 + the hardened topic handle both probe phrasings correctly now.
- `src/agentic_rag_mcp/office_gate.py` — the work-folder containment (`C:\OfficeMCP` default): by design (spec 030 FR-003, owner-ratified), a `c:\temp` save location is refused with the root named; configurable via `office_root` in the `[hermes]` config section (`hermes_office_root`), a fact not surfaced in any refusal or doc.
- No fabrication involved: the general agent's honest refusal + redirect is the `ppt-fail-change-background` fix working as intended.

## Root Cause Hypothesis

**High confidence, layered.** (1) The transcript's acute failure — the misroute — is the same intermittent classifier failure class as `office-routing-flake`, already remediated (kimi-k3 restoration + topic hardening); the live probes confirm the routing now holds for this exact phrasing. (2) The underlying product gap is real and remains: the request spans two lane roots — Office authoring is confined to `C:\OfficeMCP` while the file lane's root is `C:\temp` — so *"a PowerPoint at c:\temp\test"* has no lane that can satisfy it, and every branch's honest answer is a dead end unless the user re-asks with a work-folder location or the owner widens `office_root`. (3) The general branch's refusal phrasing ("no PowerPoint/Office tool available") is honest but misleading about the system as a whole — its redirect line ("send it as a local task") is present and correct.

## Proposed Remediation

**Preferred** (all small; no sidecar code changes):
1. **Lock the routing with a battery probe**: add this phrasing class to `scenario_office_routing`'s probe list ("create a PowerPoint file named test1 with the text Hello and save it to C:\temp\test" → Hermes branch) so the fixed classification cannot regress silently — the same guard pattern that caught the previous two routing bugs.
2. **Surface the `office_root` knob**: extend the office gate's containment-refusal reason and the DEPLOY.md troubleshooting row to state that the work folder is owner-configurable (`office_root` under `[hermes]`), turning the dead-end refusal into an actionable one for the machine's owner.
3. **General-branch wording nit** (optional): its redirect already works; optionally have it add "…or ask the local agent to create it inside its work folder".

**Alternatives**:
- Owner sets `office_root = "C:\temp"` (config-only, no code) — makes the user's preferred location the work folder; trade-off: the sandbox then overlaps the file lane's root, and everything created there is treated as office-scope. Owner's call; not recommended by default.
- A spec amendment allowing user-specified save locations inside a trusted wider root — a real trust-boundary change; out of a bug fix's scope, spec 030's containment was an owner decision.

**Files likely to change**:
- `src/agentic_rag_mcp/deploy/battery.py` (routing probe addition)
- `src/agentic_rag_mcp/office_gate.py` (refusal reason mentions the configurable root — one sentence)
- `DEPLOY.md` (troubleshooting row)

**Tests to add or update**:
- `scenario_office_routing` gains the file-creation-with-path phrasing probe (asserts the Hermes branch)
- `test_office_gate.py`: the containment-reason assertion extended for the new "owner-configurable" sentence

## Risks & Considerations

- No code-level risk: routing already works; the changes are a battery probe, a refusal sentence, and docs.
- Changing `office_root` per the alternative moves the security sandbox — an owner decision, not a default.
- The timing clarification matters for the verdict: if the transcript postdates the model restoration, kimi variance persists for this phrasing class and the battery probe becomes more important, not less.

## Open Questions

- [NEEDS CLARIFICATION: did the transcript's failing turn occur before or after the classifier model restoration (2026-11-03 03:20 UTC)? Determines whether this was the already-fixed deepseek-era failure or a residual kimi variance.]
- [NEEDS CLARIFICATION: as the owner — is `C:\OfficeMCP` the right work folder, or would you prefer `office_root` pointed elsewhere (e.g. a Documents subfolder)? This decides whether the containment dead end for `c:\temp`-style requests stays by design.]
