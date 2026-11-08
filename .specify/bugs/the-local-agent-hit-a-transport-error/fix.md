# Bug Fix: Dify MCP provider timeout 300 → 600 — the chat-side ceiling now sits above the sidecar's honest envelope

- **Slug**: `the-local-agent-hit-a-transport-error`
- **Fixed**: 2026-11-08T10:05+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — live-verified end-to-end on the exact previously-failing request

## Summary

The `tool_mcp_providers` row for `agentic-rag` now carries `timeout = 600` and `sse_read_timeout = 600` (was 300/300 — the exact 300-second ceiling that cut chat-side tool streams with "peer closed connection"), loaded via a healthy `docker-api-1` restart. The client ceiling now sits above the sidecar's 540 s honest envelope, so chat turns end like direct calls: success or the truthful verdict — and the exact request that produced the transport error completed end-to-end on the first post-fix try.

## Changes

| File / surface | Change | Notes |
|------|--------|-------|
| Dify DB `tool_mcp_providers` (live) | `timeout` 300 → 600; `sse_read_timeout` 300 → 600 | The chat-side MCP client's ceilings; both must sit above the sidecar's 540 s envelope |
| `docker-api-1` | restarted | Loads the row (brief chat interruption); healthy after 39 s |
| `DEPLOY.md` | updated | The re-apply note now carries the 600/600 value, the `sse_read_timeout` field, the api-restart step, and the rationale (600 > 540 envelope so the sidecar's honest verdict always wins) |

## Diff Highlights (optional)

```sql
UPDATE tool_mcp_providers SET timeout = 600, sse_read_timeout = 600 WHERE name = 'agentic-rag';
-- 600 (not 300): must sit ABOVE the sidecar's 540s honest envelope so chat
-- turns end in a truthful verdict, not a 300s client cut.
```

## Tests Added or Updated

- No repo code changed (live config + docs); the suite ran green for confirmation
- Live-graph checks: row verified `600|600`; api-1 healthy; DEPLOY.md note grep confirms the new command

## Local Verification

- Row: `SELECT timeout, sse_read_timeout` → `600|600`; `docker-api-1` Up (healthy); Dify root 307 after restart
- **Live e2e (09:57:09 → 10:00:52)**: the exact request from the bug report — *"open control panel , display wallpaper setting"* — through the **chat** (the path that died at 09:47): turn `status=normal`, **"Launch: SUCCESS"** — Control Panel opened fresh (pid 12172), and the agent used the fastest path (Run box → Settings → Personalization → **Background**, focused and maximized, showing Picture/Solid color/Slideshow/Spotlight), Control Panel open behind it. Full audit entry (10:00:50, executed). **No "peer closed connection"** — the pre-fix turn at this very request died at exactly 300 s with a transport error
- Honest note: this sample completed in 224 s (the FASTEST-PATH guidance from `desktop-followup-timeout-600s` visibly sped it up versus the earlier attempt) — so the >300 s stream case is config-proven (the row that produced the measured 300.000 s cut is now 600) with the first natural >300 s turn as the behavioral sample to come

## Deviations from Assessment

- Also raised `sse_read_timeout` (300 → 600) — a one-line addition beyond the assessment's `timeout`-only change: the assessment measured `timeout` as the operative cut, but `sse_read_timeout` carried the same 300 value and would have become the binding ceiling once `timeout` rose; raising both removes the whole 300 s class from the row.

## Follow-ups

- The first natural >300 s chat turn (long navigation under consent waits) will provide the behavioral sample for the >300 s stream case; with the envelope at 540 s, its honest worst case is the sidecar's "try a smaller task" verdict
- The DEPLOY.md re-apply note is the persistence mechanism for both row values — provider re-syncs (`sync-tools`) may reset them; re-apply + api restart per the note
- Your desktop now has the Settings → Personalization → Background page focused (from the verification turn) — pick a wallpaper or close it
