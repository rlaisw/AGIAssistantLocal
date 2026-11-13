# Quickstart: Browser Control v2 (spec 039)

**Spec**: 039 | **Date**: 2026-11-13

Runnable validation proving the full control surface end-to-end. Shapes in [contracts/](./contracts/README.md); entities in [data-model.md](./data-model.md); cases in [test-plan.md](./test-plan.md).

## Prerequisites

```bash
curl -s localhost:28080/healthz                          # sidecar ok (53 tools after build)
.venv/bin/python -m agentic_rag_mcp.deploy all           # after 039 implementation
# Windows: the playwright-mcp-server launcher running (:3002 SSE reachable via the bridge)
```

## End-to-end scenarios

### E1 — The full workflow (SC-001, the headline)

1. In the Chat UI: *"in my browser, go to the form page, type John Chan in the name field, select Hong Kong as the country, and click submit"*.
2. Expected: each verb lands (navigate → type → select → click), each read-back verified, and the answer presents **per-step screenshots** in order.
3. Audit: one row per verb (`browser-<verb>-v2`), each with conversation_id + duration; values excluded from outcome text.

### E2/E3/E4/E5 — The verb battery

- Select by label on a country list → the visible option lands and reads back (SC-002)
- One form-fill call, 3 fields, per-field honest results
- Tabs: open/list/switch/close
- Wait-for: delayed text appears within the bound; a never-appearing text → honest timeout naming what was awaited

### Sensitive field check

- *"type my-secret-password into the password field"* → typed (user's request is the authority); the audit row and summary contain NO value text; the screenshot shows masked dots.

### A2 adversarial (SC-003, mandatory)

- Injection payloads in page content, dropdown options, and pre-filled fields → zero actions initiated; honest reports; audit rows on every refusal.

## Expected outcomes

- `tools/list`: **53 tools** (47 + the six `browser_<verb>_v2`), existing schemas byte-identical.
- A complete workflow turn: tool work in seconds; the model's rounds the only remainder (SC-005).
- The screenshot-preservation pin and the A2 suite green.