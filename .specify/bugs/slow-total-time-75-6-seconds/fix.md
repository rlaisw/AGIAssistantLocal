# Bug Fix: office v2 — single-hop document writes (75.6 s → 0.4 s)

- **Slug**: slow-total-time-75-6-seconds
- **Fixed**: 2026-11-13T01:30:50Z
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The browser-v2 pattern applied to OfficeMCP: a persistent single-hop proxy executes FIXED, live-tested RunPython templates with the verification discipline moved INTO code, exposed as `doc_write_v2` / `doc_read_v2` sidecar tools — one deterministic call instead of a 5-step agent turn. **Live proof: the exact reported task ("hello abc") = 0.4 s tool time (was 75.6 s, ~190×).**

## Changes

| File | Change | Notes |
|------|--------|-------|
| `services/wsl-bridge/bridge.py` | +`:18888 → 127.0.0.1:8888` | the container reaches OfficeMCP (mirrored-port rule: shifted port) |
| `src/agentic_rag_mcp/office_lanes/proxy.py` | NEW | persistent legacy-SSE session (threaded reader, id-correlated, stale-session re-open once); FIXED templates — write (Dispatch Word visible → Add → literal text → SaveAs → verify exists/size/content → **Close**: lock-free repeat writes, probed live 3× after diagnosing the open-doc lock collision), read (read-only open → text ≤4000 chars → Close); the `output`-field envelope parsing (probed live); honest malformed/verification-failure envelopes |
| `src/agentic_rag_mcp/server.py` | +2 tools (45 total) | `doc_write_v2(text, name?)` — name sanitized (basename only, no traversal, `.docx` enforced, default from text), honest created/REPLACED note (the spec-031 discipline, detected server-side via `existed`), audit rows with cid; `doc_read_v2(name)` honest not-found |
| `src/agentic_rag_mcp/config.py` | `office_mcp_host/port` | bridge target |
| `dify/AGIAssistant/AGI_Assistant.yml` | routing rule + both tools on the lane | SIMPLE whole-document literal writes → doc_write_v2; ALL OTHER Office work (edits, cells, slides, email compose→confirm→send) stays on `hermes_office_task`; published |
| `tests/unit/test_office_v2.py` | NEW, 10 pins | name sanitization (traversal/backslash/dotdot/chars/default), envelope parsing (the live `{"success","output"}` shape), template discipline pins (verification in code, Close after save, `data`-parameterization = no agent-composed code) |

## Local Verification

- Probes that shaped the design (all live): OfficeMCP v4.1.5 tools list; `RunPython(code, data)` with **`output` as the return channel**; win32com available; the exact write template end-to-end (`path/size/existed/text_ok`); the open-doc lock collision on repeat writes → fixed by Close-after-save (3/3 loop ok)
- **THE timing proof** (through the deployed container): `doc_write_v2("hello abc", "hello_abc.docx")` → `status: ok, replaced the existing document (honest), size 13431, text_ok: True` — **audit duration 0.4 s** vs the same task's 75.6 s on the office lane
- 616 unit tests green, ruff clean, 45 tools synced, chatflow published

## Deviations from Assessment

None — the preferred remediation landed exactly. One discovery worth recording: the first template left the document open in Word (mirroring the office lane's "Word still open" reports) and repeat writes to the same path hit a COM lock (`DISP_E_EXCEPTION`); the v2 template closes the doc after verification — the FILE is the deliverable, and lock-free repeats matter more than the aesthetic.

## Follow-ups

- Watch the next real "open Word and type X" in the Chat UI: expected ≈ 0.4 s tool + classifier/answer rounds ≈ 10–20 s total.
- The desktop v2 (WindowsMCP primitives for Notepad-class followups) now shares ALL this infrastructure (bridge :18800 is already in; the proxy pattern is proven twice) — say "build the desktop v2" to finish that lane.
- `hermes_office_task` is untouched for the complex class — email flows, edits, and overwrite attestations keep their gates.
