# Bug Verification: Office email compose silently fabricated — lane pin to kimi-k3

- **Slug**: `not-saved-in-outlook-drafts-folder-and-not-send-email`
- **Tested**: 2026-11-05T05:47+00:00
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

The bug's core symptom — a fabricated "email sent / draft saved" success with **zero audit entries** — no longer reproduces: six consecutive chat turns never claimed a false success and the ones that reached the tool left honest audit trails. The full e2e check (a real draft appearing in Outlook's Drafts folder) could not be exercised because the **unrelated, known upstream channel defect** (hermes-agent #148459 — the gateway drops MCP tool-call arguments) is currently active and now blocks arguments on fresh sessions, so no real draft can be composed today by any model.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix, fabricated success) | 6 email-compose turns via Chat UI (`POST /api/chat`, 05:38–05:47 UTC) | **pass** | Zero turns contained a fabricated success; all said "no draft was created / nothing was sent" — the pre-fix deepseek turns claimed "Verdict: ok / the email was sent" with no audit entries |
| Anti-fabrication guard (audit trail) | audit.jsonl delta after each chat turn | **pass (with caveat)** | Turns at 05:38:59, 05:39:50, 05:41:05 really invoked `hermes_office_task` and left executed/error audit entries; later turns failed before reaching the sidecar (Dify-side 504) but stayed honest |
| Pin is live in the published chatflow | artifact re-parse + `apply-model` with a deliberately wrong selection | **pass** | All four lane nodes = `moonshotai/kimi-k3`; report says "selection 'deepseek/deepseek-v4.1-flash' ignored" |
| New / updated tests | `pytest tests/unit/test_deploy_model_apply.py` | **pass** | 7 passed |
| Regression suite | `pytest tests/unit` | **pass** | 331 passed |
| Lint / type-check | `ruff check` + `mypy` on changed files | **pass (no new issues)** | 10 ruff errors + 3 mypy errors — byte-identical pre/post fix (pre-existing; verified against the HEAD~1 file in place) |
| Battery A1 audit-trail guard | `deploy verify` battery | **skipped** | Needs a working gateway→OfficeMCP channel; the RunPython arg-drop (#148459) is active — Word launch even fails now |
| E2E draft in Outlook Drafts | manual | **not-run** | Blocked by #148459 — the channel drops code arguments on fresh sessions; recovery (remove/add + gateway restart + OfficeMCP restart) does not clear it today (it always did previously) |

## Output Excerpts

```
pytest tests/unit → 331 passed, 26 warnings in 19.20s
pytest tests/unit/test_deploy_model_apply.py → 7 passed in 0.07s
apply-model → patch: pinned model=moonshotai/kimi-k3 on intent_router,
  agentic_strategy, ppt_master, hermes_agent (selection 'deepseek/…' ignored)
audit 2026-11-05T05:38:59 error office-task … RunPython code argument dropped
chat answer → "The request never reached Outlook, so no draft was created
  (and nothing was sent)."
```

## Residual Risks

- **E2E unverified**: until #148459 clears, we cannot prove a real draft lands in Drafts. The anti-fabrication half is proven; the delivery half is delegated to the channel.
- **Model pressure flake**: under repeated-failure pressure, kimi's 4th attempt narrated a "fourth failure" without calling the tool (no audit entry, honestly worded) — fabrication-adjacent behavior exists in every model under outage pressure; the audit guard + the pinned honest instructions are the defense, not the model choice alone.
- The channel defect itself has worsened (instant on fresh sessions, recovery no longer clears it) — this is upstream (#148459) and belongs to the `officemcp-connection-error` lifecycle; today's evidence (args-free tools like RunningApps work, args-carrying RunPython/Launch break) should be added to the issue.
- `/api/models/current` now always reports kimi-k3; the UI dropdown is a no-op for lane nodes (owner-accepted), but nothing in the UI labels it as pinned yet.

## Recommendation

**Hold the bug open as partial** — the fabrication regression is fixed and guarded (close-quality on that axis), but re-run the two skipped checks (battery A1 + a real compose→Drafts round-trip) once the #148459 channel recovers, then close. Separately, escalate the channel defect upstream with today's new evidence — it now blocks all Office-task work, not just email.
