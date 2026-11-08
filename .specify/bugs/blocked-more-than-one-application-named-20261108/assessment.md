# Bug Assessment: "open chrome search hong kong weather" still MULTI-blocks — the `search` verb (and browser-context nouns) are missing from the gate's clause parser

- **Slug**: `blocked-more-than-one-application-named-20261108`
- **Created**: 2026-11-08T02:15+00:00
- **Source**: pasted text (the blocked turn transcript "The local agent blocked the request Blocked more than one application named") + live investigation
- **Verdict**: valid — a new manifestation of the closed `blocked-more-than-one-application-named` class, with a distinct root-cause detail; recorded as a sibling lifecycle at the owner's request (history preserved)
- **Severity**: medium — the launch+desktop lane is again refused on natural phrasing; every "open X and search/find/show …" request fails until fixed

## Report (verbatim or summarized)

> "The local agent blocked the request Blocked more than one application named"

The user asked "open chrome search hong kong weather , show me the temperature today" (then twice "open a new session chrome browser , search hong kong weather"). The chat agent — correctly following the republished prompt — passed the FULL task text to `hermes_launch_app` unchanged; the tool blocked all three turns with "Blocked: more than one application named — ask the user which one to launch", and the agent relayed the ask-back verbatim.

## Symptom

A launch-plus-search request naming exactly one application is refused as "more than one application named". Expected: Chrome launches, the search runs in it, and the temperature is reported.

## Reproduction (unit + live, 2026-11-08 UTC)

1. Gate unit level: `gate_launch("open chrome search hong kong weather")` → **blocked (MULTI)**; same for `"open chrome and search …"` and `"open chrome, search …"` — the GUI-clause verb set (`type|click|press|enter|scroll|type into`) does not include **search**, so no split occurs and `search hong kong weather` count as application names
2. Live audit: three `blocked` ask-backs at 02:02:21, 02:04:08, (and the 02:05:44 turn) — same reason each time
3. Secondary parse gap: even with a split at "search", the head "open a new session chrome browser" yields names `new`, `session`, `chrome`, `browser` — `session`/`new`/`browser` are not fillers or compounds, so it would STILL MULTI-block on that phrasing

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_launch_gate.py` — `_RE_GUI_CLAUSE`: the verb alternation lacks `search` (and sibling observe-verbs like `find`/`look up`/`show`); `_FILLERS` lacks `session`; `browser` is only handled as the `"default browser"` compound, not as a context noun after a real app name (`chrome browser`)
- The Dify-side prompt (`hermes_agent` node) — **working as intended** (the agent passed the full text unchanged per the republished instruction; this report's blocker is purely the gate)

## Root Cause Hypothesis

**High confidence.** The previous fix enumerated five GUI verbs but not `search` — the most common real-world launch companion ("open chrome and search …"). Two parser gaps stack: (1) `search` (and observe-verbs like `show me`) aren't split points, so the query tokens become phantom application names; (2) browser-context phrasing ("a new session chrome browser") leaves `new`/`session`/`browser` as extra name candidates even after a split. The chat-side layer did its job; the gate is the sole remaining blocker.

## Proposed Remediation

**Preferred**: extend the gate's clause parser in three small ways. (1) Add **`search`** (and **`find`**, **`look up`/`lookup`**, **`google`** as a verb) to the `_RE_GUI_CLAUSE` verb alternation — a split there carries the entire tail ("search hong kong weather , show me the temperature today") into `desktop_followup`, where the agent's WindowsMCP tools (address bar + Scrape/Snapshot for the observe step) already know how to handle it. (2) Add **`session`**, **`window`** (beyond the existing secondary-open handling), and treat **`browser`** as a context noun: either add `browser`/`session` to `_FILLERS` (safe: "default browser" is matched as a compound BEFORE filler filtering) or, more conservatively, drop a trailing `browser` token when another concrete name precedes it (`chrome browser` → `chrome`). (3) Keep every existing refusal: shell/chaining/arguments rules still apply to both halves; two real app names still ask back.

**Alternatives**:
- Move to a general clause grammar (imperative verb + arguments per clause) — more robust long-term, but a rewrite of the parser for marginal gain over the enumerated-verb approach that has held up otherwise
- Chat-side rephrasing (agent converts "search" → "and type") — rejected: the gate should understand the user's actual words

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_launch_gate.py` — verb set + filler/compound handling
- `tests/unit/test_hermes_launch_gate.py` — the three phrasings from this report + `show me` tail riding along + two-real-apps still blocked

**Tests to add or update**:
- `"open chrome search hong kong weather"` → ok, target `chrome`, followup contains the search phrase
- `"open a new session chrome browser , search hong kong weather"` → ok, target `chrome`, followup carried
- `"open chrome and search x , show me the temperature today"` → the whole tail rides the followup
- `"open chrome and search x; rm -rf"` → still blocked (chaining rule)

## Risks & Considerations

- "search" as a verb is also a noun in some phrasings ("open the search app") — the split only triggers on "and/then/comma + search", so "open search" alone still parses as a name; add a test for `"open search"` to pin that boundary
- `browser`/`session` as fillers slightly widen what counts as "no app named" → more ask-backs for vague requests, which is the designed honest fallback
- The observe step ("show me the temperature today") rides the followup as text; the agent's WindowsMCP tools (Scrape, Snapshot, Screenshot) can fulfill it, but reading a live page adds latency and network dependence — out of this gate bug's scope
- Per the previous lifecycle: the followup's typing still needs ~10 s of user idle (desktop-control policy)

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the verb-set extension is evidence-backed; the `show me` observe-step execution quality is a separate concern if it disappoints]
