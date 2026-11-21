# MCP-Action — Phase 0 Research

**Date**: 2026-11-20
**Spec**: [spec.md](spec.md)

All Technical Context choices are resolved. The live probes listed at the end verify external contracts before their dependent implementation tasks; they are validation gates, not unresolved design choices.

**Owner-approved T012 amendment**: General-cloud and Hermes passed the live N→N+1 contract. General-local failed to dispatch reliably and is excluded; its original node, prompts, and Answer path are restored unchanged. References below to three answering agents are superseded by the two approved lanes. A deterministic local-model resolver is outside this feature.

## D1 — Expose a fixed-action tool, not arbitrary desktop execution

**Decision**: Add one `mcp_action` tool with `draft`, `confirm`, and `cancel` phases. Its draft accepts only two reviewed action IDs: `windows_default_printer` and `word_printer_duplex`. The server validates a closed parameter schema and generates the effect text and exact offer itself.

**Rationale**: The feature requires that what the user confirmed is structurally what executes. A fixed registry also keeps unsupported Office and Windows procedures manual-only and prevents researched or desktop text from becoming executable instructions.

**Alternatives considered**: Reusing `hermes_run_powershell` or `windows_mcp_gui_flow` was rejected because those accept broader commands or UI sequences and do not provide the required action-specific proposal, expiry, read-back, display, and screenshot contract. A generic natural-language action interpreter was rejected as unsafe and unnecessary for the initial release.

## D2 — Enforce consent with raw response, conversation, turn, and expiry checks

**Decision**: Store one in-memory proposal per conversation with the action, validated parameters, deterministic effect, creating Dify `sys.dialogue_count`, wall-clock creation time, and a 900-second monotonic expiry. Pass raw `sys.query` and `sys.dialogue_count` on every call. Confirmation and cancellation are valid only on the immediately following dialogue turn; the tool itself classifies a small plain-affirmative/plain-negative vocabulary. Any modified or unrecognized response, intervening turn, wrong conversation, expiry, or repeated confirmation fails closed. Atomically reserve/consume a valid proposal before awaiting execution.

**Rationale**: A prompt-only rule cannot invalidate a proposal when an unrelated turn never calls the tool. The next-turn guard, raw-response validation, expiry, and atomic consumption together prevent stale, substituted, and duplicate execution.

**Alternatives considered**: The existing PowerShell draft store has no turn or expiry checks and is insufficient unchanged. A durable database is unnecessary for a single short-lived proposal and would retain consent longer than desired. A deterministic pre-router remains out of scope; if the live Dify turn-counter probe fails, implementation must stop and request owner approval for that different topology rather than weakening the guard.

## D3 — Use CIM for the per-user default printer

**Decision**: Use fixed PowerShell templates that transport the printer name as UTF-8 Base64, enumerate `Win32_Printer`, require exactly one case-insensitive exact name match, and invoke that instance's `SetDefaultPrinter` method. Require return value `0`, then issue a fresh default-printer query and compare the canonical name. Return structured output through a marked Base64 JSON envelope so unrelated CLIXML noise cannot be mistaken for verification. Combine fresh before-state, exact revalidation, mutation when needed, and after-state read-back in one execution call.

**Rationale**: Microsoft documents `Win32_Printer.SetDefaultPrinter` as setting the calling user's default printer and returning zero on success. Exact enumeration avoids wildcard and WQL-injection problems; fresh read-back is stronger evidence than a setter return or screenshot.

**Alternatives considered**: `rundll32 printui.dll` provides weaker structured errors. `Get-Printer -Name` accepts wildcards and is not sufficient for exact validation. Raw string interpolation into PowerShell or WQL was rejected. `Set-Printer -IsDefault` was not selected because the CIM method has an explicit per-user contract.

**Managed-default behavior**: Read `LegacyDefaultPrinterMode` without changing it. When Windows management is present or suspected, include a caveat in the proposal and final result; never flip that setting automatically. A verified immediate default is still reportable, but no persistence beyond the read-back is promised. Unexpected registry values or access errors produce an explicit `unknown` diagnostic, not a fabricated mode.

Source: [Win32_Printer.SetDefaultPrinter](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/setdefaultprinter-method-in-class-win32-printer).

## D4 — Use PrintManagement for Word duplex and surface permission limits

**Decision**: Validate the exact printer, map `long-edge`/`short-edge` to `TwoSidedLongEdge`/`TwoSidedShortEdge`, call `Set-PrintConfiguration -Confirm:$false`, and read the effective mode back with `Get-PrintConfiguration`. Preserve before, requested, and observed values in the result. Do not print a test page, click a duplex checkbox, auto-elevate, or automatically roll back a mismatch.

**Rationale**: Duplex is a printer configuration, not a Word document property. Microsoft documents the two accepted duplex values and states that `Set-PrintConfiguration` requires administrator credentials; access denied must therefore be an honest supported outcome.

