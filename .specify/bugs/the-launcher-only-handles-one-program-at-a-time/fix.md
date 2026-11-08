# Bug Fix: compound app names + observe verbs — "open windows control panel , show me …" executes end-to-end

- **Slug**: `the-launcher-only-handles-one-program-at-a-time`
- **Fixed**: 2026-11-08T08:15+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — live-verified end-to-end on the exact request

## Summary

The launch gate now recognizes canonical multiword Windows app names (`control panel → control`, plus `file explorer`, `task manager`, `device manager`, `registry editor`) as ONE application via a consecutive-name-pair map — unknown pairs keep the honest MULTI ask-back — and observe verbs (`show`/`show me`, `display`, `view`) join the desktop-followup verb set (comma/and/then form only, protecting app names from bare-space splits). The user's exact request now runs end-to-end: Control Panel launched, navigated to Network Connections, and the adapter's Properties dialog opened.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_launch_gate.py` | modified | `_COMPOUND_APPS` map (canonical multiword names → launch targets) merged during name extraction as consecutive pairs; `_RE_GUI_CLAUSE` verb set: + `show`/`display`/`view` in the and/then/comma alternative only (bare-space stays search/find/look up/google, per the assessment's risk note) |
| `tests/unit/test_hermes_launch_gate.py` | +5 tests | compound launches, the exact report request (tail with "ip address setting" rides the followup), canonical set mapping, unknown-pair MULTI fallback, show-me comma split |

## Diff Highlights (optional)

```python
_COMPOUND_APPS = {"control panel": "control", "file explorer": "explorer",
                  "task manager": "taskmgr", "device manager": "devmgmt",
                  "registry editor": "regedit"}
# extraction: merge consecutive name pairs matching the map ("control","panel"
# -> "control"); unknown pairs stay two names -> honest MULTI ask-back
```

## Tests Added or Updated

- 5 new gate tests (49 gate-suite tests pass); full suite **351 passed**; `ruff` clean

## Local Verification

- Gate matrix (15 cases): the exact request → `ok, target=control, followup='show me network adapter configuration, e.g. ip address…'`; all four canonical compounds map; `open chrome firefox` still MULTI; `open search` still ask-back; `default browser` compound unaffected; chaining bypass still blocked
- `deploy redeploy` → ok
- **Live (08:06–08:13)**: the exact request → `status ok` — *"Control Panel started fresh. I opened Network Connections and the Intel i219-LM adapter's Properties dialog. No settings were changed. LAUNCH: SUCCESS"* — 470 s (Control Panel cold start + several click-navigation steps + desktop-control idle waits), full audit trail, and the read-only guarantee the agent attested ("No settings were changed")

## Deviations from Assessment

- None — the preferred remediation was applied as specified, with the open question resolved per the assessment's own recommendation (the full canonical compound set, not just `control panel`).

## Follow-ups

- Extend `_COMPOUND_APPS` opportunistically as real usage surfaces more multiword names (the map is one dict — trivial additions); unknown pairs fail honestly to the ask-back, so nothing blocks on the map being incomplete
- The 470 s turn duration is the known floor (cold app + click-navigation + consent waits) — the deterministic-executor follow-up remains the structural fix for desktop latency
- Watch natural "open X , show me Y" turns: the observe-followup's execution quality (navigating and reading settings) is now agent+WindowsMCP territory, one live sample so far (clean)
