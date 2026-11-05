# Bug Assessment: Email compose still failing — the wait guidance is falsified; healing tracks canary bursts, not time

- **Slug**: `say-the-local-agent-failed-and-include-the-recovery-hint`
- **Created**: 2026-11-05T09:12+00:00
- **Source**: pasted text (chat transcript of the 09:04 email request and the agent's honest wait-guidance reply)
- **Verdict**: valid — and it supersedes the guidance deployed earlier today in `the-tool-call-failed`
- **Severity**: high — the lane's primary failure mode remains, and the currently deployed mitigation gives advice that is now **provably wrong** on two axes

## Report (verbatim or summarized)

> "The email draft couldn't be created — the Office automation service reported a failure before composing anything."
> "Recovery hint: The agent indicates this is a temporary condition. Once a short window has passed, just ask me to retry…"

The user re-asked the draft (body "test abc v3", subject "hello test v3") at ~09:04; the agent honestly relayed the strip-window wait guidance and gave up — per the deployed 3-canary cap — without composing anything.

## Symptom

The email compose fails whenever the gateway's RunPython channel is in its argument-stripping state; the deployed recovery guidance ("WAIT about 15 minutes … the window will pass") does not work, and the 3-canary retry cap sits below the empirically observed breakthrough threshold, so the agent gives up inside recoverable episodes. Expected: retries that actually flip the channel back, and a compose that succeeds.

## Reproduction (all evidenced from audit + args-capture, 2026-11-05 UTC)

1. 09:04:40 — the user's email turn: strip detected → **3 canaries attempted, none delivered** (the deployed cap) → honest FAILED with the wait guidance. Gateway PID 19277 is **71 minutes old at this point** — the strip persisted across the entire hour, so waiting does not heal it.
2. Channel flip timeline today: stripped 08:12 → **delivered 08:15–08:20** (the 08:15 compose turn ran 10 stripped canaries, then the next calls delivered — draft composed; the 08:20 cycle ran real COM code) → **stripped again 09:04**.
3. Breakthrough thresholds observed across the day: ~5–6 calls (06:29), ~10–14 calls (07:01→07:14), ~10 calls (08:15 mid-turn). Every recovery followed a **burst of canary calls**, never elapsed time alone; conversely, an hour with few calls (08:20→09:04) left the channel stripped.
4. `hermes mcp test` (fresh discovery) does **not** heal the channel (verified at 08:15: 7 echoes after a fresh test).
5. **The "direct-SSE fallback" story is embellishment**: no `office_rpc.py` or any direct-SSE machinery exists on the Windows side (searched `C:\OfficeMCP`, `C:\temp`); the calls that delivered during the "fallback" steps were gateway RunPython retries that broke through. Two prior lifecycles cited this fictional fallback as the savior — the real mechanism is canary-burst breakthroughs.

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_client.py` — `OFFICE_INSTRUCTIONS` SESSION-DEGRADATION RULE: the 3-canary cap ("up to 3 tiny canaries") and the "WAIT about 15 minutes" recovery text — both now falsified (cap too low; wait ineffective)
- `DEPLOY.md` (known-defect row) — "Recovery: WAIT ~15 minutes … the window will pass" — same falsification
- Upstream (`hermes-agent` #148459) — the strip itself: state now characterized as **flipping**, healing on call bursts, persisting ≥71 min without them

## Root Cause Hypothesis

**High confidence on the lane-side mis-fix; the upstream mechanism remains unproven.** The upstream defect flips between stripped and delivered states (possibly a session-pool rotation inside the gateway's MCP client). What is now established empirically: **healing correlates with bursts of argument-carrying calls (observed thresholds 5–15) and not with time** — the channel stayed stripped for an hour with no calls, and every recovery followed a canary burst. Today's deployed mitigation caps retries at 3 (below threshold) and advises waiting (provably ineffective), so user turns fail exactly like this one while the agent at 08:15 — which ignored the cap and kept retrying — broke through and composed the draft.

## Proposed Remediation

**Preferred**: make the rule match the evidence. (1) Raise the canary cap to **15** (empirical threshold plus margin; canaries are cheap — the 08:15 turn's breakthrough burst fit easily inside the 600 s budget, and the bounded-attach rule from `local-agent-failed` keeps the expensive COM steps capped). (2) Replace the wait-based recovery text: instead of "WAIT about 15 minutes", say the channel flips intermittently and **retrying the request (with its canary burst) is what recovers it** — advise the user to "ask again now or in a few minutes" rather than promising a window that doesn't exist. (3) Correct DEPLOY.md's recovery column likewise. (4) Update the #148459 evidence drafts: the flip/burst characterization and the 71-minute persistence replace the time-window model.

**Alternatives**:
- Fix the gateway's MCP client locally in the editable hermes-agent install — remains the durable fix but the mechanism is still unlocalized (session-pool suspicion, unproven); a blind patch risks drift
- A lane-side warm-up script (fire 15 canaries through the gateway after every gateway/OfficeMCP restart) — viable, but it wastes calls during genuinely-stuck states and duplicates what the in-turn rule will now do anyway

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_client.py` — SESSION-DEGRADATION RULE: cap 3 → 15; wait text → retry guidance
- `DEPLOY.md` — known-defect row recovery column
- `tests/unit/test_hermes_office_tool.py` — guard updates (cap value, absence of the "WAIT about 15 minutes" text)

**Tests to add or update**:
- Guard test: instructions contain the 15-canary cap and the retry-based recovery; the falsified "WAIT about 15 minutes" string is **absent**

## Risks & Considerations

- 15 canaries × agent overhead could stretch turns toward the budget on truly-dead channels; the honest stale error remains the backstop after the 15th echo, and the bounded attach keeps the expensive steps capped — worst case ≈ a few minutes
- The flip mechanism is unproven upstream; if the channel ever enters a *permanently* stripped state, the cap increase just delays the honest error — acceptable trade
- The guidance text is user-facing; it must not promise recovery, only describe what evidence supports (burst-retry flips the channel)
- The `local-agent-failed` and `the-tool-call-failed` lifecycles' residual guidance references the time-window model — their test reports should be annotated after this fix lands

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the cap and guidance changes are fully evidence-backed; the upstream mechanism (session pool?) stays an open question for the #148459 issue]
