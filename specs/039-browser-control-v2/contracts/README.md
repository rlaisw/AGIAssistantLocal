# Contracts: Browser Control v2 (spec 039)

**Spec**: 039 | **Date**: 2026-11-13 | The six new sidecar tools (one per verb, clarified). All: `conversation_id` REQUIRED, audited per-verb, honest unavailable envelopes, screenshot-after-action best-effort on every call.

```
browser_select_v2(target: str, option: str, conversation_id: str)
  -> {status, verified, summary, screenshot?}
     option = the VISIBLE label the user asked for (value-match fallback);
     no match -> {status: "ask-back", reason: "no option '<option>' — available: [..]"}

browser_type_v2(target: str, text: str, conversation_id: str)
  -> {status, verified, summary, screenshot?}
     text = the user-provided literal, typed into ANY named field including
     passwords (displayed-masked; never logged in audit/summary/errors);
     read-back verified; not-found -> ask-back listing page fields

browser_form_v2(fields: {target: value}, conversation_id: str)
  -> {status, verified, summary, per_field?, screenshot?}
     multiple literal fields in ONE call; per-field results reported honestly

browser_press_key_v2(key: str, conversation_id: str)
  -> {status, summary, screenshot?}
     key allowlist: Enter, Escape, Tab, ArrowUp/Down/Left/Right

browser_tabs_v2(action: str, target: str = "", conversation_id: str)
  -> {status, tabs?, summary, screenshot?}
     action: list | switch | open | close (one per call)

browser_wait_v2(condition: str, text: str = "", bound_s: int = 10,
                conversation_id: str)
  -> {status, summary}
     condition: text-appears | navigation; bound 1..30s;
     timeout -> honest error naming what was awaited
```

## DSL wiring (per-component ownership)

- The six tools register on the Hermes lane list; the workflow rule gains the full verb vocabulary (the browser-action rule from 2026-11-13 is unchanged — action beats search).
- The per-step screenshot presentation rule (owner-required) stays in the routing text; the answer presents the step captures in order.
- `tool_mcp_providers` rebuild + api/worker restarts on publish.

## Audit contract

New `operation` values: `browser-select-v2`, `browser-type-v2`, `browser-form-v2`, `browser-press-key-v2`, `browser-tabs-v2`, `browser-wait-v2` — house row shape; outcome text EXCLUDES typed values (sensitive-field rule, R5).