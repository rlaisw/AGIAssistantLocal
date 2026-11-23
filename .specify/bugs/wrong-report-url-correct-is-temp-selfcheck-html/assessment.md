# Bug Assessment: Health answer shows the temporary report URL instead of the saved report file

- **Slug**: wrong-report-url-correct-is-temp-selfcheck-html
- **Created**: 2026-11-22
- **Source**: pasted text (includes a loopback URL)
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

> "html report url is wrong Report(http://localhost:28080/mcp-action/reports/OzWfjfnEAQm0fDKg2pUytwHog74FAcpWNdptSIR4dtk) the correct html report is (written to C:\Temp\selfcheck.html, expires in 15 min)
> you should replace http://localhost:28080/mcp-action/reports/OzWfjfnEAQm0fDKg2pUytwHog74FAcpWNdptSIR4dtk by C:\Temp\selfcheck.html"

URL policy: the supplied URL is loopback (`localhost:28080`), so it was **not fetched** (`auto-refused: loopback host`). The report link is data in the bug description, not a page to retrieve.

## Symptom

The health-check answer still presents the temporary capability URL as the report, e.g. `Report(http://localhost:28080/mcp-action/reports/<43-char-token>)`. Expected: the visible report reference is the saved file path `C:\Temp\selfcheck.html` (or a clear file reference), not the temporary `/mcp-action/reports/` URL.

## Reproduction

1. Confirm a `system_health_check`.
2. Read the visible answer.
3. Observed: a `Report(...)` line contains the `/mcp-action/reports/<token>` URL; the path `C:\Temp\selfcheck.html` may also appear, but the URL is still presented as the report.
4. Expected: `Report: C:\Temp\selfcheck.html` and no `/mcp-action/reports/` URL in the visible answer.

## Suspected Code Paths

- `src/agentic_rag_mcp/mcp_action/service.py:775-784` — the `usage` string still says “Include this temporary report link once as [Open the system health report](url)”; the model follows it.
- `dify/AGIAssistant/AGI_Assistant.yml:1562` — the HEALTH RESULT prompt requires the exact `/mcp-action/reports/` URL and says to append it when missing.
- `dify/AGIAssistant/AGI_Assistant.yml:2002` — the finalizer appends the URL (`healthSuffix += ' [Open the system health report](' + healthReportUrl + ')'`) and does not remove an already-emitted URL.
- `tests/unit/test_mcp_action_dsl.py:1166` — the prompt test currently requires the report URL and token grammar, reinforcing the old behavior.
- `tests/integration/test_mcp_action_e2e.py` — E04/E15 assert the tool-envelope report URL; the chat-level finalizer has no equivalent URL-removal test.

## Root Cause Hypothesis

Confidence: **high**. The full-HTML override added `report.host_path`, but the prompt, service usage hint, and finalizer still treat the temporary URL as the canonical report reference. The model emits the URL because the prompt requires it; the finalizer only appends the path and HTML, so both appear. The fix must make the host file path the primary visible reference and remove the `/mcp-action/reports/` URL from the answer.

## Proposed Remediation

**Preferred**: Make `report.host_path` the visible report reference when `host_path_status == "written"`:

- Change the service `usage` hint to: “The complete report is at `report.host_path`; include that path once and do **not** emit a `/mcp-action/reports/` URL.”
- Change the HEALTH RESULT prompt/tool description: report the file path, keep the full HTML, and do not include the temporary URL.
- In the finalizer, strip any `/mcp-action/reports/<43-char-token>` URL (including the markdown link form) from the visible answer and append `Complete report file: C:\Temp\selfcheck.html` when it is missing. Keep the full HTML append.
- Keep the report store/publication as an internal fallback; it must not appear in the visible answer.
- If `host_path_status != "written"`, do not claim the file exists; fall back to the temporary URL only with an explicit “temporary link” label, or report that the file could not be written.

**Alternatives**:
- Remove the report URL and report store entirely. Simplest output, but loses the browser fallback when the host file cannot be written.
- Keep both references. Rejected: the user explicitly asked to replace the URL with the file path.

**Files likely to change**:
- `src/agentic_rag_mcp/mcp_action/service.py`
- `dify/AGIAssistant/AGI_Assistant.yml`
- `tests/unit/test_mcp_action_dsl.py`
- `tests/unit/test_mcp_action_tool.py`
- `tests/integration/test_mcp_action_e2e.py` (tool-envelope expectations only; the URL may remain internal)
- `specs/048-system-health-check/{spec.md,contracts/system-health-check.md,test-report.md}` and `AGENTS.md`/`README.md` if the contract changes

**Tests to add or update**:
- A DSL finalizer test where the model answer contains a valid `/mcp-action/reports/...` URL: assert the URL is removed and `C:\Temp\selfcheck.html` appears once.
- A no-path case: assert no file path is claimed and the fallback is explicitly labelled temporary.
- Update the prompt test to require the host path and forbid the temporary URL in the visible answer.
- Keep the tool-envelope/E2E URL test if the URL remains in the result for internal fallback.

## Risks & Considerations

- The report URL is a valid local-trust capability URL; removing it from chat is a product decision, not a security fix.
- The path is Windows-host-specific (`C:\Temp\selfcheck.html`); the chat UI must display it as text, not a clickable browser URL.
- Stripping URLs must not remove the full HTML report or the path line.
- If the host copy fails, the answer must not claim the file exists; the fallback must be honest.
- Audit rules remain unchanged: no URL, token, HTML, or PII in the audit.

## Open Questions

- [NEEDS CLARIFICATION: should the temporary URL remain available in the tool result as an internal fallback, or be removed from the result entirely?]
- [NEEDS CLARIFICATION: when the host file cannot be written, should the answer show the temporary URL with a “temporary link” label, or omit a report reference and report the write failure?]
