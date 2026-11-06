# Bug Fix: chat-side refusal removed — prompt republished + comma-clause gate split; live e2e blocked by a disconnected Windows session (environmental)

- **Slug**: `typing-search-is-gui-automation-that-the-local-agent-cant-perform`
- **Fixed**: 2026-11-06T15:30+00:00
- **Assessment**: ./assessment.md
- **Status**: partial — both planned code changes applied and unit-verified; the live end-to-end is blocked by a NEW environmental finding (below), not by this fix's code

## Summary

The chatflow's `hermes_agent` prompt (the layer that was ordering the agent to refuse GUI automation verbatim) now instructs passing the FULL task text to `hermes_launch_app` unchanged, and the launch gate now splits comma-separated clause lists ("open chrome, open a new tab, type …") into one launch plus a carried desktop followup. The stale refusal is gone from the published app (verified in the live workflow graph), and the gate matrix proves the split at unit level. Live e2e remains blocked: WindowsMCP's control machinery cannot start in the machine's current session state (see Deviations).

## Changes

| File | Change | Notes |
|------|--------|-------|
| Live Dify workflow (`hermes_agent` node prompt) | modified | "GUI automation → refuse verbatim" replaced with the DESKTOP-FOLLOWUPS-ARE-SUPPORTED block: pass the full task text unchanged; never strip typing/clicking clauses; ask which application when no program is named. Applied export→patch→publish via the console API (a hand-edit of the local DSL alone is clobbered by the apply cycle's export step — see Deviations) |
| `dify/AGIAssistant/AGI_Assistant.yml` | synced | re-exported post-publish so the repo artifact matches live |
| `src/agentic_rag_mcp/hermes_launch_gate.py` | modified | `_RE_GUI_CLAUSE` splits at "and/then **or comma** + type/click/press/enter/scroll"; `_RE_SECONDARY_OPEN` routes "open a new tab/window" clauses into the followup instead of phantom name tokens |
| `tests/unit/test_hermes_launch_gate.py` | +4 tests | comma-list split, comma-before-verb, two-launch-targets still MULTI, GUI-only ask-back |

## Diff Highlights (optional)

```python
# gate: comma-lists now split like "and"-lists
_RE_GUI_CLAUSE = re.compile(
    r"(?:\b(?:and|then)\s+|,\s*)(type|click|press|enter|scroll|type\s+into)\b.*$", re.I)
_RE_SECONDARY_OPEN = re.compile(
    r",\s*(?:and\s+)?(?:open|launch|start|go\s+to)\s+a?\s*"
    r"(new\s+tab|new\s+window|...)\b", re.I)
# cut = earliest of the two matches; head = launch, tail = desktop_followup
```

## Tests Added or Updated

- Gate: `test_comma_list_splits_at_first_gui_verb` ("open chrome, open a new tab, type www.google.com, type hong kong hang seng index at search" → ok, target `chrome`, followup carries the whole sequence), `test_comma_before_verb_splits`, `test_two_launch_targets_comma_list_still_blocked`, `test_gui_only_with_no_app_ask_back`
- `pytest tests/unit` → **341 passed**; `ruff` clean on the gate

## Local Verification

- Gate unit matrix: all four real phrasings from the failing turns now pass (and/comma/secondary-clause), MULTI protection intact
- Live workflow graph check: `w.graph::text LIKE '%Desktop followups ARE supported%'` → **true** on the current published version (15:04:40)
- **Live e2e**: one turn exhausted its 600 s budget (desktop-control consent loops — the user was actively using the machine), and a lighter turn launched Chrome but honestly declined the typing ("WindowsMCP desktop control channel reports state 'unavailable'"). Investigation below.

## Deviations from Assessment

- **Hand-editing the local DSL is insufficient**: the apply-model cycle *exports the live app and overwrites the local file* before patching/publishing, so my first attempt was silently clobbered. The prompt change had to be applied **between export and publish** via the console API (export → patch the `hermes_agent` instruction → update draft → publish). A small tooling gap worth a follow-up: a prompt-patch step in the deploy cycle.
- **NEW environmental root cause for the live-blocked e2e (not this fix's code)**: WindowsMCP 0.8.8's control machinery hard-requires an **Active** Windows session (`control.py:329 → control_win32.py:_interactive_desktop()` → `WTSQuerySessionInformation` + `OpenInputDesktop`). The machine's session (rlwc145, ID 1) is currently **`Disc` (disconnected)** — `qwinsta` confirms — so: (1) the day's server degraded to ControlState "unavailable" (generation 146) when the session disconnected midday, explaining the agent's "consent timeout" and "unavailable" reports; (2) after my restart, the server **cannot start at all** in this state ("No active interactive desktop"), and 0.8.8 has NO config/env escape hatch (no `enabled` field; `--no-control` and `WINDOWS_MCP_CONTROL` are newer-version features — verified in the installed source). The lane returns when the console session is reconnected (physical login or RDP reconnect → `Start-ScheduledTask windows-mcp-server` / `./reboot.sh`). A Windows reboot also clears the wedged generation counter.
- The default-browser inference and ask-back-for-app-less-GUI (assessment open question) were implemented as specified: ask-back.

## Follow-ups

- **User action**: reconnect the Windows console session, then `./reboot.sh` (or `Start-ScheduledTask windows-mcp-server`) — the lane comes back with control working; re-run the comma-list e2e then
- Upgrade path worth evaluating: a newer windows-mcp version supports `[control] enabled=false` — a control-less mode would let the server survive disconnected sessions (currently the whole server refuses to start), at the cost of losing takeover safety; owner's call
- Deploy tooling: a prompt-patch step (or export-preserve) in the apply cycle so prompt edits aren't clobbered — the same trap will bite the next prompt change
- The 600 s budget exhaustion on multi-step desktop turns (consent waits while the user is active) is a separate UX cost — the deterministic-executor lifecycle remains the structural fix