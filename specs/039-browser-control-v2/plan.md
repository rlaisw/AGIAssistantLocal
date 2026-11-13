# Implementation Plan: Browser Control v2 — full interaction surface (spec 039)

**Branch**: `039-browser-control-v2` | **Date**: 2026-11-13 | **Spec**: [spec.md](./spec.md)

**Input**: `/specs/039-browser-control-v2/spec.md` (with both clarify decisions: one tool per verb; sensitive-field typing allowed), governing `/specs/037-browser-lanes/`, proven proxies `browser_lanes/proxy.py` (navigate/read/click) and `office_lanes/proxy.py`.

## Summary

Extends the browser v2 single-hop proxy to the full control surface: six new per-verb tools (select, type, form, press-key, tabs, wait) plus screenshot-after-every-action, surfacing the browser engine's existing capability — no new engine, no new dependencies. 47 → 53 tools.

## Technical Context

**Language/Version**: Python 3.12 sidecar; the browser engine is the installed Playwright MCP (:3002 via the docker0 bridge, `Host` allowlist override, session-id protocol — all live-proven).

**Primary Dependencies**: Existing only — `browser_lanes/proxy.py` (the persistent SSE session, `call()`, honest envelopes, stale-session recovery — extended, not replaced); the engine's live-verified tool inventory: `browser_select_option`, `browser_type`, `browser_fill_form`, `browser_press_key`, `browser_tabs`, `browser_wait_for`, `browser_hover`, `browser_handle_dialog`, `browser_take_screenshot`.

**Storage**: None new — audit rows (existing JSONL) and screenshots (transient engine artifacts, not persisted server-side).

**Testing**: Unit suites (mock-transport proxy pins); live battery: a real multi-step workflow; A2 injection battery extended to the new verbs.

**Target Platform**: The existing stack; no host changes.

**Performance Goals**: Each verb one engine call (sub-second to seconds); workflow turns bounded by model rounds, not tool time.

**Constraints**: Untrusted-content law unchanged; honest ask-backs on not-found; per-step screenshots mandatory (owner-required, pinned); one tool per verb (clarified); Dify tool-cache staleness rule on publish.

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I. Contract Preservation | ✅ Pass | additive tools only (47→53); navigate/read/click unchanged |
| II. Tests-First | ✅ Pass | proxy verb pins red-first; A2 extension; live workflow battery |
| III. Minimal Dependencies | ✅ Pass | zero new deps — the engine's tools + the existing proxy |
| IV. Honest Answers | ✅ Pass | read-back verification per verb; ask-backs on not-found; honest timeouts |
| V. Spec-Driven Replacement | ✅ Pass | no supersession — extends 037 |

**Post-Phase-1 re-check**: still all-pass — the design is one proxy extension + per-verb handlers + the existing audit machinery.

## Project Structure

```text
specs/039-browser-control-v2/
├── plan.md            # this file
├── research.md       # Phase 0
├── data-model.md     # Phase 1
├── test-plan.md      # unit + e2e + error handling (requested)
├── contracts/        # the six tool schemas
└── quickstart.md

src/agentic_rag_mcp/browser_lanes/proxy.py   # +6 verb methods + screenshot helper
src/agentic_rag_mcp/server.py                  # +6 tools (53 total)
dify/AGIAssistant/AGI_Assistant.yml            # the 6 tool entries + workflow rules
tests/unit/test_browser_control_v2.py          # verb pins
tests/integration/test_browser_a2.py            # extended A2
```

## Test Plan

See **[test-plan.md](./test-plan.md)** — unit suites (per-verb envelopes, ask-backs, read-back verification, name resolution), the live end-to-end workflow battery (navigate → type → select → form → click → read with per-step screenshots), the A2 adversarial extension, and the error-handling matrix (element-not-found, engine down, dialog unexpected, wait timeout, tab missing).

## Complexity Tracking

> Not required — Constitution Check passes with no violations.