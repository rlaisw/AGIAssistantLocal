# Bug Assessment: Office turn still slow — 75.6 s on the office lane

- **Slug**: slow-total-time-75-6-seconds
- **Created**: 2026-11-13T01:23:42Z
- **Source**: pasted text (the agent's trace, conversation `7096969a…`)
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim, summarized)

> "slow-Total time: ~75.6 seconds." — "open Word, type hello abc" routed correctly to the office lane (the why-not-officemcp fix working), the skill loop ran (search → get → follow), and the office turn completed perfectly: Word opened, "hello abc" typed, saved to `C:\OfficeMCP\hello_abc.docx`, verified (13,435 bytes). But the turn took **75.6 s**.

## Symptom

The routing is now right (office lane ✓, skill loop ✓, honest verification ✓) but a trivial document-write still takes ~75 s end-to-end. Expected: seconds-to-tens.

## Reproduction (measured, conversation `7096969a…`, 2026-11-13)

| Step | Time | Share |
|------|------|-------|
| skill_search + skill_get | 01:20:15–17 (~2 s + 2 short rounds) | ~3% — cheap, the loop works |
| **hermes_office_task turn** (open Word → create → type → save → verify) | 01:20:18 → 01:21:34 = **75.6 s** | **~90% — the whole complaint** |

The office turn's own steps (from the audit): STEP open/create, STEP compose, STEP save (default folder), STEP verify (read-back through Word: exists, 13,435 bytes, ActiveDocument, content) — 5 narrated steps, each a kimi reasoning round plus an OfficeMCP COM call.

## Suspected Code Paths

- `hermes_office_task` (sidecar) → `_run_hermes` — the office lane rides the **same double-LLM structure** the launch and browser lanes had before their v2 fixes: Dify agent → tool call → **[Hermes agent = 2nd LLM turn]** → OfficeMCP. The 75.6 s is kimi reasoning × ~5 steps + verification narration; the COM calls themselves are milliseconds.
- `services/wsl-bridge/bridge.py` — forwards :3002/:8080/:8800 but **not :8888** (OfficeMCP) — the sidecar cannot currently reach OfficeMCP directly; that is the missing plumbing for the fix.
- The task shape itself is **fully deterministic** (open a doc, type a literal, save, verify) — no exploration needed; an LLM in the mechanical loop adds cost, not value.

## Root Cause Hypothesis

Same architectural class as the launch/desktop (196 s) and pre-v2 browser (37–230 s) findings: the office lane is agent-paced end to end. The deterministic 80% of the work (create→write→save→verify) pays a full LLM round per step inside a second agent turn. The browser v2 fix (single-hop proxy, trimmed reads) took that lane from minutes to ~5 s of tool time; the office lane has not had that treatment. Confidence: **high** — the audit rows enumerate the steps and the gateway times the turn exactly.

## Proposed Remediation

**Preferred — the office v2 proxy** (the browser-v2 pattern applied to OfficeMCP):
1. **Bridge**: add the :8888 forward (shifted port, e.g. 18888 → 127.0.0.1:8888) to the wsl-bridge (one line; the bridge already carries :18800 for WindowsMCP from the desktop-v2 prep).
2. **Sidecar proxy**: `office_lanes/proxy.py` — a single session to OfficeMCP (legacy SSE transport, same class as WindowsMCP) exposing **deterministic document primitives** as sidecar tools the Dify agent calls directly (one LLM in the loop): `doc_write_v2(text, name?)` (create/write/save, default work folder), `doc_read_v2(name)`, `doc_append_v2`. Each primitive does its own read-back verification (the STEP-verify discipline moved into code — file exists, content matches, no narration needed).
3. **Routing**: the DSL routes simple document-write shapes ("open Word and type X", "write X in a new Word document") to the v2 primitives; `hermes_office_task` stays for the complex class (compose→confirm→send email, REPLACED-overwrite attestations, multi-step document surgery).
4. Expected: **75.6 s → ~5–10 s tool time**, turn ~20–30 s total.

**Alternatives**:
- Deterministic office scripts (the scripted-lane pattern): parameterized scripts for common shapes — slower to author, no interactive reads; the proxy covers more.
- Accept 75.6 s as the office-lane cost — the complaint shows that's not acceptable.

**Files likely to change**:
- `services/wsl-bridge/bridge.py` (:18888 forward)
- `src/agentic_rag_mcp/office_lanes/proxy.py` (new), `server.py` (2–3 v2 tools)
- `dify/AGIAssistant/AGI_Assistant.yml` (routing rule; publish)
- `tests/unit/test_office_proxy.py` (new pins)

**Tests to add or update**:
- Proxy client pins (session handshake, honest envelopes, verification-in-code)
- Routing pins: simple document-write → v2 path; email/complex stays on `hermes_office_task`
- Live timing before/after recorded in the audit rows

## Risks & Considerations

- **OfficeMCP consent/visibility**: v2 primitives drive COM directly — Word windows appear and vanish on the user's desktop; no USER_CONTROL consent applies (same as today's office lane).
- **The verification discipline must move into code, not vanish**: each v2 primitive asserts its own read-back (exists, size, content) and reports honestly — the STEP-verify pattern the agent does narratively today.
- Keep `hermes_office_task` untouched for the complex class — this is additive, same as browser v2 kept `browser_dynamic_task`.

## Open Questions

- None blocking. (The desktop v2 for Notepad-class followups remains separately parked; the office v2 shares the bridge/proxy infrastructure.)