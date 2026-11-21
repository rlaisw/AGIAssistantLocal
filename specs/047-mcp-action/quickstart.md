# MCP-Action — Validation and Test Plan

**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)
**Contracts**: [mcp_action](contracts/mcp-action.md) · [screenshot route](contracts/screenshot-route.md)

This is the runnable unit, contract, integration, and end-to-end validation guide for MCP-Action. It is a test plan, not implementation code.

## 1. Test policy and safety

1. **Red first**: Add each test before its implementation and confirm it fails for the expected missing behavior. Do not weaken a test to accommodate an implementation defect.
2. **Deterministic CI**: Unit and contract tests mock every Windows-MCP, OfficeMCP, Dify, clock, filesystem, and network trust boundary. They must not change a real desktop or require live services.
3. **Owner-present live tests**: Live printer and Word tests run only with the owner present and an interactive Windows desktop. They are excluded from normal CI.
4. Use at least two owner-approved test printers, including one duplex-capable printer. Do not use a production physical printer for error injection and never print a test page.
5. Record the original default printer and duplex configuration before every live scenario and restore them in `finally`, even after a failed assertion. Report restoration separately.
6. Use a disposable unsaved Word document containing a harmless marker. Never close or save it during the action. The test harness may close only windows/documents it created after the owner confirms the marker is preserved.
7. Do not auto-elevate. Run the duplex success case only when the interactive user already has the required permission; otherwise use it as the expected access-denied case.
8. Do not wait 15 minutes in routine tests. Proposal and screenshot expiry use fake clocks; one optional owner-approved live 15-minute check is sufficient.
9. Use fresh Dify conversations for offer/confirmation tests. Verify unrelated generic “Want me to…?” follow-ups separately so yes/no routing is not hijacked.
10. No screenshot bytes, capability tokens, local paths, document names, raw desktop text, credentials, or executable payloads may appear in persistent logs or audit records.

## 2. Prerequisites

- Repository virtual environment and package installation are present.
- Sidecar, Dify, Windows-MCP, OfficeMCP, WSL port bridges, and the interactive Windows desktop are healthy.
- Word is installed and can be automated as the same interactive user.
- Chat UI development server and CDP Chrome are available for the browser acceptance script.
- Dify deployment credentials remain in the existing secret config and are never printed.
- Live contract probes in [research.md](research.md) pass before dependent implementation:
  - `sys.dialogue_count` is `N` at draft and `N+1` on the next user turn for General-cloud and Hermes. Owner-approved scope excludes General-local, whose original behavior must remain unchanged.
  - The shared multi-input honesty node selects only the active agent output.
  - One real Windows-MCP screenshot produces a valid MCP image block.
  - Printer and Word read-back/display behavior matches the fixed-handler assumptions.

If the turn-counter probe fails, stop execution wiring and request approval for a different deterministic resolver. Do not substitute prompt-only stale-offer handling.

## 3. Unit tests

### Proposal, consent, and tool behavior

| ID | Test case | Expected result |
|---|---|---|
| U01 | Valid default-printer and Word-duplex drafts | Exact server-generated effect and offer, `expires_in_s=900`, one stored proposal; zero mutation, display, Office, or screenshot calls |
| U02 | Missing printer/orientation, ambiguous target, unknown action, unknown parameter key, executable/free-form action text | `ask-back`, `unsupported`, or bounded `error`; no executable proposal and no host calls beyond permitted read-only validation |
| U03 | Confirm/cancel supplies replacement `action_id` or `parameters` | Rejected; stored proposal cannot be substituted |
| U04 | Plain affirmative/help-affirmative and plain negative/cancel vocabulary, casing, surrounding whitespace/punctuation | Defined responses resolve the proposal, including `yes, help to do it`; modified replies still fail closed |
| U05 | “Yes, but use another printer”, changed orientation, or any unrecognized response | Old proposal invalidated, no execution, fresh draft required |
| U06 | Confirm/cancel at draft turn `N`, next turn `N+1`, and later turn `N+2` | Only `N+1` is eligible; an intervening unrelated turn invalidates the proposal |
| U07 | Fake-clock ages 899.99 and 900 seconds | First is eligible, second expires without execution; later yes cannot revive it |
| U08 | Wrong conversation, orphan yes, repeated yes, yes after cancellation/error/queue timeout | `blocked`; no execution and no consumption of another conversation's proposal |
| U09 | Two concurrent confirms for one proposal | Atomic reservation permits exactly one execution; the other receives no-pending/blocked |
| U10 | New draft replaces old; two conversations hold independent proposals; restart/new empty store | Superseded and restarted proposals fail closed without affecting the other conversation |

