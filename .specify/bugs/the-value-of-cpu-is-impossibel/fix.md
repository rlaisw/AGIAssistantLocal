# Bug Fix: CPU% above 100% explained in the relay — the multi-core scale note in the lane instruction and tool description

- **Slug**: the-value-of-cpu-is-impossibel
- **Fixed**: 2026-11-14T13:02:00+00:00
- **Assessment**: ./assessment.md
- **Status**: applied — DSL-only, published, live-verified in chat

## Summary

The windows-mcp CPU% column aggregates across all logical processors (values >100% are correct on many-core hosts — verified live: System Idle ~1876% on 20 logical CPUs), but nothing told the agent what the unit meant, so chat answers relayed "impossible" numbers bare. The fix adds the scale explanation to the Hermes lane's fast-path instruction and the `windows_mcp_process_list` tool description — the agent now relays the genuine table verbatim and appends the one-line explanation. No data path touched (the verbatim-relay contract holds); DSL-only change, published, and live-verified: the replay answer carries both the table and the note.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `dify/AGIAssistant/AGI_Assistant.yml` | modified | (1) new `CPU% scale` bullet right after the process-listing FAST PATH rule: CPU% aggregates across ALL logical processors, >100% normal (each fully-busy core contributes 100%; System Idle Process often >1000% on an idle many-core host), relay verbatim AND append the one-line explanation; (2) the same note embedded in the `windows_mcp_process_list` tool_description |
| `tests/unit/test_intent_router_rules.py` | added test | `test_cpu_percent_scale_explained` — pins the explanation in exactly the two DSL locations (count == 2) |

## Diff Highlights (optional)

```yaml
# the lane instruction (and the same note in the tool description):
"CPU% scale (…): the service's CPU% column aggregates across ALL logical
processors — values above 100% are normal and correct (each fully-busy
core contributes 100%; on a many-core host, System Idle Process commonly
shows well over 1000% on an idle machine). Relay the table verbatim AND
append this one-line explanation to any CPU-sorted listing…"
```

## Tests Added or Updated

- `test_intent_router_rules.py::test_cpu_percent_scale_explained` — the scale note must exist in exactly both places (the fast-path instruction + the process-list tool description), so a future DSL edit cannot silently drop it.

## Local Verification

- Commands: `pytest tests/unit/test_intent_router_rules.py` → **3 passed**; full `pytest tests/unit` → **679 passed, 0 failed**; `ruff check` → clean; `deploy chatflow` → draft updated in place + published.
- **Live replay** (conversation `0d128029…`, "on my computer, list the top 5 processes by cpu", 18.6 s turn): the answer contains the genuine table (audit: `windows-mcp-process` executed 11.3 s) **and the explanation verbatim**: "Note on the CPU% column: the values aggregate across **all logical processors**, so numbers above 100% are normal and correct — each fully-busy core contributes 100%…" — plus a helpful reading of vmmemWSL at 175.3% as the WSL VM's multi-core footprint. The reported confusion cannot recur on this path.

## Deviations from Assessment

- The assessment said the note goes in "both windows-mcp tool_descriptions"; it was added to `windows_mcp_process_list` only — `windows_mcp_status` relays no CPU numbers, and the note there would be noise. The fast-path instruction (which governs every listing turn) plus the process-list description cover every surface the data appears on. Logged as a deliberate narrowing.

## Round 2 (2026-11-14, same day — owner follow-up: "121.8% is not a human understandable value")

The explanation-only remedy was superseded by a **presentable dual-scale output** — the numbers themselves now carry the meaning:

- **What the user sees now** (live, from the rebuilt container):
  ```
  0    System Idle Process  1700.4% (85.0% of machine)  0.0 MB
  8928 vmmemWSL             254%    (12.7% of machine)   19791.4 MB
  ```
  plus a scale note in the output: "CPU% aggregates across all 20 logical processors — '(x% of machine)' normalizes it to the whole host (100% = every core fully busy)."

- **How**: `render_cpu_scale()` in `client.py` annotates each row's raw value with the whole-machine share (Task-Manager-style), with a **self-check that refuses to present wrong numbers** — any share above ~100% means the count is inconsistent with the data → falls back to the raw text. The host's logical-processor count is **baked into the container at redeploy time** (`docker_ops.py::_windows_logical_processors()` reads the real Windows count via WSL interop and passes `WINDOWS_LOGICAL_PROCESSORS=20` to the container; the container's own cpu_count is the WSL VM's capped view — 8 vs 20 — and must never be used). Unknown count → raw + the round-1 explanation.
- **Dead ends verified on the way** (recorded so they are not retried): the service's Registry tool is unusable for reads in this build (CLIXML noise on get/list); the WSL VM's cpu_count is capped (8 ≠ 20).
- **Tests**: 6 new pins (`TestCpuScaleRendering`: dual-cell rendering, unknown-count fallback, the inconsistent-count self-check, non-listing text untouched, env parsing, the deploy bake) — lane battery 32, full suite **685 passed, 0 failed**. DSL republished (the pin count of 2 holds); one YAML stumble on the way (apostrophes in a single-quoted scalar) fixed before publish.
- **Live**: `windows_mcp_process_list(sort_by="cpu")` through the container shows the clean dual-scale table (no dangling %).

## Follow-ups

- Upstream note (optional, out of repo): the windows-mcp service could offer both a normalized CPU% column (0–100% across cores) and the raw aggregate, removing the need for lane-side rendering; its Registry read paths are also broken for spaced keys in this build.
- The DSL explanation is deliberately generic ("many-core host", no hardcoded core count) so it ships correctly to any machine; the machine-share column appears automatically wherever the redeploy-derived count is present.
