# Bug Fix: launch-plus-GUI requests split at the gate; the agent completes the desktop followup via WindowsMCP

- **Slug**: `blocked-more-than-one-application-named`
- **Fixed**: 2026-11-06T09:52+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — live-verified end-to-end (Chrome launched, profile picker handled, google.com typed and navigated, screenshot-verified)

## Summary

The launch gate now recognizes a trailing "and/then type/click/press/enter/scroll …" clause as desktop-automation intent rather than a second application: the launch half runs every existing scope check, and the clause rides on the verdict as `desktop_followup`, which the server carries into the directive for the agent to complete with its WindowsMCP tools (focus verification required before typing). "default browser" is one compound target the agent resolves. "open chrome and type www.google.com" went from a false "more than one application named" refusal to a working, verified flow.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_launch_gate.py` | modified | `_RE_GUI_CLAUSE` splits the task at "and/then type/click/press/enter/scroll"; shell/chaining rules apply to **both** halves; `LaunchVerdict.desktop_followup` field; "default browser" compound-target handling; followup carried on all three ok-return paths |
| `src/agentic_rag_mcp/hermes_client.py` | modified | `LAUNCH_INSTRUCTIONS` gained the DESKTOP FOLLOWUP rule: resolve default browser (ask once if ambiguous, never guess), foreground the window, **verify focus before typing** (never type into a wrong window), report what was typed and where; WindowsMCP's control policy (idle wait, AI indicator, user takeover) governs the input |
| `src/agentic_rag_mcp/server.py` | modified | `hermes_launch_app` appends the followup clause to the launch directive |
| `tests/unit/test_hermes_launch_gate.py` | added 4 tests | split-not-two-apps; default-browser compound; two real apps still ask back; followup does not bypass shell/chaining rules |

## Diff Highlights (optional)

```python
_RE_GUI_CLAUSE = re.compile(r"\b(?:and|then)\s+(type|click|press|enter|scroll|type\s+into)\b.*$", re.I)
# gate: followup = task[m.start():]; task = task[:m.start()]
# server: launch_directive = f"{launch_directive} — then, as a desktop followup: {followup}."
```

## Tests Added or Updated

- 4 new gate tests (35 launch-suite tests pass); full suite **337 passed**; ruff — only the 5 pre-existing I001s

## Local Verification

- Gate-level reproduction matrix: `open chrome and type www.google.com` → **ok, target=chrome, followup carried**; `open chrome and firefox` → still MULTI ask-back; shell/chaining in the followup → still blocked
- `deploy redeploy` → ok
- **Live end-to-end (09:47–09:50, the bug's exact request)**: `status ok` — *"Chrome launched fresh via WindowsMCP (no arguments). It opened to the 'Who's using Chrome?' profile picker, so I selected the user's 'Raymond' profile… focused the address bar (ctrl+l), typed www.google.com, and pressed Enter. Verified by screenshot: the tab title is 'Google' and the address bar shows google.com with the Google homepage loaded."* Full audit entry recorded; 152 s turn (desktop-control idle waits + several LLM iterations — no stream cut, well past 120 s, the keep-alive fix holding).

## Deviations from Assessment

- The assessment's open question (URL-typing confirmation) defaulted to **no extra in-chat confirmation**: address-bar typing rides WindowsMCP's own desktop-control policy (10 s idle wait, visible AI indicator, Ctrl+Alt+Shift+Backspace takeover), consistent with every other desktop action — noted here for the owner to tighten later if wanted.
- Scope kept to v1 verbs (type/click/press/enter/scroll); scroll/click rides the same field but the instructions emphasize typing — broader verbs can expand later if asked.

## Follow-ups

- Watch natural "open X and …" turns for parser edge cases (e.g., "open word and type a letter" → the office lane may be the better route for that one; the Dify router decides)
- The 152 s turn duration is the known nested-LLM floor plus desktop-control idle waits — the deterministic-executor follow-up remains the structural fix
- Consider a one-line note in DEPLOY.md's WindowsMCP section that launch-followup typing now flows through this path
