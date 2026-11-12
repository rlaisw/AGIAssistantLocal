# Bug Assessment: "MS Word" launch blocked as "more than one application named"

- **Slug**: the-launch-was-blocked-by-the-local-agent-its-verdict-verbatim
- **Created**: 2026-11-12T06:50:03Z
- **Source**: pasted text (the chat answer's relay: "The launch was blocked by the local agent. Its verdict, verbatim …")
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim, summarized)

The user asked "open MS Word, type Hello" in the Chat UI. The answer relayed: *"The launch was blocked by the local agent. Its verdict, verbatim: Blocked: more than one application named — ask the user which one to launch (v1 launch scope: one program by name or full .exe path only …)"*.

## Symptom

A natural, extremely common phrasing — "open **MS Word**, type Hello" — is refused by the launch gate as **two applications** ("MS" + "Word" are parsed as two names), forcing a pointless ask-back. Worse, the failure is **intermittent by agent phrasing**: the same user prompt succeeded at 06:25 (the agent happened to phrase the launch single-name) and was blocked at 05:47:25 and 06:47:43 (phrased "MS Word" both times — audit rows identical to the minute).

## Reproduction

1. Ask "open MS Word, type Hello" in the Chat UI.
2. The Dify agent passes "open MS Word, type Hello" to `hermes_launch_app`; the gate's GUI-clause split yields the launch head "open MS Word"; the name parser produces **["MS", "Word"]**; `_COMPOUND_APPS` has no "ms word" entry → len(names) > 1 → honest MULTI ask-back (audit: `Blocked: more than one application named …`, 05:47:25 and 06:47:43).
3. Re-ask the same thing; depending on how the agent words the tool call, it may pass (06:25) — the intermittency is the phrasing lottery, not the user's prompt.

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_launch_gate.py:48` — `_COMPOUND_APPS` maps only 5 Windows-system compounds ("control panel", "file explorer", "task manager", "device manager", "registry editor"); the entire Microsoft Office family is absent.
- `hermes_launch_gate.py:258` — the consecutive-pair merge consults that map; "ms word" misses → two names → `_ask_back(_MULTI)`.
- Knock-on: the skill "launch_app_and_type_text" (saved 06:25) templates `open {{application}} and type {{text}}` — a future replay with application="MS Word" hits the same block, so the learning loop would record failures for a phrasing problem.

## Root Cause Hypothesis

The gate's compound-name map simply never learned the Microsoft application family; "MS Word"/"Microsoft Excel"/"MS PowerPoint" are canonical user phrasings that tokenize into two bare names. The 06:25 success was the agent spontaneously using a single-token name ("Word"-style), which is why the same request flip-flops. Confidence: **high** — both blocked rows, the gate code, and the compound map are all in hand.

## Proposed Remediation

**Preferred**: extend `_COMPOUND_APPS` with the Microsoft family (two-token merges):
`"ms word": "word"`, `"ms excel": "excel"`, `"ms powerpoint": "powerpoint"`, `"ms outlook": "outlook"`, `"ms access": "access"`, `"microsoft word": "word"`, `"microsoft excel": "excel"`, `"microsoft powerpoint": "powerpoint"`, `"microsoft outlook": "outlook"`, `"microsoft edge": "edge"`, `"ms edge": "edge"`, `"microsoft teams": "teams"`, `"ms teams": "teams"`, `"ms paint": "mspaint"`, `"visual studio code": "code"` (three-token merges are NOT needed for the demonstrated class; skip).

**Alternatives**: resolve "MS" as a silent prefix (drop leading "ms"/"microsoft" tokens before name parsing) — broader but risks swallowing a real second target; the explicit map is honest and testable. Chosen: the map.

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_launch_gate.py` (the map)
- `tests/unit/test_hermes_launch_gate.py` (pins)

**Tests to add or update**:
- `gate_launch("open MS Word, type Hello")` → ok, target "word", followup "type Hello"
- "open Microsoft Excel" → ok target "excel"; "open MS PowerPoint" → ok; "open ms edge" → ok
- Negative pin unchanged: two REAL apps ("open chrome and firefox") still MULTI-blocks

## Risks & Considerations

- Map keys are matched on lowercased consecutive name pairs — no false merges with real two-app requests (e.g., "open word excel" stays two names; only exact family pairs merge).
- The merged single token ("word", "excel") must resolve at launch time — the Hermes agent resolves names to executables (it launched "Word" fine at 06:25), so no additional mapping needed there.
- Sidecar rebuild required for the gate change; no DSL change.

## Open Questions

- None blocking.