### Fixed actions and verification

| ID | Test case | Expected result |
|---|---|---|
| U11 | Printer names containing wildcards, quotes, `$()`, backticks, Unicode, smart quotes, and near-duplicate names | UTF-8 transport remains literal; exactly one case-insensitive exact match is required; no injected command executes |
| U12 | Zero/multiple matches, printer removed between draft and execution, no current default | Bounded validation/execution error; no substitute target |
| U13 | Default-printer setter returns zero/nonzero, already active, after-read matches/mismatches | Zero + fresh match is required; already active is `ok/changed:false`; mismatch is never success |
| U14 | Managed-default values absent/0/1/unexpected and registry read failure | Only the documented proposal caveat/diagnostic changes; never a registry write or fabricated mode |
| U15 | Duplex long/short mapping, unsupported mode/printer, access denied, missing PrintManagement | Only the two reviewed modes are emitted; honest error; no elevation or test page |
| U16 | Setter throws before/after an actual change, malformed JSON, CLIXML before/after the marker | Attempt after-read when possible; parse only the marked structured result; report actual/unknown partial state without raw noise |
| U17 | Unexpected internal exception at each action stage | Sanitized `error`, no fabricated success, safe after-read where possible, and no secret/path/payload leakage |

### Concurrency, display, and evidence

| ID | Test case | Expected result |
|---|---|---|
| U18 | Two conversations confirm with executor gated by `asyncio.Event` | `max_active == 1`; second queue wait is reported separately; display and capture finish before lock release |
| U19 | Queue leaves insufficient full 60/90-second budget, executor raises, transport outcome unknown | Queued proposal times out without execution; exceptions release lock only after host work is settled; no blind retry |
| U20 | Settings opens but host-side `WaitFor("Printers & scanners")` fails or page markers are missing | Display is unverified/failed; screenshot is skipped; verified setting result remains separate |
| U21 | Word running/COM attach succeeds, Word absent, Word running but not COM-registered | Attach-first; Dispatch only when no Word process exists; never start an empty second instance to hide user documents |
| U22 | No Word document, unsaved disposable document, preview foreground denied | Blank creation is disclosed; existing document count/Saved flags remain unchanged; preview and foreground outcomes are distinct |
| U23 | Word busy/modal COM rejection, timeout, unsupported legacy preview | No Backstage/GUI fallback after busy/unknown outcome; bounded no-retry error; fallback only for explicit unsupported preview and requires UI-tree proof |
| U24 | Mixed text/image MCP result, default `include_images=False`, missing/multiple/malformed/oversized images | Existing callers remain unchanged; opt-in accepts exactly one valid image and honestly rejects the others |
| U25 | Screenshot token grammar, PNG/JPEG sniffing, 10 MiB cap, file modes, traversal, fake-clock TTL/janitor/startup cleanup, `capture_scope` and region fallback | Valid bytes receive a capability URL; expiry is absolute, GET does not renew, invalid/expired tokens are 404, leftovers are removed; foreground-window/full-display scope is disclosed |
| U26 | Audit and access logs after success and every failure | Required phase/action/timing/conversation fields exist; no raw query, Base64, token, URL, path, document name, desktop text, or stderr payload persists |
| U27 | Chat image proxy receives upstream `no-store` and an ordinary cacheable image | `no-store` is preserved for screenshots; ordinary images retain `public, max-age=3600` |
| U28 | Exact offer passes through `splitFollowUp`; DSL tool/prompt/guard assertions | Existing renderer styles the offer; General-cloud and Hermes are wired, General-local/PPT nodes are not, generic yes/no is unaffected, research-only and leaked calls cannot satisfy the guard |
| U29 | Existing Hermes fabrication/honest-draft and skill-replay suites | All prior cases pass; `mcp_action` cannot be replayed as pre-confirmed |
| U30 | Dify runtime arguments use `auto: 0` variable selectors and a raw query contains newlines/quotes | Exact conversation/query/turn reach `mcp_action`; tool JSON never collapses to a string |
| U31 | Plain affirmative is mistakenly sent as a `draft` while a proposal is pending | Non-mutating `phase='confirm'` hint is returned; proposal is preserved and no host effect occurs |
| U32 | Visible default-printer display/execution claim lacks verified evidence | Sanitized no-change user message is returned; no raw `Honesty check:` diagnostic |
| U33 | Confirmation-priority prompt and multi-input honesty guard | A pending offer's next plain yes confirms rather than re-drafting; hidden reasoning is not treated as visible claims |

