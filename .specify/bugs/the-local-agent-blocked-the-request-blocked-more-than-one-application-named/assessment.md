# Bug Assessment: "check" missing from the observe-verb set — "open chrome , check hong kong temperature" MULTI-blocks

- **Slug**: `the-local-agent-blocked-the-request-blocked-more-than-one-application-named`
- **Created**: 2026-11-09T02:15+00:00
- **Source**: pasted text (the blocked reason relay) + live investigation (audit 02:06:30; the request: "help to open chrome browser , check hong kong temperature today")
- **Verdict**: valid — the fourth manifestation of the launch-gate parsing class, one new verb short
- **Severity**: medium — the natural "open X , check Y" phrasing family is refused despite the capability existing

## Report (verbatim or summarized)

> "The local agent blocked the request. Here's its reason, verbatim. Blocked: more than one application named"

The user asked "help to open chrome browser , check hong kong temperature today" (02:06:26); the gate blocked with the MULTI ask-back; the agent relayed it honestly.

## Symptom

A launch-plus-observe request naming exactly one application ("check the temperature in Chrome") is refused as "more than one application named". Expected: Chrome launches and the check tail rides the desktop followup.

## Reproduction (gate unit level, 2026-11-09)

```
gate_launch("help to open chrome browser , check hong kong temperature today") -> blocked (MULTI)
gate_launch("open chrome browser , check hong kong temperature today")        -> blocked (MULTI)
gate_launch("open chrome , check hong kong temperature today")                 -> blocked (MULTI)  ← no split happens
gate_launch("open chrome browser")                                             -> ok (chrome)    ← fillers fine
gate_launch("open chrome , show me hong kong temperature")                    -> ok (chrome + followup) — works today
```

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_launch_gate.py` — `_RE_GUI_CLAUSE` verb alternation (`type|click|press|enter|scroll|type into|search|find|look up|google|show|display|view`): **`check` is absent**, so the ", check …" tail never splits; the tokens `check hong kong temperature today` all become phantom application names. Precedents: the same class fixed three times (and/comma splits → search verbs → compound names + show/display/view).

## Root Cause Hypothesis

**High confidence.** Single missing verb: the observe-verb family gained `show/display/view` on 2026-11-08 but not `check` — and "check the weather/temperature/price" is the most common natural companion phrasing after "open X". Everything else in the pipeline is proven working by the same unit matrix (fillers handle "help to", "browser" is a context noun, the split mechanism itself is intact — demonstrated by the `show me` variant passing).

## Proposed Remediation

**Preferred**: add `check` (and its closest siblings `read` and `tell me`, the same observe family) to the `_RE_GUI_CLAUSE` verb alternation — comma/and/then form only, exactly as `show/display/view` were added. One regex change + the usual test batch.

**Alternatives**:
- A general clause grammar — rejected (the enumerated-verb approach has held through three fixes and each addition is one word + tests)
- Chat-side rephrasing — rejected (the gate should understand the user's words; pass-unchanged is the installed contract)

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_launch_gate.py` — verb set
- `tests/unit/test_hermes_launch_gate.py` — the report's phrasings + boundary cases

**Tests to add or update**:
- The exact report phrasing → ok, target `chrome`, followup carries "check hong kong temperature today"
- `open chrome , check x` and `open chrome and check x` → split
- `open chrome firefox` → still MULTI; `open check` alone → still ask-back (bare-verb protection already handles "search"; "check" must not gain bare-space form — comma/and/then only, protecting any app named "check")

## Risks & Considerations

- "check" as a bare-space verb could collide with a hypothetical app named "check" — mitigate by comma/and/then-only form (same protection the observe family already uses)
- The followup's execution ("check the temperature" = navigate + read a weather result) is the agent's WindowsMCP work with the fastest-path guidance; the known ~300 s chat ceiling applies — a weather check is a light task, well under it
- This is the fourth addition to the same regex; each has been one word + tests — the pattern is cheap and regression-guarded (49 gate tests)

## Open Questions

- [NEEDS CLARIFICATION: none blocking — "check" is evidence-backed; read/tell-me ride along as the same family with zero extra mechanism]