**Alternatives considered**: Word GUI automation was rejected because it is fragile and does not prove the effective DEVMODE setting. Automatically changing registry/security settings or elevating was rejected. Treating a setter exception as failure without an after-read was rejected because the actual state may be partially changed and must be reported.

Sources: [Set-PrintConfiguration](https://learn.microsoft.com/en-us/powershell/module/printmanagement/set-printconfiguration?view=windowsserver2025-ps), [Get-PrintConfiguration](https://learn.microsoft.com/en-us/powershell/module/printmanagement/get-printconfiguration?view=windowsserver2025-ps).

## D5 — Display Word through a bounded attach-first COM helper

**Decision**: Add a fixed OfficeMCP `RunPython` template and `OfficeProxy.show_word_print()` that initializes COM, attaches to the running Word instance first, starts Word only when no Word process exists, makes it visible, and calls `Document.PrintPreview()`. Verify `PrintPreview`, `ActiveWindow.View.Type == 4`, window visibility, and actual foreground HWND. Compare document count and `Saved` flags without returning document names; never call `PrintOut`, `Save`, `Close`, `Quit`, or assign `Saved`. If no document exists, create one blank unsaved document only after confirmation and disclose that in the proposal/result.

**Rationale**: Print Preview is a documented non-printing view switch and satisfies the visible Word print-screen requirement without keyboard automation. Attach-first prevents an empty second Word instance from hiding the user's documents. Independent COM/Win32 checks distinguish preview, visibility, and foreground outcomes.

**Alternatives considered**: `Dialogs(...).Show/Display` can block and carry out dialog actions, so it is unsuitable. Ctrl+P and coordinate clicking were rejected. `ExecuteMso("PrintPreviewAndPrint")` is a fallback only for an explicitly unsupported legacy-preview call, never after busy/timeout/unknown outcomes, and requires UI-tree confirmation. Existing OfficeProxy's 180-second retry behavior is not suitable; this helper gets a bounded no-retry path while existing callers retain their defaults.

Sources: [Document.PrintPreview](https://learn.microsoft.com/en-us/office/vba/api/word.document.printpreview), [Word View.Type](https://learn.microsoft.com/en-us/office/vba/api/word.view.type), [Document.Saved](https://learn.microsoft.com/en-us/office/vba/api/word.document.saved).

## D6 — Verify the visible screen before capturing evidence

**Decision**: Add the reviewed `ms-settings:printers` target. After opening Settings, use host-side `WaitFor("Printers & scanners")` to verify the printer page before declaring it displayed. For Word, require the COM preview and foreground checks. Capture only after the relevant display is verified; otherwise return screenshot `skipped-display-unverified` rather than an image of an unrelated window. Use active-window bounds for regional capture when available; otherwise disclose full-display capture.

**Rationale**: A successful open command does not prove the intended page is visible, and a screenshot of the wrong window is misleading and may expose unrelated content.

**Alternatives considered**: Treating `Start-Process` or `ExecuteMso` returning without an exception as display success was rejected. Always taking a full-desktop screenshot was rejected when a reliable target cannot be established.

## D7 — Deliver screenshots through short-lived capability URLs

**Decision**: Add opt-in MCP `ImageContent` extraction to `windows_mcp.call_tool`, preserving existing responses by default. Require exactly one valid PNG/JPEG image, cap decoded bytes at 10 MiB, and store it in a private container-local temporary directory. Return only an unguessable 256-bit URL token and expiry metadata; never return Base64, local paths, or desktop text. Serve `GET /mcp-action/screenshots/{token}` with `Cache-Control: no-store`, `nosniff`, inline disposition, and cross-origin headers required by chat/PDF embedding.

**Rationale**: The chat stream already supports Markdown images but not native MCP image events. A temporary URL avoids Base64 in Dify history and requires no chat-renderer change. The existing `/exports` route is PPTX-only and permanent, so it cannot be reused.

**Lifetime**: TTL is 900 seconds from capture; a lifespan janitor sweeps every 30 seconds, route access after expiry deletes and returns 404, and startup/shutdown sweeps remove leftovers. GET does not renew expiry or delete after first read. The public origin is derived from `ppt_exports_url_base` like infographic URLs.

**Security**: Tokens match exactly `[A-Za-z0-9_-]{43}`; malformed, unknown, and expired tokens are indistinguishable 404s. Directory/file modes are `0700`/`0600`; validate image magic bytes rather than trusting MIME. Add access-log token redaction and audit only capture/delivery outcomes, never token, URL, path, bytes, or desktop text. Preserve upstream `no-store` in the existing chat image proxy instead of replacing it with one-hour public caching; ordinary remote images retain current behavior.

**Alternatives considered**: Native MCP images or data URIs would require Dify/frontend changes and pollute history. Permanent audit artifacts conflict with the clarification. Authenticated same-origin proxying is deferred because this is the existing single-user local-trust deployment; anyone possessing the capability URL can fetch it until expiry.

## D8 — Serialize execution with one desktop lock and a bounded total budget

**Decision**: Use one server-wide `asyncio.Lock` for confirmed MCP-Action execution and a separate short-duration state lock that is never held across `await`. Hold the desktop lock from fresh before-read through mutation, after-read, display verification, and screenshot capture. Use a 240-second total confirmation budget including queueing; start an action only if its full reviewed 60/90-second action budget remains. Return queue wait and execution time separately. A queued timeout consumes the proposal without executing and requires a fresh draft.

**Rationale**: This is the smallest mechanism that prevents cross-conversation settings/focus/screenshot interference while staying below Dify's approximately 300-second tool ceiling. A background job and polling API are unnecessary for the two bounded initial actions.

**Alternatives considered**: Per-action locks still allow focus conflicts. A background queue improves immediate waiting notices but adds job lifecycle complexity. A Windows-host mutex is unnecessary for the current single sidecar process; multi-process deployment would require a future host-level lock. Do not cancel an underlying host call merely because a client timed out while it may still be running.

## D9 — Wire General-cloud and Hermes and extend the shared honesty guard

**Decision**: Register `mcp_action` on `agentic_strategy` and `hermes_agent`, not on `agentic_strategy_local` or PPT-Master. Add the same narrow protocol to both approved prompts: ask-first first, manual steps, draft only for reviewed actions, exact server-returned offer, next-turn confirm/cancel with raw query/turn, confirmation priority for help-affirmative replies, no skill-loop detour, and no generic router change. Add `mcp_action` to replay-gated tools so a saved skill cannot pre-confirm it.

**Rationale**: Ordinary how-to and confirmation turns can remain in General-cloud or Hermes rather than forcing a route. Globally rerouting every yes/no would break unrelated follow-ups. General-local is excluded because it failed the live dispatch contract.

**Honesty containment**: Reuse the existing multi-input `honesty_check` topology for both approved agents. Keep existing Hermes claims lane-specific, but add MCP-action-specific detection: exact offer requires a real `mcp_action` pending result; execution/verification/display/screenshot claims require the corresponding result; research-only calls do not satisfy either; leaked `mcp_action` invocations are replaced. A provisional draft's manual steps are not execution evidence; raw honesty diagnostics must not be returned as the user-facing answer. Existing Hermes honesty cases must remain green.

**Alternatives considered**: Hermes-only wiring misses General-cloud confirmations. Wiring General-local failed the live dispatch contract. Prompt-only anti-fabrication leaves General outputs unguarded. Two separate new guards duplicate the same DSL logic and increase drift.

## D10 — Make errors structured, partial-state-aware, and privacy-safe

**Decision**: Every phase returns a bounded envelope; unexpected internal errors become sanitized `error` results with no fabricated success. Separate proposal, queue, mutation, verification, display, and screenshot outcomes. Read actual state after setter errors when possible. A verified setting with display/screenshot failure is `partial`; a read-back mismatch is never success. Audit phase, conversation ID, action ID, outcome, and timings, but no Base64, image token/path/URL, document names, raw desktop content, or unconstrained stderr.

**Rationale**: The setting may already have changed when a later step fails. Independent outcome fields and after-reads prevent both false success and false claims that nothing changed.

**Alternatives considered**: A single success/error flag loses partial state. Automatic rollback is not part of the confirmed proposal and could compound an unknown failure. Raw exception/CLIXML propagation was rejected in favor of bounded honest reasons plus audit detail.

## Live contract probes required before dependent implementation

1. **Dify turn semantics**: prove a draft sees dialogue count `N` and the next user turn sees `N+1` for General-cloud and Hermes. If unavailable or not monotonic, stop before execution wiring and request approval for a deterministic resolver.
2. **Shared guard topology**: prove one multi-input code node selects exactly the active agent's answer/items and that unexecuted branches are empty without breaking the existing Hermes path.
3. **Windows printer contract**: with owner approval and a disposable printer, verify exact CIM matching, default read-back, managed-default interpretation, duplex permissions, and setter/read-back envelopes. No test page or auto-elevation.
4. **Word display contract**: with an unsaved disposable document, prove PrintPreview/View.Type/HWND/document preservation and the bounded no-retry behavior. Exercise Backstage only if legacy preview is genuinely unsupported.
5. **Screenshot contract**: capture one real mixed text/image MCP result, verify MIME/Base64 extraction, then verify URL bytes, headers, expiry with a fake clock in tests, and token-free logs/audit.

No `NEEDS CLARIFICATION` markers remain for planning.
