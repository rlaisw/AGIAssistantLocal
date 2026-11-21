# Implementation Plan: MCP-Action — Confirmed Desktop Automation

**Branch**: `047-mcp-action` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/047-mcp-action/spec.md`

## Summary

Add one reviewed, conversation-scoped `mcp_action` tool that bridges existing manual Office/Windows instructions to an optional confirmed action. The initial release supports only Windows default-printer changes and Word printer-duplex changes. Drafting stores an exact 15-minute proposal without mutation; only a plain affirmative on the immediately following dialogue turn can execute it. Fixed CIM/PrintManagement handlers perform fresh before/after reads, one desktop-wide lock serializes execution, the relevant Settings or Word Print Preview screen is verified and displayed, and a temporary screenshot URL is returned for inline chat evidence. Unsupported procedures and all unrelated behavior remain unchanged.

## Technical Context

**Language/Version**: Python 3.12+; existing TypeScript/Vitest only for the small image-proxy cache-policy correction and its test

**Primary Dependencies**: Existing FastMCP (`mcp>=1.12,<2`), `asyncio`, `httpx`, Starlette/Uvicorn, Windows-MCP client/lane, OfficeMCP `RunPython` proxy, Dify Chatflow, and existing chat Markdown image rendering; no new runtime dependency

**Storage**: In-memory pending proposals; private container-local `/tmp` screenshot files with 15-minute TTL; existing append-only sanitized audit log; no database or migration

**Testing**: `pytest` + `pytest-asyncio` with mocked trust boundaries; Starlette route/contract tests; Vitest; owner-present live Windows/Office integration tests; Dify + CDP end-to-end acceptance

**Target Platform**: Single WSL2/Docker sidecar controlling one interactive Windows 11 desktop through the existing bridges; Microsoft Word and PrintManagement available on the Windows host

**Project Type**: Local web-service/chatflow desktop automation with additive backend and DSL changes

**Performance Goals**: Default-printer execution + verification + display within 60 seconds for at least 95% of eligible runs; Word duplex within 90 seconds; queue wait reported separately; total queue + action budget below 240 seconds

**Constraints**: No mutation/display before explicit next-turn yes; 900-second proposal and screenshot TTL; one confirmed action per desktop at a time; no arbitrary PowerShell/GUI/COM input; no auto-elevation or direct registry writes; managed-default side effects are disclosed and never enabled or disabled silently; no Base64 in chat history/audit; no automatic rollback or test printing; existing tool schemas remain compatible

**Scale/Scope**: One sidecar process, one Windows desktop, one active execution across conversations, one pending proposal per conversation, two reviewed action types; additional actions require separate reviewed handlers

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Contract Preservation — PASS**: `mcp_action` is additive. Windows-MCP image extraction is opt-in and existing response shapes remain unchanged by default. OfficeProxy no-retry/bounded behavior is local to the new helper; existing public tools and callers retain their contracts.
- **Tests-First — PASS**: [quickstart.md](quickstart.md) defines red-first unit, contract, integration, Dify, and live E2E checks before implementation, including refusal, partial-state, concurrency, expiry, privacy, and regression cases.
- **Minimal Dependencies — PASS**: Uses the standard library and installed MCP/HTTP/Starlette/test infrastructure. No new service, database, GUI framework, or package is introduced.
- **Honest Answers — PASS**: Read-back is authoritative; screenshots are supporting evidence only. Setter, verification, queue, display, screenshot, permission, and unknown outcomes are separately reported. Dify's honesty guard is extended for the new tool.
- **Spec-Driven Replacement — PASS / NOT APPLICABLE**: This feature adds a lane and does not retire an existing one. Existing direct-action workflows remain intact.
- **Quality Gates — PASS**: Performance is measured from execution start; queueing is separate. Live external-contract probes precede dependent implementation, and the full existing Python/frontend suites must remain green.

## Project Structure

### Documentation (this feature)

```text
specs/047-mcp-action/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── mcp-action.md
│   └── screenshot-route.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 only; not created by /speckit.plan
```

### Source Code (repository root)

```text
src/agentic_rag_mcp/
├── mcp_action/
│   ├── __init__.py
│   ├── state.py          # proposals, raw-response/turn/expiry validation, atomic consumption
│   ├── actions.py        # two fixed handlers, PowerShell templates, structured read-back
│   ├── service.py        # draft/confirm/cancel orchestration, desktop lock, outcomes/audit
│   └── screenshots.py    # image validation, capability tokens, TTL storage/janitor
├── server.py             # additive mcp_tool registration and service lifetime
├── windows_mcp/
│   ├── client.py         # opt-in ImageContent extraction; bounded consent behavior
│   └── targets.py        # reviewed ms-settings:printers target
├── office_lanes/proxy.py # fixed attach-first Word PrintPreview helper
├── skill_manager/executor.py # prevent skill replay from bypassing live confirmation
└── logging_setup.py      # redact screenshot capability tokens

dify/
├── AGIAssistant/AGI_Assistant.yml # General-cloud + Hermes tool/prompt wirings + shared honesty guard
└── docker/mcp-server/server.py    # temporary screenshot GET route + janitor lifetime

ai-chat-landing/
├── app/api/image-proxy/route.ts   # preserve upstream no-store; default policy unchanged
├── app/api/image-proxy/route.test.ts # no-store propagation + unchanged default policy
├── lib/follow-up.test.ts          # exact-offer renderer pin; production renderer unchanged
└── scripts/mcp-action-check.mjs   # optional CDP acceptance driver

