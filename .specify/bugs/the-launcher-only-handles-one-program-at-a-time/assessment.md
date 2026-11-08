# Bug Assessment: "open windows control panel , show me …" blocked — multiword app names ("control panel") count as two apps, and "show me" isn't a recognized followup verb

- **Slug**: `the-launcher-only-handles-one-program-at-a-time`
- **Created**: 2026-11-08T08:00+00:00
- **Source**: pasted text (the blocked Control Panel request + the agent's relay of the "more than one application named" ask-back)
- **Verdict**: valid — the third manifestation of the launch-gate parsing class, with two new root-cause details
- **Severity**: medium — a whole family of natural requests (multiword Windows app names + "show me …" navigation followups) is refused despite being fulfillable

## Report (verbatim or summarized)

> "The local agent blocked this one — here's its reason verbatim: Blocked: more than one application named"

The user asked: "open windows control panel , show me network adapter configuration, e.g. ip address setting". The agent (correctly) passed the full task text to `hermes_launch_app`; the gate blocked it with the MULTI ask-back, and the agent relayed it honestly.

## Symptom

A request naming exactly one application — the Windows Control Panel — is refused as "more than one application named". Expected: Control Panel launches and the "show me network adapter configuration" tail rides the desktop followup for the agent's WindowsMCP tools.

## Reproduction (gate unit level, 2026-11-08)

```
gate_launch("open control panel")                                    -> blocked (MULTI)
gate_launch("open the control panel")                                -> blocked (MULTI)
gate_launch("launch control")                                        -> ok      (target: control)
gate_launch("open control panel and show me network adapter config") -> blocked (MULTI)
gate_launch("open control , show me network adapter configuration")  -> blocked (no split, no MULTI reason visible)
```

1. **Multiword app name gap**: `open control panel` yields names `[control, panel]` — `panel` is not a filler, so the gate counts **two applications** from one compound name. Even a bare `open control panel` with no followup blocks.
2. **"show me" verb gap**: the GUI-clause verb set (`type|click|press|enter|scroll|search|find|look up|google`) does not include **show (me)/display/view** — so the "show me network adapter configuration" tail never rides the followup even when a comma precedes it.
3. The chat-side prompt and honesty flow worked exactly as designed (full text passed, ask-back relayed, no re-attempt).

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_launch_gate.py` — bare-name extraction: no compound-name support; two consecutive non-filler nouns are indistinguishable from two launch targets. `_RE_GUI_CLAUSE`: verb set lacks observe-verbs (`show`, `show me`, `display`, `view`).
- Precedents: `blocked-more-than-one-application-named` (2026-11-06: and/comma split), `blocked-…-named-20261108` (search verbs + `new/session/browser` fillers) — same class, new details.

## Root Cause Hypothesis

**High confidence, two stacked causes.** (1) The gate has no notion of multiword application names: "control panel" (like "file explorer", "task manager", "device manager") is one app to the user but two name tokens to the parser → MULTI ask-back. (2) The followup verb set covers input verbs but not observe verbs, so "show me …" navigation requests never split and their tokens add phantom names. The compound case cannot be solved by fillers alone — "panel" is only a context word *after* "control".

## Proposed Remediation

**Preferred**: two small gate extensions. (1) **Known-compound app names**: a small mapping of canonical multiword Windows app names to their launch targets — at minimum `control panel → control` (also natural: `file explorer → explorer`, `task manager → taskmgr`, `device manager → devmgmt`, `registry editor → regedit`, `command prompt` is already shell-blocked) — matched as a two-token window during name extraction; a matched compound replaces its tokens with the single mapped target. Unknown two-token sequences keep today's MULTI ask-back (honest fallback for genuinely ambiguous requests like "open chrome firefox"). (2) **Observe verbs in the followup set**: add `show` (covering "show me"), `display`, `view` to `_RE_GUI_CLAUSE`'s verb alternation — with comma/and/then prefixes as today — so "open X , show me Y" splits and the tail rides `desktop_followup`.

**Alternatives**:
- Generic merge of consecutive non-filler tokens into one compound name — rejected: makes "open chrome firefox" launch a phantom "chrome firefox" and breaks the honest two-app ask-back.
- Chat-side rephrasing (agent converts "control panel" → "control") — rejected: the gate should understand the user's actual words; also violates the pass-unchanged instruction we installed.

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_launch_gate.py` — compound-name map + extraction window; verb set extension
- `tests/unit/test_hermes_launch_gate.py` — the report's phrasings + boundary cases

**Tests to add or update**:
- `open control panel` → ok, target `control`
- `open windows control panel , show me network adapter configuration, e.g. ip address setting` → ok, target `control`, followup carries the show-tail
- `open file explorer` / `open task manager` → ok, mapped targets (if the map includes them)
- `open chrome firefox` → still MULTI (unknown compound falls back honestly)
- `open control , show me x` → split works (verb test independent of compound map)

## Risks & Considerations

- The compound map is a hardcoded list — keep it to unambiguous, canonical Windows applets; anything unmapped asks back (designed honesty)
- Mapping to `devmgmt`/`regedit`-style tools widens what the gate will launch — stick to names the user could have typed anyway (no privilege expansion: these are normal user-level applets)
- "show" as a verb also appears in "open the show app"? — no such common app; bare-space splitting for observe-verbs should NOT be enabled (comma/and/then only) to avoid mangling "open powershow"-type names; the input verbs keep their bare-space form
- The followup's execution (navigating Control Panel to adapter settings) is the agent's WindowsMCP work — reading settings via click-navigation is user-visible but read-only; no new gating needed beyond the existing desktop-control policy

## Open Questions

- [NEEDS CLARIFICATION: scope of the initial compound map — just `control panel`, or the short canonical set (file explorer, task manager, device manager, registry editor) in the same fix? Recommend the short set: same mechanism, one test batch.]
