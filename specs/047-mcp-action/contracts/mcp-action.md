# Contract: `mcp_action`

**Purpose**: Add a two-phase, fixed-action confirmation tool for the two spec-047 reference actions. This is an additive MCP tool; existing tools are unchanged.

## Tool signature

| Field | Type | Presence and rule |
|---|---|---|
| `phase` | `"draft" \| "confirm" \| "cancel"` | Required |
| `conversation_id` | string | Required non-empty Dify `sys.conversation_id` |
| `dialogue_count` | integer ≥0 | Required Dify `sys.dialogue_count`; confirm/cancel must be exactly one greater than at draft |
| `query` | string | Raw Dify `sys.query`; required for confirm/cancel response classification, optional/empty for draft |
| `action_id` | string | Draft only; `windows_default_printer` or `word_printer_duplex` |
| `parameters` | object | Draft only; closed action-specific schema |

`confirm` and `cancel` MUST NOT carry `action_id` or `parameters`; supplying either is rejected. The caller cannot supply effect text, commands, UI steps, COM code, screenshot URLs, before/after states, or verification claims.

## Action parameters

```text
windows_default_printer:
  { "printer": "<one exact installed printer name>" }

word_printer_duplex:
  { "printer": "<one exact installed printer name>",
    "orientation": "long-edge" | "short-edge" }
```

Missing material parameters return `ask-back`. Unknown actions/parameters return `unsupported` or `error` without an offer or mutation.

## Draft

Example request:

```json
{
  "phase": "draft",
  "conversation_id": "conv-123",
  "dialogue_count": 4,
  "query": "",
  "action_id": "windows_default_printer",
  "parameters": {"printer": "Microsoft Print to PDF"}
}
```

Successful response:

```json
{
  "status": "pending-confirmation",
  "action_id": "windows_default_printer",
  "effect": "Change your default printer to Microsoft Print to PDF, then open Windows printer settings to show the result.",
  "offer": "Do you want me to do it automatically for you?",
  "expires_in_s": 900,
  "caveats": []
}
```

Draft performs only read-only target validation. It does not change a setting, control/open an application, or capture a screenshot. The agent must provide its tailored manual steps and place the returned `offer` in the standalone final paragraph. The Word duplex effect also discloses printer-wide scope, orientation, and whether a blank unsaved document may be created solely to show Print Preview.

## Confirm

Valid request for the example above:

```json
{
  "phase": "confirm",
  "conversation_id": "conv-123",
  "dialogue_count": 5,
  "query": "yes"
}
```

The tool, not the model, validates the raw response against a bounded plain-affirmative vocabulary. “Yes, but use another printer”, an unrecognized response, an intervening turn, or an expired proposal invalidates the proposal without execution. A wrong-conversation or orphan confirmation returns `blocked` without touching another conversation's proposal.

Illustrative success result:

```json
{
  "status": "ok",
  "action_id": "windows_default_printer",
  "changed": true,
  "before": {"default_printer": "Old Printer"},
  "after": {"default_printer": "Microsoft Print to PDF"},
  "verification": "verified",
  "display": {"status": "displayed"},
  "screenshot": {
    "status": "captured",
    "capture_scope": "foreground-window",
    "image_url": "http://localhost:28080/mcp-action/screenshots/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "expires_in_s": 900,
    "usage": "Inline this temporary image once as ![Verification screenshot](<image_url>)."
  },
  "timing": {"queue_wait_s": 0.0, "execution_s": 4.2, "total_s": 4.2, "display_s": 1.1, "screenshot_s": 0.4}
}
```

The agent must report actual before/after values and separate verification/display/screenshot outcomes. It may inline `image_url` only when `screenshot.status == "captured"`; it must never invent an image or call a screenshot proof of the setting by itself.

The audit `outcome` is `<action_id>:<status>:verification=<verification>:display=<display.status>:screenshot=<screenshot.status>` (or `<status>` when there is no action ID). `display_s` and `screenshot_s` are additive timing fields and are `null` when the corresponding stage was not attempted. `screenshot.capture_scope` is `foreground-window` when a relevant rectangle was captured or `full-display` when no valid rectangle was available or regional capture failed; `region_fallback` is `region-capture-failed` when the full-display fallback was used after a regional error. Audit never includes the screenshot URL/token/path or image bytes.

## Cancel

```json
{
  "phase": "cancel",
  "conversation_id": "conv-123",
  "dialogue_count": 5,
  "query": "no"
}
```

Response:

```json
{"status": "cancelled", "reason": "No automatic action was performed."}
```

Cancellation consumes the proposal and performs no mutation, display, or screenshot operation. The user remains with manual guidance only.

## Status and outcome contract

| Status | Meaning |
|---|---|
| `pending-confirmation` | Exact proposal stored; no mutation occurred |
| `ask-back` | Material target/parameter information is missing or ambiguous |
| `unsupported` | No reviewed action exists; manual steps only |
| `cancelled` | Pending proposal discarded without execution |
| `ok` | Requested target verified; `changed` may be false when already active |
| `partial` | Independently verified setting succeeded but display or screenshot did not fully succeed |
| `blocked` | No eligible proposal, wrong conversation/turn, modified response, or expired/repeated confirmation |
| `queued-timeout` | Proposal consumed without execution because its full action budget was unavailable |
| `error` | Validation, execution, verification, transport, or internal failure; fields must still describe any observed partial state |

`verification`, `display`, `screenshot`, and `timing` retain the nested values defined in [data-model.md](../data-model.md). All errors are sanitized and bounded. A setter exception triggers an after-read when possible; neither automatic rollback nor automatic retry of an unknown mutation is permitted.

## Dify wiring requirements

- Pass `sys.conversation_id`, `sys.dialogue_count`, and raw `sys.query`; do not let the agent paraphrase the raw response used by the tool.
- Register the tool on General-cloud Agentic Strategy and Hermes Local Agent only. General-local and PPT-Master retain their original behavior without MCP-Action.
- The exact offer requires a real pending result in the shared honesty guard. Execution/verification/display/screenshot claims require an actual `mcp_action` execution result.
- No global yes/no router change and no skill replay bypass are allowed.
