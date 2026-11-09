# Bug Fix: every configurable ceiling raised — the binding 300.000 s cut is hardcoded in the Dify plugin-daemon binary

- **Slug**: `the-local-agent-hit-a-transport-error`
- **Fixed**: 2026-11-09T02:00+00:00 (cycle 3; supersedes cycles 1–2, preserved in git)
- **Assessment**: ./assessment.md
- **Status**: partial — all env-configurable ceilings raised and verified live; the binding 300.000 s constant is inside the compiled Dify plugin-daemon and not reachable by configuration

## Summary

This cycle raised the last env-reachable ceiling (`DIFY_BACKWARDS_INVOCATION_READ/WRITE_TIMEOUT`) — with one empirically-confirmed unit correction (the knob is in **milliseconds**: the naive 600 broke every LLM read at 0.6 s; 600000 = 600 s restored the stack and is now live) — but the decisive >300 s sample still cut at **exactly 300.03 s**, proving the binding constant lives in the compiled daemon code itself. Every failure remains honest (accurate relay, re-ask hint, no silent kills).

## Changes

| File / surface | Change | Notes |
|------|--------|-------|
| `/home/administrator/dify/docker/docker-compose.yaml` (committed to the Dify repo) | modified | `DIFY_BACKWARDS_INVOCATION_READ_TIMEOUT` / `WRITE_TIMEOUT: ${…:-600000}` with a why-comment documenting the millisecond unit and the 600-misstep |
| Live daemon | recreated ×2 | First with 600 (broke LLM reads at 0.6 s — unit is ms), then 600000; env verified: both at 600000 |
| `DEPLOY.md` | unchanged this cycle | The cycle-2 note covers the recreate requirement; the ms-unit discovery is recorded here and in the compose comment |

## Diff Highlights (optional)

```yaml
# plugin_daemon environment:
DIFY_BACKWARDS_INVOCATION_READ_TIMEOUT: ${DIFY_BACKWARDS_INVOCATION_READ_TIMEOUT:-600000}  # ms!
DIFY_BACKWARDS_INVOCATION_WRITE_TIMEOUT: ${DIFY_BACKWARDS_INVOCATION_WRITE_TIMEOUT:-600000}
```

## Tests Added or Updated

- No repo code; the empirical unit test was the production stack itself (600 → total LLM-read failure → 600000 → recovery), the strongest possible evidence for the millisecond unit

## Local Verification

- Env chain fully verified live: provider row 600/600, plugin-process env 600 (`/proc`), daemon env 600000 (after recreate); chat recovered post-correction ("Say OK" and an "open notepad" turn streamed)
- **Decisive sample (wallpaper turn, +310 s wall)**: sidecar stream ran 01:48:50.278 → terminated 01:53:50.307 = **300.03 s** — the identical cut, entirely under the 600000 daemon. The binding 300.000 s is therefore not the row, not the plugin library, not the backwards-invocation env — it is compiled into the Dify plugin-daemon invoke/relay path
- Incidental finding: the api's gunicorn runs with the default 2-second keep-alive (no `--keep-alive` in the entrypoint) — the immediate post-recreate "read llm model failed / use of closed network connection" flakiness class; transient, recovered on its own
- One test turn failed on an unrelated OpenRouter blip ("Duplicate Kimi K3 argument") — honestly relayed by the lane
- `pytest tests/unit` → 354 passed (no repo code touched)

## Deviations from Assessment

- The assessment's remediation (set the two daemon knobs to 600) was applied but its unit assumption was wrong: the knobs are **milliseconds**, and 600 (=0.6 s) broke all plugin→api LLM reads — corrected to 600000 in the same cycle, with the failure/recovery sequence captured as the unit proof
- The remediation did not remove the cut: the binding 300.000 s survived every configurable ceiling, locating it in non-configurable daemon code — this is a **root-cause boundary**, not a fix failure per se; the assessment's mechanism section is now empirically closed

## Follow-ups

- **Upstream issue (recommended)**: file against `langgenius/dify-plugin-daemon` with the precise evidence — a tool invocation through the agent lane cuts its stream at exactly 300.000 s regardless of: `tool_mcp_providers.timeout/sse_read_timeout=600`, plugin env `MAX_REQUEST_TIMEOUT/MAX_INVOCATION_TIMEOUT=600`, daemon env `DIFY_BACKWARDS_INVOCATION_READ/WRITE_TIMEOUT=600000` (ms), daemon restarts. Ask for the invoke-path timeout to be env-configurable (or a keep-alive/ping on the invoke response stream)
- **Operating posture meanwhile**: chat-side `hermes_*` tool calls cap at ~300 s. All failures are honest (accurate relay + re-ask hint — verified live); the FASTEST-PATH guidance keeps most turns well under 300 s; heavy navigation should be split ("open X", then "show me Y") — which also matches the 540 s direct/battery envelope
- The 600000 values stay in place (harmless, and correct if a future daemon version honors them); the DEPLOY.md re-check command covers all three knob families after Dify upgrades
- Consider raising gunicorn's keep-alive upstream too (the 2 s default produced the transient closed-connection flakiness after daemon restarts)