tests/
├── unit/
│   ├── test_mcp_action_state.py
│   ├── test_mcp_action_actions.py
│   ├── test_mcp_action_tool.py
│   ├── test_mcp_action_concurrency.py
│   ├── test_mcp_action_dsl.py
│   ├── test_mcp_action_screenshots.py
│   ├── test_windows_mcp_lane.py
│   ├── test_office_v2.py
│   ├── test_logging_setup.py
│   └── test_skill_executor.py
├── contract/
│   ├── test_mcp_contract.py
│   └── test_mcp_action_screenshot_route.py
└── integration/
    ├── test_mcp_action_e2e.py     # explicit owner-present/non-CI live battery
    └── test_mcp_action_dify_contract.py # opt-in lane, turn, and newline consent contract
```

**Structure Decision**: Keep all proposal/action/orchestration code in one feature package and make only additive wiring changes to existing Windows, Office, HTTP, Dify, skill, logging, and image-proxy modules. No production chat-renderer or intent-router change is planned. Any newly discovered dependency outside this tree requires owner approval before editing.

## Implementation Sequence

1. **Prove external contracts and write failing tests**: Probe Dify dialogue-count/multi-input guard behavior, one real screenshot content shape, and owner-approved printer/Word behavior. Create sanitized fixtures and the unit/contract/E2E skeletons. Stop if the turn counter cannot enforce next-turn consent.
2. **Implement proposal state and public tool contract**: Closed schemas, deterministic effects/offers, raw-response classification, next-turn and expiry enforcement, supersession/cancellation, atomic consumption, sanitized statuses, and audit events. Draft tests must prove zero executor/display/screenshot calls.
3. **Implement the two fixed action handlers**: Exact printer validation, Base64 transport/structured output, default-printer CIM call, duplex PrintManagement call, fresh before/after reads, already-active handling, managed-default caveat, and partial-state-aware errors.
4. **Implement serialization, display, and evidence**: Desktop-wide `asyncio.Lock`, total/remaining budgets, Settings page + host-side `WaitFor` printer-page verification, attach-first Word Print Preview + document preservation (called through `asyncio.to_thread` with its own bounded no-retry path so the event loop remains responsive), opt-in image extraction, temporary storage/route/janitor, log redaction, and proxy `no-store` propagation.
5. **Wire Dify without changing general routing**: Add the tool/protocol to General-cloud Agentic Strategy and Hermes only, exempt the deterministic flow from skill replay, and route those two outputs through the extended existing honesty guard. General-local retains its original node and Answer path unchanged. Preserve generic follow-ups and all prior Hermes honesty cases.
6. **Deploy and run acceptance**: Run all unit/contract/frontend suites, rebuild the sidecar, publish both Dify apps by ID, run the headless battery and owner-present E2E matrix, verify screenshots and expiry/privacy, then restore original printer settings and close only test-owned windows.

## Error-Handling Design

| Stage | Condition | Required result and side-effect policy |
|---|---|---|
| Draft | Missing/ambiguous printer or orientation | `ask-back`; no proposal eligible for execution and no mutation |
| Draft | Unsupported action, unknown parameter, free-form executable text | `unsupported` or bounded `error`; no offer and no mutation |
| Draft validation | Windows/Office read-only validation unavailable | Honest validation error; do not offer an unvalidated executable proposal |
| Confirm | Wrong conversation, orphan/repeated yes | `blocked`; do not consume another conversation's proposal and do not execute |
| Confirm | Modified response, intervening turn, or age ≥900 seconds | Invalidate the stored proposal; require a fresh draft; no execution |
| Cancel | Plain no/cancel on the next turn | `cancelled`; consume proposal; zero executor/display/screenshot calls |
| Queue | Full action budget cannot remain before the 240-second total deadline | `queued-timeout`; consume proposal without executing; active action continues undisturbed |
| Mutation | Printer removed, access denied, unsupported duplex, nonzero setter result | Attempt an after-read; return actual observed state and bounded reason; never auto-elevate or roll back |
| Verification | Missing/malformed output or after-state mismatch | `error` with `verification:"mismatch"` or `"unavailable"`; never claim success |
| Display | Word busy/modal, Settings not confirmed, foreground denied, elevation prompt | Stop or return `partial` when the setting is independently verified; no blind GUI fallback |
| Screenshot | No/invalid/oversized image, storage failure, display unverified | `attempted-but-failed` or `skipped-display-unverified`; preserve separately verified setting result |
| Transport/internal | Timeout, CLIXML/malformed payload, unexpected exception | Sanitize the error; attempt safe after-read; do not retry an unknown mutation or release the desktop lock while host work may still run |
| Evidence retrieval | Malformed/unknown/expired screenshot token | Indistinguishable 404 + `no-store`; no image bytes or metadata leakage |

Every non-trivial error path has a corresponding test in [quickstart.md](quickstart.md). Audit records phase/action/outcome/timings and conversation ID, never executable Base64 payloads, screenshot bytes/tokens/paths/URLs, document names, raw desktop content, or unconstrained stderr.

## Post-Design Constitution Re-check

All pre-design gates still pass. The selected design adds no dependency or breaking contract, preserves existing lanes, defines red-first checks for every new branch, and makes partial/unknown outcomes explicit. No Complexity Tracking justification is required.