Primary files: `test_mcp_action_state.py`, `test_mcp_action_actions.py`, `test_mcp_action_tool.py`, `test_mcp_action_concurrency.py`, `test_mcp_action_dsl.py`, `test_mcp_action_screenshots.py`, `tests/integration/test_mcp_action_dify_contract.py`, plus the existing Windows/Office/logging/skill/follow-up suites listed in [plan.md](plan.md).

## 4. Contract tests

| ID | Contract | Expected result |
|---|---|---|
| C01 | `mcp_action` advertised through the MCP server | Schema and action/phase rules match [mcp-action.md](contracts/mcp-action.md); historical tool-presence and `ask` contracts pass without freezing the global tool count |
| C02 | Screenshot route immediate GET and repeated GET | Exact image bytes/MIME and all no-store/security/CORS headers; repeated reads work without extending TTL |
| C03 | Malformed, wrong, unknown, expired token and non-GET method | Indistinguishable 404 for tokens, 405 + `Allow: GET` for wrong method, always `no-store`; no metadata leakage |
| C04 | Tool result with captured screenshot | Contains only URL/expiry/usage, never Base64, local path, raw desktop text, or a caller-supplied verification claim |
| C05 | Existing `ask`, Windows, Office, PowerShell, and GUI contracts | No removed/renamed required field and no default behavior change; new image extraction is opt-in only |

## 5. Commands for deterministic validation

Run from the repository root:

```bash
.venv/bin/python -m pytest tests/unit/test_mcp_action_*.py tests/unit/test_windows_mcp_lane.py tests/unit/test_office_v2.py tests/unit/test_logging_setup.py tests/unit/test_skill_executor.py -q
.venv/bin/python -m pytest tests/contract/test_mcp_action_screenshot_route.py tests/contract/test_mcp_contract.py -q
.venv/bin/python -m pytest tests/unit tests/contract -q
```

Run frontend checks without running a production build while the development server is active:

```bash
cd ai-chat-landing
pnpm test
pnpm typecheck
pnpm lint
```

Expected: all new and pre-existing tests pass; lint has no new errors or warnings attributable to this feature.

## 6. Owner-present live integration and E2E matrix

After deterministic checks pass, deploy safely without the name-based `deploy all` path:

```bash
.venv/bin/python -m agentic_rag_mcp.deploy redeploy
# publish both apps by explicit ID, then:
.venv/bin/python -m agentic_rag_mcp.deploy verify
```

Run the opt-in Dify contract and live integration batteries:

```bash
RUN_MCP_ACTION_DIFY_CONTRACT=1 .venv/bin/python -m pytest tests/integration/test_mcp_action_dify_contract.py -q -s
RUN_MCP_ACTION_E2E=1 .venv/bin/python -m pytest tests/integration/test_mcp_action_e2e.py -q -s
```

For browser-level verification with the Chat UI and CDP Chrome running:

```bash
cd ai-chat-landing
node scripts/mcp-action-check.mjs
```

### Primary user journeys

| ID | Journey | Expected evidence |
|---|---|---|
| E01 | General agent: ask how to change the default printer to named test printer B, answer any context question, then reply **no** | Manual steps precede the exact offer; printer A remains default; no Settings/Word control or screenshot occurs; proposal is cancelled |
| E02 | Repeat E01 and reply **yes** | Only B becomes default; fresh read-back names B; Printers settings is visibly confirmed; response names A→B and shows a loaded screenshot (`naturalWidth > 0`); sanitized audit exists |
| E03 | Offer B, then reply “yes, but use C” | No change occurs on the modified response; revised proposal names C; only a fresh yes changes the default to C |
| E04 | Word: ask for long-edge duplex on the duplex test printer with an unsaved disposable document open, then reply **yes** | Proposal discloses printer-wide scope; effective mode reads back as long-edge; Word Print Preview is foreground; marker and `Saved=false` remain; screenshot loads; no print job |
| E05 | Repeat Word journey for short-edge and once with the requested mode already active | Correct short-edge read-back; already-active returns verified `changed:false`; no duplicate mutation is claimed |
| E06 | Repeat E01/E02 through Hermes and exercise an ordinary General-local question | Same stored-proposal and verification behavior on both approved agents; General-local retains its original behavior with no MCP-action tool or offer; no skill-search detour or router-only dependency |
| E07 | Ask an unsupported Excel/PowerPoint/Outlook procedure and an unrelated general question | Manual/existing answer only; no MCP-action offer or tool call; existing generic follow-up behavior remains |
| E08 | Ask an ordinary non-MCP follow-up, reply yes/no, then send an orphan/repeated MCP-action yes | Ordinary follow-up behaves as before; orphan/repeated MCP-action confirmation is blocked without host activity |

