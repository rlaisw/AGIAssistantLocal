# Bug Verification: Office-task prompts intermittently misroute to the general lane

- **Slug**: `office-routing-flake`
- **Tested**: 2026-11-02
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original symptom does **not** reproduce post-fix: the exact failing prompt — *"Insert a row at the top and add the header 'Height' in A1."* — now routes to the **Hermes Local Agent** branch and reaches the office tool. The new automated routing guard passes (run twice), adjacent-lane routing is unaffected (file lane, deck lane, launch lane all green), and the targeted test suites pass. The fix holds end-to-end on the live stack.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | Live chatflow probe with the **exact original phrasing**, node-trail capture | **pass** | `User Input → AI LLM Router → PPT or General? → Hermes Local Agent → Answer`; the agent proceeds to call the office tool |
| New/updated tests (guard) | `scenario_office_routing` via the battery, run twice | **pass ×2** | Both flaky phrasings → `hermes ok` in every run (4 probes total) |
| Adjacent routing (regression) | File-lane chat probe "create a folder routing_check in C:\temp" | **pass** | routed → hermes |
| Adjacent routing (regression) | `chat-journey` + `hermes-launch-app` (run post-publish during the fix) | **pass** | deck generation + launch L1–L9 green under the restored classifier |
| Regression suite | `pytest tests/unit/test_office_*.py tests/unit/test_hermes_office_tool.py tests/contract/test_deploy_cli.py tests/unit/test_deploy_sync_payload.py` | **pass** | 60 passed |
| Lint | `ruff check battery.py test_deploy_cli.py office_gate.py` | **pass (pre-existing only)** | 10 findings, all pre-existing (spec-011/028-era noqa/import nits; blind-except follows the battery's honest-failure pattern); none in the fix's new code |

## Output Excerpts

```
original-symptom reproduction: routed -> hermes
nodes: User Input -> AI LLM Router -> PPT or General? -> Hermes Local Agent -> Answer

office-routing guard: PASS | office-routing: 'Insert a row at the top and add the ' -> hermes ok;
                      "add a column B and put the text 'rou" -> hermes ok
file-lane routing probe: hermes
60 passed in 2.31s
```

## Residual Risks

- The original flake was **intermittent** — seven clean post-fix probes (the exact phrasing, four guard probes, file/deck/launch lanes) demonstrate the fix works now but cannot statistically exclude a rare future misroute; the `office-routing` battery scenario now catches any recurrence on every `deploy verify`, so a regression cannot ship silently again.
- The fix is **uncommitted** (classifier model restoration + prompt hardening + guard) alongside the rest of spec 030's held T022 — until committed, a re-deploy from a clean clone would lose it.
- The agent nodes remain on `deepseek-v4.1-flash` (owner-blessed cost choice, recorded in fix.md); if their behavior ever degrades, that is the first place to look — it is separate from routing, which the kimi-k3 classifier now owns again.

## Recommendation

Close the bug — **verified end-to-end**: the original reproduction was exercised post-fix with the exact failing prompt and routes correctly, the automated guard passes twice, adjacent lanes are unaffected, and the targeted suites are green. Fold the fix into the held T022 commit for spec 030 so the classifier restoration and the routing guard become permanent.
