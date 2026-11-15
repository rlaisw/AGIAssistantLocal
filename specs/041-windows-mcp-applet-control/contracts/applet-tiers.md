# Contracts: Windows-MCP Applet Control (041)

The four tiers as chat-facing surfaces, each with its gate contract. All details verified against the live 21-tool service surface (2026-11-15, research R1).

## Tier 1 — open (`windows_mcp_open_settings`)

- **In**: a settings-surface request in natural language; `conversation_id` required.
- **Gate**: target must resolve to one entry of the reviewed list (Control Panel applets + `ms-settings:` pages); ambiguous/unknown → ask-back naming the list; one target per request; nothing beyond the identifier is executed.
- **Out**: the window opens on the owner's desktop; `{status: ok, target, display_name}`; audit `windows-mcp-open-<kind>`, decision executed, < 15 s (SC-001).
- **Errors**: unknown target → `blocked` + ask-back; service down / desktop disconnected → the existing honest unavailable envelope with the task recovery; USER_CONTROL → the named deferral.

## Tier 2 — read (`windows_mcp_read_settings`)

- **In**: a settings question ("what's my power plan?"); `conversation_id` required.
- **Gate**: the strict read allowlist (fixed command shapes: adapters, power plan, firewall-rule listing, volumes, system/locale facts); anything unmapped or write-shaped → refused with the list shown; one query per request; no confirmation (reads cannot change state — proven by before/after in the E2E).
- **Out**: genuine values, verbatim, bounded (4000 chars, truncation named); audit `windows-mcp-read-<query>`; < 30 s (SC-002).
- **Errors**: unmapped → `blocked` + the allowlist; the shared down/deferral envelopes.

## Tier 3 — confirmed write (existing `hermes_run_powershell` surface, extended)

- **In**: a settings-change request.
- **Gate (unchanged machinery)**: draft shown verbatim → plain chat confirmation → stored-text execution; a confirm carries no command text; one command per request; re-draft on modification.
- **Never-list (this feature's only security-list change)**: additions — adapter enable/disable, IP/gateway changes, firewall-**profile** disable, remote-access and account changes (the remote-access-cutting class). Boundary per the 2026-11-15 clarification: individual firewall-rule additions/changes are confirmed-only, never-listed nowhere.
- **Out**: genuine result relayed verbatim; audit via the existing classes; < 60 s post-confirm (SC-006).
- **Errors**: never-list → refused at draft and confirm, reason verbatim; unconfirmed → nothing runs (pending state honest); the existing transport/honesty contracts.

## Tier 4 — GUI flow (safe starter set: uninstall, power options, display, sound, date/time)

- **In**: a GUI task ("uninstall Zoom from Programs and Features").
- **Gate**: the assistant proposes the sequence in plain words naming each control and its effect → stored as a `gui_sequence` draft → plain confirmation → step-by-step execution. Stop conditions (all audited, all honest): a credential/password field (refused before any call, value never in the audit); an elevation (UAC) prompt (stop, report, owner approves by hand — never a success claim); a dialog beyond the described sequence (stop, describe, re-confirm); USER_CONTROL exhaustion (the named deferral with the completed-steps report). The never-list binds: a never-list action inside a dialog is refused exactly like a typed command.
- **Out**: completion with the final state relayed (screenshot permitted, sensitive content masked); audit `windows-mcp-gui-*` per step; inside the ~300 s turn budget (SC-004).
- **Scope**: day-one applets per the clarification — appwiz (uninstall), powercfg.cpl, desk/display, mmsys (sound), timedate.cpl; expansion to the full list is a deliberate follow-up.

## Cross-tier contracts

- **No raw passthrough**: the service's `PowerShell` tool (destructiveHint=True) is never registered to the chat; the wrappers are the only path.
- **Honesty**: no claim without the same turn's call; refusals verbatim; recovery hints name real actions.
- **Audit**: every attempt, every tier, every GUI step — append-only, masked sensitive values.
- **Routing**: the Hermes Local Agent lane routes tier phrasings to these tools (DSL rules per tier); bare ambiguous phrasing asks back rather than guessing.
