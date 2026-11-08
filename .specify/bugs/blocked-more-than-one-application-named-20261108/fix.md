# Bug Fix: `search` (and find/look up) join the gate's split verbs; session/browser are context nouns — the MULTI false-block on search requests is gone

- **Slug**: `blocked-more-than-one-application-named-20261108`
- **Fixed**: 2026-11-08T02:30+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — gate-level fix complete and unit-verified; live-verified that the gate passes the exact request; the followup's *execution* is environmentally blocked by the recurring RDP-disconnect issue (below), which is out of this bug's scope

## Summary

The launch gate now treats `search`/`find`/`look up`/`google` as desktop-followup verbs (splitting at "and/then", a comma, **or plain whitespace** after a launch head), and `new`/`session`/`browser` are fillers so "open a new session chrome browser" reduces to the single target `chrome`. The exact report request — "open chrome search hong kong weather , show me the temperature today" — now returns `ok` with target `chrome` and the whole tail (search + observe clause) carried as the desktop followup.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_launch_gate.py` | modified | `_RE_GUI_CLAUSE` verb set: + `search`, `find`, `look up`, `google`; a bare-whitespace alternative splits "open chrome search X" when a launch head precedes the verb; `_FILLERS`: + `new`, `session`, `browser` ("default browser" compound matched before filler filtering, so it is unaffected — pinned by existing test) |
| `tests/unit/test_hermes_launch_gate.py` | +5 tests | bare-space search split, observe-clause riding along, context-noun fillers, "open search" ask-back boundary, chaining rule cannot be bypassed via search |

## Diff Highlights (optional)

```python
_RE_GUI_CLAUSE = re.compile(
    r"(?:\b(?:and|then)\s+|,\s*)"
    r"(type|click|press|enter|scroll|type\s+into|search|find|look\s+up|google)\b.*$"
    r"|\s+(search|find|look\s+up|google)\b.*$", re.IGNORECASE)
# fillers += {"new", "session", "browser"}
```

## Tests Added or Updated

- `test_search_verb_splits_without_conjunction`, `test_search_tail_rides_with_observe_clause`, `test_new_session_browser_context_nouns_are_fillers`, `test_open_search_alone_is_askback_not_phantom_launch`, `test_search_followup_cannot_bypass_chaining_rule`
- Gate suite 44 passed; full suite **346 passed**; `ruff` clean

## Local Verification

- Gate matrix (all report phrasings): "open chrome search hong kong weather" → ok target `chrome`; with ", show me the temperature today" → tail rides the followup; "open a new session chrome browser , search …" → ok target `chrome`; two real apps still blocked; chaining in the followup still blocked; "open chrome, type www.google.com" unchanged
- `deploy redeploy` → ok
- **Live (02:20)**: the exact request → `status ok`, gate passed, followup carried — *"Chrome launch: succeeded… Desktop followup (search 'hong kong weather', show today's temperature): not completed. WindowsMCP desktop control is currently unavailable (state: unavailable…)"* — the agent honestly declined rather than fabricating or working around the gate
- **Environmental blocker (recurring, out of scope)**: by 02:25 the RDP session had **disconnected again** (`qwinsta`: state `Disc`), WindowsMCP 0.8.8 cannot restart ("No active interactive desktop"), and its control machinery had degraded — the same pattern as 2026-11-06. Reconnect the session (RDP), then `Start-ScheduledTask windows-mcp-server` (or `./reboot.sh`), and re-ask to complete the search end-to-end

## Deviations from Assessment

- The bare-space split (for "open chrome search x" with no and/comma) goes slightly beyond the assessment's letter (which focused on adding the verb) — required by the first report phrasing, and its one behavior change ("open search" alone now ask-backs instead of launching a phantom "search" app) is pinned by test and matches FR-011's honest-fallback design
- No other deviations

## Follow-ups

- **Recurring environmental fragility worth its own lifecycle**: the RDP session disconnects and WindowsMCP 0.8.8 dies/degrades every time (observed 2026-11-06 and again within 30 min today). Candidates: reboot.sh proactively restarting the `windows-mcp-server` task when its control state is unavailable; a watchdog; or evaluating a newer windows-mcp version whose control-off mode survives disconnected sessions — owner's call
- The observe step ("show me the temperature today") rides the followup as text; the agent's WindowsMCP Scrape/Snapshot can fulfill it once the control state is healthy — watch quality on the first natural occurrence
- Multi-step desktop turns still take 3–6 minutes (desktop-control idle waits + LLM iterations) — the known latency floor
