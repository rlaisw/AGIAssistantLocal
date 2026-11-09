# Bug Verification: minutes-long wait at the "AI is controlling this computer" stage — documented-limit closure verified against the live graph

- **Slug**: `waiting-long-long-time-at-ai-is-controlling-this-computer-stage`
- **Tested**: 2026-11-09
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The closure's factual claims all hold: the two mitigations (the ~300 s window explanation and the split-request guidance) are live in the **currently published** chatflow graph (Postgres check below), the no-code claim is proven by git (the only working-tree delta since `c3a6f61` is the lifecycle docs themselves), and the reproduction — three live turns earlier today (38 s split / 128 s / 274 s combined, all completing with honest, screenshot-verified results) — ran **after** those mitigations published at 04:03:14, so the evidence is post-mitigation. No regressions: the stack is green. To be explicit: "verified" means the floor is understood, mitigated, and honestly relayed — **not** that the minutes-long wait is gone; that wait is the documented expected behavior until the deterministic-executor spec lands.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-mitigation) | The three live turns of 2026-11-09 (04:04:40 / 04:18:56 / 04:24:02) | **pass** | Actually exercised live earlier today, post-mitigation: the 38 s split step is fast, both combined turns (128 s, 274 s) completed with honest verified results (the 274 s turn read the weather card: 26°C Sunny, HKO) with zero gateway warnings in the window. A **fresh** turn was deliberately not re-driven from this phase — git proves zero source changed since those turns, so a rerun would re-measure the same documented floor at the cost of 2–5 min of controlling the user's desktop (plus arg-strip re-arm / canary-budget risk). |
| Live-graph mitigation check | `docker exec docker-db_postgres-1 psql … SELECT version, created_at, graph::text LIKE '%roughly 300 seconds%' AS has_window_text, graph::text LIKE '%suggest splitting%' AS has_split_text FROM workflows ORDER BY created_at DESC` | **pass** | Current published version `2026-11-09 04:03:14.710407` → `t` / `t`; prior version (03:48:02) → `f` / `f`. Both mitigation bullets went live at 04:03, i.e. **before** all three evidence turns. |
| No-code claim | `git status --short` + `git log --oneline -3` | **pass** | Only untracked file: this bug's `fix.md`; HEAD = `c3a6f61` (the assessment). Zero source deltas since the evidence turns — nothing behaviorally new to re-verify. |
| Stack health (nothing broken) | sidecar `:28080/`, Dify `:80/`, Chat UI `:3000/`, gateway `:8642/v1/models` (house checks from `reboot.sh`) | **pass** | Sidecar ok, Dify ok, Chat UI ok, gateway 200 (bearer key from `[hermes]` config). Note: an initial gateway probe against `127.0.0.1:8642/sse` printed FAIL — wrong address/path for this listener (it binds `172.17.0.1:8642` and serves `/v1/models`); the house-verbatim check passes, so the gateway was never down. |
| New / updated tests | — | **not-run** | The fix added no tests by design (no code changed); the three live turns are the evidence per the assessment. |
| Regression suite | — | **skipped** | No changed files — nothing to regress. Last full run (359 python + 143 UI) was green at `c3a6f61`, the exact HEAD this closure sits on. |
| Lint / type-check | — | **skipped** | No source changes to lint or type-check. |

## Output Excerpts

```
 version           | created_at         | has_window_text | has_split_text
-------------------+--------------------+-----------------+---------------
 2026-11-09 04:03…  | 2026-11-09 04:03…  | t               | t
 2026-11-09 03:48…  | 2026-11-09 03:48…  | f               | f
(2 rows)

?? .specify/bugs/waiting-long-long-time-at-ai-is-controlling-this-computer-stage/fix.md   ← only tree delta
Sidecar: ok   Dify: ok   ChatUI: ok   Gateway: 200
```

## Residual Risks

- The minutes-long wait **will recur** on every heavy combined desktop turn until the deterministic-executor spec lands; this closure verifies the floor is understood, mitigated, and honestly relayed — it does not remove the wait.
- Mid-turn chat feedback remains architecturally blocked (Dify MCP tool calls are opaque); the cycling control notice stays the only visible activity signal, by design (spec 032's 3 s clear is the owner-approved balance).
- Consent idle-waits will keep stretching combined turns while the user is active at the machine — user-safety behavior, deliberately not tuned for speed.
- The 274 s combined turn sits inside the 540 s envelope but the ~300 s Dify plugin-daemon ceiling still exists for heavier turns; the split guidance is the mitigation.
- If a fresh live sample is ever wanted, it costs a 2–5 min desktop-control turn and burns arg-strip canary budget; today's three turns already cover it.

## Recommendation

Close the bug — verified. Every factual claim of the no-code closure checked out against the live published graph, git, and today's live evidence; there is no defect at our layer and no regression surface. The remaining lever for making combined desktop turns fast is the **deterministic sidecar executor** spec (now backed by four lifecycles) — schedule it as spec-sized work; do not reopen this as another bug hunt.
