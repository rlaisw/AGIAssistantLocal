# Bug Assessment: chat still refuses typing — stale GUI-automation refusal in the Dify-side prompt + comma-list phrasing the gate can't split

- **Slug**: `typing-search-is-gui-automation-that-the-local-agent-cant-perform`
- **Created**: 2026-11-06T15:05+00:00
- **Source**: pasted text ("typing search) is GUI automation that the local agent can't perform") + live investigation of the four failing turns
- **Verdict**: valid — two gaps in the previous fix's coverage (`blocked-more-than-one-application-named`): the fix updated the **sidecar's** launch instructions but not the **chatflow's** agent prompt, and the gate's clause split only matches "and/then" phrasing
- **Severity**: medium — the user's natural phrasing ("open chrome, open a new tab, type X, type Y") is refused or silently truncated in real chat, even though every piece is now performable

## Report (verbatim or summarized)

> "typing search) is GUI automation that the local agent can't perform."

Four consecutive turns (14:46–14:52 UTC): "type hong kong hang seng index at search bar" → the chat refused outright ("This is GUI automation — typing … relay the refusal verbatim"); then three "open chrome, open a new tab, type www.google.com, type hong kong hang seng index at search" attempts → the chat launched Chrome only ("The only executable part here is 'open chrome.' The rest … is all GUI automation, which is out of scope") and told the user the rest can't be done.

## Symptom

In the real chat, typing/clicking followups are still refused or stripped from the request, while the same task called directly at the tool level (the previous fix's live test) worked end-to-end. Expected: the full sequence — launch, new tab, URL, search query — executes via the agent's WindowsMCP tools.

## Reproduction (evidenced, 2026-11-06 UTC)

1. 14:46:39 — "type hong kong hang seng index at search bar" → chat answers "This is GUI automation — typing … the launch [scope] … relay the refusal verbatim" — the Dify-side agent refused **without calling any tool**
2. 14:48–14:51 — the comma-list variants: the chat answers "The only executable part here is 'open chrome.' The rest — opening a new tab, typing a URL, typing a search query — is all GUI automation, which is out of scope", then calls the tool with **only the launch part**
3. Audit trail: only two executed launches (14:44:41, 14:52:21), both plain "LAUNCH: SUCCESS" with no desktop followup — the typing clauses never reached the tool
4. **The stale text lives in the chatflow DSL** (`dify/AGIAssistant/AGI_Assistant.yml:~1400`, the `hermes_agent` node's prompt): "The tool enforces this — if the user asks for launch arguments, PowerShell/shell commands, or **GUI automation, relay the refusal verbatim; do not try to work around it.**" — the previous fix updated `LAUNCH_INSTRUCTIONS` (sidecar) but this Dify-side prompt still orders the opposite behavior, and the Dify agent obeys it before the tool ever sees the task
5. **Gate gap**: `hermes_launch_gate.py`'s `_RE_GUI_CLAUSE` splits only at "(and|then) + verb" — "open chrome, **,** open a new tab, type …" (comma-separated clauses) never matches; and "open a new tab" contributes phantom name tokens (`new`, `tab`) to the MULTI count

## Suspected Code Paths

- `dify/AGIAssistant/AGI_Assistant.yml:~1400` — the stale GUI-automation refusal in the `hermes_agent` node prompt (the layer that decides how to phrase tool calls from chat)
- `src/agentic_rag_mcp/hermes_launch_gate.py` — `_RE_GUI_CLAUSE` covers "and/then" only; comma-lists and additional imperative clauses ("open a new tab") unhandled
- `src/agentic_rag_mcp/hermes_client.py` — `LAUNCH_INSTRUCTIONS` already has the correct DESKTOP FOLLOWUP delegation (the sidecar side is fine)

## Root Cause Hypothesis

**High confidence, two stacked causes.** (1) The Dify-side `hermes_agent` node prompt — the first and most authoritative instruction the chat agent reads — still orders refusing GUI automation verbatim; the previous fix's live test bypassed this layer by calling the sidecar tool directly, so it passed while real chat kept refusing. (2) Even if the chat passed the full text, the gate's clause regex only recognizes "and/then" before a GUI verb — the user's comma-separated clause list doesn't match, "open a new tab" itself is a GUI clause the parser treats as phantom application names, and the followup would be lost or the whole request MULTI-blocked.

## Proposed Remediation

**Preferred**: close both layers. (1) **Chatflow prompt**: rewrite the launch-scope bullet in the `hermes_agent` node — GUI automation is now supported as the tool's *desktop followup*: pass the user's full task text (including "and/then/comma type/click/press …" clauses) to `hermes_launch_app` unchanged and relay its verdict; never strip clauses or refuse typing/clicking on the chat side (the tool enforces its own scope and reports honestly). Republish via the existing apply-model cycle (model pin = no model change). (2) **Gate clause parser**: generalize the split to comma-separated clauses — match the *first* GUI verb (type/click/press/enter/scroll) preceded by "and/then" **or a comma**; additionally treat secondary imperative clauses that are not launch targets ("open a new tab", "switch to …") as part of the followup rather than name candidates. The followup text then carries the full remaining sequence (new tab → URL → search query) for the agent's WindowsMCP tools, which already know Ctrl+L / Ctrl+T-style steps.

**Alternatives**:
- Teach only the chat prompt to rephrase comma-lists into "and" form — rejected: fragile; the gate should understand real phrasings
- A dedicated `hermes_desktop_task` tool for pure-GUI requests with no launch ("type X at search bar") — note: turn 14:46:39 had NO launch clause at all, so the launch gate can't carry it; the chat prompt must route pure-GUI requests somewhere. Minimal answer: let `hermes_launch_app` accept a followup with no launch target when the user names a running app ("type X in chrome's search bar" → target chrome), and for truly target-less GUI requests the chat asks which app — same ask-back philosophy as FR-011

**Files likely to change**:
- `dify/AGIAssistant/AGI_Assistant.yml` — `hermes_agent` node prompt (launch-scope bullet), republished
- `src/agentic_rag_mcp/hermes_launch_gate.py` — comma-clause split + non-launch imperative clauses → followup; allow target-from-running-app phrasing where feasible
- `tests/unit/test_hermes_launch_gate.py` — comma-list phrasings, "open a new tab" clause, pure-GUI-with-app phrasing

**Tests to add or update**:
- Gate: "open chrome, open a new tab, type www.google.com, type hong kong hang seng index" → ok, target chrome, followup carrying the whole remaining sequence
- Gate: "type hong kong hang seng index at search bar" (no launch) → ask-back or app-inference path per chosen design
- Chat prompt: after republish, a live turn with the comma-list phrasing must execute the full sequence

## Risks & Considerations

- The comma-split must not weaken the MULTI protection for genuinely different app targets ("open chrome, open edge, …") — comma lists of *launch* clauses still need the ask-back
- The Dify prompt change is user-facing agent behavior; verify the office/file lanes' bullets aren't accidentally edited in the same block
- Publishing the chatflow briefly touches the draft workflow — use the pinned apply-model cycle (no model change, prompt-only)
- "type X at search bar" with no app named: inferring the focused window is exactly the wrong-window hazard the instructions forbid — prefer the ask-back over inference

## Open Questions

- [NEEDS CLARIFICATION: for pure-GUI requests with no launch clause and no app named ("type X at search bar"), should the chat ask-back which application — or attempt the currently focused window? The instructions' focus-verification rule argues for ask-back]