### Error-handling and recovery E2E cases

| ID | Injected or observed condition | Expected honest behavior |
|---|---|---|
| E09 | Default printer removed after draft; ambiguous/nonexistent printer requested | Fresh validation fails; no alternative printer is selected and no mutation occurs |
| E10 | Duplex setter returns access denied or printer does not support requested mode | No elevation or test page; after-read/report describes actual state and the permission/capability limitation |
| E11 | Windows is in managed-default mode | Proposal/result carries the persistence caveat; registry setting remains unchanged; any mismatch is an error |
| E12 | Word has a modal dialog or rejects COM calls | No blind Backstage/click fallback; documents remain untouched; display error is distinct from any verified printer change |
| E13 | Settings/Word cannot be foregrounded or display verification fails | Setting result remains independently reported; screenshot is skipped/unverified rather than showing an unrelated window |
| E14 | Screenshot transport returns no image, malformed image, or storage fails | Verified setting returns `partial` with screenshot failure; response contains no invented image |
| E15 | Windows-MCP/OfficeMCP is offline before mutation | Bounded unavailable error and no change; no fabricated offer/result |
| E16 | Transport fails after mutation outcome may be unknown | Safe after-read when possible; no automatic retry/rollback; actual or unknown partial state is reported and audit recorded |
| E17 | Two conversations confirm different actions concurrently | No overlapping host execution; second waits with explicit queue timing or consumes a queued-timeout without executing; first is not cancelled |
| E18 | Same conversation sends two simultaneous yes requests | Exactly one execution and one blocked/no-pending outcome |
| E19 | Proposal ages past expiry under the integration fake clock; later yes arrives | No execution; fresh proposal required. Optional live 15-minute variant has the same result |
| E20 | Screenshot URL is fetched repeatedly, with an invalid token, and after fake-clock expiry | Immediate/repeated image GETs work with `no-store`; invalid/expired GETs are 404; file and token-free logs/audit are verified |
| E21 | Restore original default/duplex settings in `finally` after every mutating case | Original values are read back and recorded; failure to restore is a visible test failure requiring owner attention |
| E22 | Offer a newline-bearing Q1/Q2 reply, then send `yes, help to do it` against the already-active default | Confirm executes the stored proposal, Settings is displayed, no replacement draft or raw honesty diagnostic appears, and the default remains unchanged |

## 7. Acceptance traceability

| Spec outcome | Proof |
|---|---|
| Manual steps + exact offer only for supported procedures | U01/U02/U28, E01/E04/E07 |
| No action before yes; no/cancel/modified/stale/orphan cannot execute | U03–U10, E01/E03/E08/E19 |
| Executed action is exactly the confirmed proposal | U03/U11–U16, E02–E05 |
| Independent before/after verification and honest partial results | U13–U23, E09–E16 |
| Relevant desktop screen and inline temporary screenshot | U20–U27, E02/E04/E12–E14/E20 |
| One active execution per desktop with queue reporting | U09/U18/U19, E17/E18 |
| Existing behavior and contracts preserved | U28/U29, C01/C05, E06–E08 |
| Confirmation fidelity and honest user-facing fallback | U30–U33, E22 |
| Performance targets | T056: 20 service-side samples per action; default p95 23.723 s < 60 s, Word p95 3.249 s < 90 s, queue wait separate |

## 8. Completion evidence and exit criteria

Record in the implementation test report:

- Focused and full Python/Vitest results, typecheck/lint results, and the deployment battery result.
- Dify app IDs used, turn-counter probe evidence, and the shared-honesty-guard cases.
- Before/after printer read-backs and restoration evidence for each mutating test.
- Word marker/document preservation and visible Print Preview evidence.
- Loaded-chat-image verification, route headers, fake-clock expiry, and log/audit privacy scans.
- Queue/execution timings and all blocked/error/partial cases, not only successful journeys.

The feature is complete only when all deterministic suites are green, every applicable live matrix row passes or is explicitly marked environment-blocked with owner sign-off, no dishonest success remains, both Dify apps are published, and original printer/test-document state has been restored.
