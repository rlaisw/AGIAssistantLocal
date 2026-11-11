# Bug Fix: Chrome weather query — browser+followup re-route (launch gate + DSL)

- **Slug**: no-response-test-playwright
- **Fixed**: 2026-11-11T08:15:27Z
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The 2026-11-06 "desktop followups" rule and spec 037's "browser intents never ride OS/desktop automation" rule were in direct conflict for browser+typing prompts — the exact class of the silent 08:08 test turn. Both layers now agree: typing/searching/reading in a browser is a web intent (dynamic browser lane), and the launch gate structurally refuses browser+followup launches with an honest re-route.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_launch_gate.py` | modified | `_BROWSER_PROGRAMS` set (chrome/edge/firefox/brave/browser/safari/opera/vivaldi/default browser) + `_BROWSER_FOLLOWUP_REFUSAL` honest re-route text; both final `ok` paths (quoted + name targets) now refuse when the target is a browser AND a desktop followup exists — never a stalled silent GUI attempt |
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | The 2026-11-06 desktop-followup rule scoped to NON-BROWSER programs, with the browser carve-out verbatim ("open chrome and type X in the search bar means: browse and read — a dynamic-lane task, NOT desktop automation") |
| `tests/unit/test_browser_routing_gate.py` | added 5 tests | Mixed browser+typing prompts (incl. the verbatim 08:08 test prompt) → dynamic lane, never OS; non-browser typing → not-browser ask-back |
| `tests/unit/test_hermes_launch_gate.py` | modified + added | 4 new refusal pins (chrome+typing, edge+search) + preserved capabilities (bare chrome launch ok; notepad+typing followup ok); 9 existing chrome+followup pins re-scoped to the new contract — they were the bug's own documentation |

## Diff Highlights

```python
# gate: browser + followup -> honest re-route (never silent GUI stall)
if low in _BROWSER_PROGRAMS and followup:
    return _blocked(_BROWSER_FOLLOWUP_REFUSAL.format(app=target), target=target)
```

## Tests Added or Updated

- `TestMixedBrowserTyping::test_routes_to_dynamic_never_ask_back_or_scripted` — the verbatim 08:08 prompt + 3 variants → dynamic lane
- `TestBrowserFollowupRefusal::test_chrome_plus_typing_refused_with_reroute` / `test_edge_plus_search_refused` — the launch gate refuses with the re-route
- `TestBrowserFollowupRefusal::test_bare_chrome_launch_still_ok` / `test_notepad_plus_typing_still_ok_followup` — the 2026-11-06 capability preserved for non-browsers
- 9 existing pins re-pointed at notepad targets (their chrome examples were the conflict itself)

## Local Verification

- Commands run: `pytest tests/unit/test_hermes_launch_gate.py` → **47 passed** (43 re-scoped + 4 new)
- Commands run: `pytest tests/unit/test_browser_routing_gate.py` → **16 passed** (11 + 5 new)
- Commands run: `pytest tests/unit/` → **559 passed** (full regression green)
- Commands run: `ruff check --fix` → clean on all touched files; diff surgical (+25 lines gate)
- Manual checks: YAML re-validated after the DSL edit

## Deviations from Assessment

The assessment proposed routing fixes only at the DSL level; the fix adds a **structural gate refusal** too (the same insight as 034/036/037: prompt rules are soft, tool-level refusals are hard). The gate refusal text re-routes rather than errors — matching the assessment's honest-failure requirement. No other deviations.

## Follow-ups

- **Publish DONE (2026-11-11T09:07Z)**: `deploy all` rebuilt the container (gate fix verified in-image: browser-refusal refs present) and published the re-scoped DSL (chatflow-publish ✓ at 08:48). The battery died mid-office-lane when the container exited cleanly (Exit 0, no OOM) at ~09:01 and restart=always recovered it — the office/run/powershell lanes + final summary never ran. **Targeted live verification on the post-deploy container instead**: the X1 probe returned status ok + the REPLACED: stamp (both legs green), and the launch-gate browser refusal is in the image. A full `deploy verify` re-run at a future window would give the formal 15/15 battery record; the fixes themselves are live.
- The two assessment open questions (UI symptom, Chrome visibility) closed as moot — the root cause was confirmed in the DSL text itself.
- Live re-test: re-send the verbatim weather prompt — expected: the dynamic browser lane executes (or an honest ask-back), never silence.