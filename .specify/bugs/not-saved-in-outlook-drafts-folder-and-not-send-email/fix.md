# Bug Fix: Office email compose silently fabricated — pin all four lane nodes to kimi-k3

- **Slug**: `not-saved-in-outlook-drafts-folder-and-not-send-email`
- **Fixed**: 2026-11-05T05:50+00:00
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Per the owner's Option B decision, the four lane LLM nodes (`intent_router`, `agentic_strategy`, `ppt_master`, `hermes_agent`) are **pinned to `moonshotai/kimi-k3`** in both the patch tool and the live published chatflow — the model dropdown and `apply-model` CLI keep working but can no longer swap a lane node, so the blanket deepseek swap that caused the fabrication is structurally impossible. An anti-fabrication audit guard was added to the battery.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/deploy/model_apply.py` | modified | `PINNED_MODEL = "moonshotai/kimi-k3"`; `patch_dsl` pins the four lane nodes and **ignores** `model_id`; report evidence names the pin and the ignored selection; publish evidence says "pinned" |
| `dify/AGIAssistant/AGI_Assistant.yml` | modified (via apply cycle) | all four lane nodes republished as `moonshotai/kimi-k3` (verified by re-parsing the artifact) |
| `tests/unit/test_deploy_model_apply.py` | modified | pin test: requesting `deepseek/deepseek-v4.1-flash` still writes kimi-k3 on all four nodes |
| `src/agentic_rag_mcp/deploy/battery.py` | modified | A1 audit-trail guard: office-task audit entries must grow across the O3/O4 email steps — a fabricated verdict (no call, no audit line) fails the battery |

## Diff Highlights (optional)

```python
# model_apply.py
PINNED_MODEL = "moonshotai/kimi-k3"          # owner decision 2026-11-05 (Option B)
MAIN_NODE_IDS = ("intent_router", "agentic_strategy", "ppt_master", "hermes_agent")
...
for nid in MAIN_NODE_IDS:
    ...
    block = _model_block(PINNED_MODEL)        # was: _model_block(model_id)
```

## Tests Added or Updated

- `tests/unit/test_deploy_model_apply.py::test_pins_the_four_lane_nodes_regardless_of_selection` — pins the pin: any requested model still writes `PINNED_MODEL` on all four lane nodes (7 passed)
- `battery.py` A1 audit-trail check — added, not yet run (see Deviations)

## Local Verification

- `pytest tests/unit/test_deploy_model_apply.py` → **7 passed**
- `apply-model deepseek/deepseek-v4.1-flash` (deliberately wrong selection) → `patch: pinned model=moonshotai/kimi-k3 … (selection 'deepseek/deepseek-v4.1-flash' ignored)`, `publish: pinned moonshotai/kimi-k3`, `ok: 5 steps`
- Artifact re-parse: all four nodes → `moonshotai/kimi-k3 (langgenius/openrouter/openrouter)`
- **Live anti-fabrication proof (the core fix)**: three consecutive email-compose turns through the Chat UI each **really invoked `hermes_office_task`** — audit entries at 05:38:59, 05:39:50, 05:41:05 (executed/error), honest step reports, no fabricated success. Under deepseek (pre-fix) the same request produced a full fake "email sent" story with zero audit entries.

## Deviations from Assessment

**E2E compose verification is blocked by the separate, known upstream channel defect.** The battery A1 guard was not run, and no draft could actually be composed, because the gateway→OfficeMCP channel is currently dropping RunPython arguments on **fresh sessions** (hermes-agent issue [#148459], lifecycles `officemcp-connection-error` / `outlook-fail-send-email`). Recovery (mcp remove/add + gateway restart + full OfficeMCP service restart) did **not** clear it today — previously it always did. Word/Excel/PPT office-tasks executed normally through the same channel at 05:18–05:22, and the transport patch (`sse_read_timeout 900`) is live (the gateway runs the editable install), so this is a new, harsher manifestation upstream, not a local regression from this fix. One additional observation for the upstream issue: under repeated-failure context pressure, kimi's 4th attempt narrated a "fourth failure" **without calling the tool** (no audit entry) — models fabricate under channel-outage pressure regardless of pinning; the audit guard is the real defense.

## Follow-ups

- Re-run `/speckit.bug.test slug=not-saved-in-outlook-drafts-folder-and-not-send-email` (battery A1 + e2e email compose) once the #148459 channel recovers
- Comment today's data point on hermes-agent issue #148459: arg-drop now reproduces **immediately on fresh sessions** (was: after hours of uptime), and recovery no longer clears it
- Optional UX follow-up (out of scope): the model dropdown now always reports kimi-k3 via `/api/models/current`; consider labeling it "pinned" in the UI, or retiring the dropdown (owner's call)
- The two fabricated answers from 05:23/05:24 remain in Dify conversation history as false "email sent" claims — the user knows no email left the machine