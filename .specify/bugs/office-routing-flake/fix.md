# Bug Fix: Office-task prompts intermittently misroute to the general lane on first try

- **Slug**: `office-routing-flake`
- **Fixed**: 2026-11-02
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The routing classifier's model was restored to `moonshotai/kimi-k3` (the model the Hermes lanes were tuned and verified on — the silent uncommitted swap to `deepseek-v4.1-flash` was the owner-reverted cause), the classifier prompt now explicitly covers document-**structure** edits (insert rows/columns, add headers — the phrasing that flaked), and a new automated **office-routing battery scenario** guards the routing so this class cannot regress silently. Live verification: both previously-flaky phrasings route to the Hermes branch; adjacent lanes (deck, launch) unaffected.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | `intent_router` model restored to `moonshotai/kimi-k3` (owner decision, 2026-11-02); classifier topic + instruction extended with structure-edit phrasing ("insert a row at the top", "add the header Height in A1", "add a column B") — the exact prompt shapes that misrouted |
| `src/agentic_rag_mcp/deploy/battery.py` | added scenario | `scenario_office_routing`: chat-level probe asserting insert-row/add-column phrasings land on the **Hermes Local Agent** branch (the routing regression guard that was missing when the bug shipped) |
| `tests/contract/test_deploy_cli.py` | modified | `CONTRACT_SCENARIOS` gains `office-routing` (15-scenario registry) |
| `DEPLOY.md` | modified | battery count line 14 → 15 scenarios with the routing-guard note |

## Diff Highlights (optional)

```diff
  # intent_router model — the routing-critical node (owner: restore the proven classifier)
- model: deepseek/deepseek-v4.1-flash
+ model: moonshotai/kimi-k3
  # classifier instruction — structure edits were outside every example pattern
+ ...including structure edits such as inserting or deleting rows or columns and
+ adding or renaming headers ('insert a row at the top', 'add the header Height in A1',
+ 'add a column B')... are 'Hermes local task', NOT 'General'.
```

## Tests Added or Updated

- `scenario_office_routing` (battery) — sends the two flaky phrasings through the live chatflow and asserts the **Hermes Local Agent** node runs (any Agentic Strategy node = MISROUTE, fails the scenario)
- `tests/contract/test_deploy_cli.py::test_registry_matches_contract` — pins the 15-scenario registry including the new guard

## Local Verification

- Commands: `deploy chatflow` → published; `pytest tests/contract/test_deploy_cli.py` → **10 passed**; live `scenario_office_routing` → **PASS (50 s)**: `'Insert a row at the top and add the…' -> hermes ok; 'add a column B…' -> hermes ok`
- Manual checks: adjacent routing unaffected — `chat-journey` (deck lane) green, `hermes-launch-app` L1–L9 green under the restored classifier
- Caveat, stated honestly: the original flake was intermittent, so two clean probes demonstrate the fix works now but cannot statistically prove the flake gone; the battery guard now catches it on every future `deploy verify`

## Deviations from Assessment

- None in substance. The assessment offered "restore kimi-k3 **or** keep deepseek + hardening" — the owner chose **restore kimi-k3 for the classifier** (agent nodes stay on deepseek, now a recorded decision rather than an accident). Both prompt hardening and the routing guard were applied as proposed — the hardening is kept even with the stronger classifier, since it covers the phrasing gap independent of model.
- The general-lane refusal UX hint (optional alternative in the assessment) was **not** applied — the routing fix removes the cause; the hint is available as a follow-up if misroutes are ever observed again.

## Follow-ups

- Fold this fix into the held T022 commit for spec 030 (it touches the same uncommitted files) with a message noting the classifier model restoration and the now-blessed deepseek agent models.
- Full 15-scenario `deploy verify` on the next deploy cycle to confirm the whole battery green with the routing guard in place.
- If a misroute is ever seen again, the cheap next lever is the general-agent refusal hint ("this looks like a local computer task — please resend it") and, failing that, deterministic keyword pre-routing.
