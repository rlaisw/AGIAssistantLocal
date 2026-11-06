# Bug Assessment: "open chrome and type www.google.com" falsely blocked as "more than one application" — and the GUI part is now fulfillable via WindowsMCP

- **Slug**: `blocked-more-than-one-application-named`
- **Created**: 2026-11-06T09:40+00:00
- **Source**: pasted text (three chat transcripts: "open default browser/…chrome/…edge and type www.google.com", all blocked)
- **Verdict**: valid — a gate parsing false-positive **plus** a stale lane contract (written before WindowsMCP existed)
- **Severity**: medium — a whole class of natural requests ("open X and do Y in it") is refused with a misleading reason; with WindowsMCP installed it is a capability gap, not just a message bug

## Report (verbatim or summarized)

> "Blocked: more than one application named — ask the user which one to launch (v1 launch scope: one program by name or full .exe path only — never arguments, never shell/PowerShell, never scripts or shortcuts)"

Three consecutive requests — "open default browser and type www.google.com", "open chrome and type www.google.com", "open edge and type www.google.com" — all blocked with the same reason, and the agent (following its instructions) relayed the refusal verbatim and offered no path forward other than launching the bare browser.

## Symptom

A launch-plus-GUI request ("open chrome **and type** www.google.com") is refused as naming "more than one application", even though exactly one application is named. Expected: Chrome launches, then the URL gets typed into the address bar — both now possible with the installed toolset.

## Reproduction (gate unit level, 2026-11-06)

```
gate_launch("open chrome")                              -> ok  (Launch 'chrome')
gate_launch("open chrome and type www.google.com")     -> blocked (MULTI)
gate_launch("open default browser and type ...")        -> blocked (MULTI)
gate_launch("open edge and type www.google.com")       -> blocked (MULTI)
```

Audit trail: three `blocked` ask-backs at 09:29:09 / 09:35:51 / 09:36:22 / 09:36:57 UTC.

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_launch_gate.py:139-163` — bare-name extraction: every token not in `_FILLERS` becomes an application-name candidate, so `type`, `www.google.com`, `default`, `browser` all count as "applications" → `len(names) > 1` → MULTI ask-back. The v1 scope was deliberately strict (spec 029), but "and type/click/do X" is **GUI-automation intent, not a second application**, and `www.google.com` is not an application at all
- `src/agentic_rag_mcp/hermes_client.py` — `LAUNCH_INSTRUCTIONS`: the lane contract predates WindowsMCP and says GUI automation is refused verbatim ("never arguments, never GUI automation — relay the refusal"). The gateway agent executing these instructions **now has WindowsMCP's 21 desktop tools registered** (this morning): App/Type/Click/Shortcut can complete the typing part under their own desktop-control policy
- `src/agentic_rag_mcp/hermes_launch_gate.py:166-167` — `_NON_APP_NOUNS` includes "browser"? (not checked — likely absent; "default browser" parsing needs verification in the fix phase)

## Root Cause Hypothesis

**High confidence, two stacked causes.** (1) The launch gate's name extraction has no notion of a post-launch GUI clause: action verbs ("type", "click", "press", "enter") and their operands (URLs, text) are miscounted as additional application names, producing a false "more than one application named" instead of the correct outcome for a one-app-plus-GUI request. (2) The lane contract is stale relative to this morning's WindowsMCP installation: it instructs the agent to refuse GUI automation outright, even though the agent's own toolset can now perform it. The result is a triple refusal loop on an entirely reasonable request, with a misleading message each time.

## Proposed Remediation

**Preferred**: two-part fix. (1) **Gate**: split the task at GUI intent — when the request contains a launch clause plus an "and/then type/click/press …" clause, extract the single launchable name (running the existing scope checks on it: no shell, no chaining, no arguments *to the launch*) and return an `ok` verdict whose `sanitized_task` covers only the launch; carry the GUI clause as an explicit `desktop_followup` field on the verdict. Anything with two *real* app names still gets the MULTI ask-back. (2) **Lane contract**: update `LAUNCH_INSTRUCTIONS` — when the verdict carries a desktop followup, the agent completes it with its WindowsMCP tools (`App` for focus, `Type` for text, `Shortcut` for keys) under WindowsMCP's own desktop-control policy (idle wait, AI indicator, user takeover), reporting both steps; pure launch requests unchanged. "Default browser" resolves to the agent checking/asking once, then behaves as the named case.

**Alternatives**:
- A separate `hermes_desktop_task` sidecar tool with its own gate — cleaner layering long-term (and consistent with the file/office lanes), but a new surface to gate and audit; the verdict-field approach reuses the existing gate and audit trail with a much smaller diff
- Keep the refusal but fix only the message — rejected: the capability now exists; refusing fulfillable requests is the bug

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_launch_gate.py` — GUI-clause split, `desktop_followup` field, "type/click/press" verb set
- `src/agentic_rag_mcp/hermes_client.py` — `LAUNCH_INSTRUCTIONS` update
- `src/agentic_rag_mcp/server.py` — `hermes_launch_app` passes the followup into the directive (where `directive_ctx` style hint injection already lives)
- `tests/unit/test_hermes_launch_gate.py` (or wherever the gate's tests live) — new cases

**Tests to add or update**:
- Gate: "open chrome and type www.google.com" → ok with target `chrome`, followup `type www.google.com`; two real apps still MULTI; shell/chaining/argument refusals unchanged; "default browser" resolution path
- Guard: LAUNCH_INSTRUCTIONS contains the desktop-followup delegation rule

## Risks & Considerations

- **Desktop control is now reachable from the launch lane** — a deliberate scope expansion, but every GUI action still passes through WindowsMCP's own gates (idle wait, indicator, Ctrl+Alt+Shift+Backspace takeover), and the audit log records the whole turn; the launch itself keeps the no-arguments/no-shell rules
- URL-in-address-bar is user-visible typing (browsing history, possibly logins) — the desktop-control policy is the mitigation; consider whether the agent should confirm before typing into a browser address bar (owner's call, can default to confirm)
- The "type" clause could contain arbitrary text to type into whatever has focus — the instruction must pin focus verification (App/click the address bar first) or wrong-window typing becomes a real hazard; the fix phase should require a focus step
- "default browser" resolution needs a source (check installed browsers, or ask once) — do not guess silently

## Open Questions

- [NEEDS CLARIFICATION: should typing a URL into a browser address bar require an in-chat confirmation, or is WindowsMCP's idle-wait policy sufficient?]
- Should other GUI verbs (scroll, click coordinates) ride the same followup field now, or only text typing in v1 of this fix?