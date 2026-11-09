# Bug Fix: anti-fabrication gate on the Hermes lane — prompt law + structural honesty-check node, published live

- **Slug**: `cannot-open-a-new-tab-on-current-chrome-browse`
- **Fixed**: 2026-11-09
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Two layers went live at 08:01 UTC: the `hermes_agent` instruction gained the ANTI-FABRICATION LAW (a local-task request is never answered without a hermes_\* tool call in THIS turn; earlier turns' results are not evidence), and a new `honesty_check` code node now sits between `hermes_agent` and the shared `answer` node — it inspects the agent node's structured output (`text` + `json` iterations) and replaces any answer that claims local-agent action (completion phrases, key presses, snapshots, LAUNCH attestations, tool names) **without any tool call this turn** with a fixed honest notice. A fabrication can no longer reach the user even if kimi-k3 narrates one.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | (1) ANTI-FABRICATION LAW bullet inserted in the `hermes_agent` instruction; (2) new `honesty_check` code node (JS, `version: '2'`, inputs `answer ← hermes_agent.text`, `items ← hermes_agent.json`, output `result: string`); (3) edge `hermes_agent→answer` replaced by `hermes_agent→honesty_check→answer` (ids `hermes-agent-honesty`, `honesty-answer`); (4) shared answer template switched `{{#hermes_agent.text#}}` → `{{#honesty_check.result#}}` |

No python changed — the sidecar, gates, and audit were provably not implicated (the assessment's forensics: all fabrication happened relay-side with zero sidecar contact).

## Diff Highlights (optional)

```yaml
# the gate's core logic (code node)
var claims = /local agent (completed|did|was)|the agent (sent|pressed|opened|typed|launched|focused|confirmed|handled)|confirmed (by |with )?(a |the )?(snapshot|it)|LAUNCH: ?(SUCCESS|FAILED)|hermes_(launch_app|office_task|file_task|cancel_turn)/i;
if (!called && claims.test(String(answer))) {
  return {result: 'Honesty check: the local agent was NOT called for this request, so nothing was done on your computer. The drafted reply described actions that never ran and was blocked by the honesty check. Please send the request again.'};
}
return {result: answer};
# "called" = any iteration item with non-empty tool_input or a tool_response
```

## Tests Added or Updated

- No python tests (DSL-side fix; the assessment's contract). The gate logic was verified directly against the three RECORDED cases from the incident (node v22 harness):
  - fabricated-new-tab turn (run `27d828a5`) → **BLOCKED (replaced)**
  - real-japan turn (run `86f4497d`, real tool calls) → **PASSED THROUGH**
  - real-hongkong turn (run `42f2c1fb`, real tool calls) → **PASSED THROUGH**

## Local Verification

- DSL structure: YAML parses; 12 nodes / 14 edges; edge endpoints all exist; the answer template and node wiring verified programmatically.
- Publish safety: exported the **live** app before pushing and compared against the committed yml — node count, edge count, hermes instruction, and answer template all matched HEAD (no live-only drift would be lost), then pushed the edited workflow as draft and published (established `update_workflow_draft` + `publish` cycle, app `194e1edf`).
- Live graph: Postgres `workflows` — the new version `2026-11-09 08:01:07` carries the law, the node, the template, and the edges (`t`/`t`/`t`/`t`); the prior version (04:03) carries none.
- Live smoke through the published chatflow (the code node's `hermes_agent.json` selector was the one runtime risk): blocking chat probe `"delete the folder C:\temp\bench-honesty"` → routed to the Hermes lane, the relay **made a real tool call**, the gate blocked the delete, the honest refusal flowed through `honesty_check` to the answer with **no code-node error**, and the audit logged `blocked unsupported` at 08:01:39 — the full new path is exercised and healthy.

## Deviations from Assessment

- None. Both proposed layers (prompt law + structural code node) were applied as specified. The publish used the established full-graph `update_workflow_draft` push (the same mechanism `python -m agentic_rag_mcp.deploy chatflow` uses) rather than an instruction-only patch — same tooling, not a scope change. (One script-side stumble on the way: the first publish attempt called `DeployConfig()` directly instead of `resolve(load_config())` and hit an empty-credential 422 — fixed and re-run; no system state was touched by the failed attempt.)

## Follow-ups

- `/speckit.bug.test` live verification: ask "open a new tab in chrome" in a **fresh conversation** — it must produce a real `hermes_launch_app` call (audit entry + timing) and an honest verdict; optionally re-ask inside the poisoned conversation `1036904c` — its history contains three fake successes, so if kimi fabricates again the user should now see the fixed honesty notice instead of a lie.
- The user should **delete conversation `1036904c`** (spec 015 delete) once satisfied, so future turns don't inherit the fabricated context.
- The `claims` regex is deliberately narrow (completion phrases, LAUNCH attestations, tool names); if a future fabrication uses novel phrasing, widen it — but never make the node replace answers that lack claimed action (ask-backs/refusals must pass through verbatim).
- Fold the DSL change into the next lifecycle commit together with the timing-instrumentation work.
