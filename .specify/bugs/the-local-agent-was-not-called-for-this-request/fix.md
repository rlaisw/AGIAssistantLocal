# Bug Fix: honesty check precision — visible-answer testing, narrowed claims, actionable message, and the locale ask served

- **Slug**: `the-local-agent-was-not-called-for-this-request`
- **Fixed**: 2026-11-09
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The honesty check now tests only the **visible answer** (kimi's thinking preamble is stripped by splitting on its ``` fences and taking the last non-empty segment), its claims regex lost the bare tool-name alternation (which false-fired on reasoning text like "Let me call hermes_run_command") and gained `the tool (returned|responded)` (which catches fabricated tool-*interaction* claims such as the 08:53 draft's "The tool returned an error again" for a call that never happened), and its block message is now actionable (names the allowed commands that work). The relay instruction gained the emit-the-call rule, the gate now maps locale asks to `systeminfo` (whose output contains the System Locale lines — the exact reported ask is servable), and a malformed-`\\n` defect in the live law text (introduced by this morning's edit, harmless to the model but malformed) was found and repaired in passing.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `dify/AGIAssistant/AGI_Assistant.yml` — `honesty_check` code node | modified | visible-answer extraction (```-fence split, fence-less text tested whole — over-block direction); claims narrowed (`hermes_*` now needs a completion verb; added `the tool (returned\|responded)`); actionable block message naming working asks |
| `dify/AGIAssistant/AGI_Assistant.yml` — `hermes_agent` instruction | modified | new rule: *Emit the call, never narrate it* — a decided tool call must be in the same response, never a dangling "I'll check that for you"; also repaired the law bullet's literal `\\n` sequences to parseable newlines (morning-edit defect, live since 08:01, harmless to the model — kimi quoted the law verbatim all day) |
| `src/agentic_rag_mcp/hermes_run_gate.py` | modified | intent-map: `system locale`, `input locale`, `locale setting` → `systeminfo` (its output carries the locale lines) |
| `tests/unit/test_hermes_run_gate.py` | added test | `test_locale_asks_map_to_systeminfo` — pins the four locale phrasings |

## Diff Highlights (optional)

```js
// visible answer only — the thinking preamble mentions tools legitimately
var parts = String(answer).split('```');
var visible = String(answer);
for (var j = parts.length - 1; j >= 0; j--) {
  if (parts[j] && parts[j].trim()) { visible = parts[j]; break; }
}
var claims = /local agent (completed|did|was)|the agent (sent|pressed|...|handled)|the tool (returned|responded)|confirmed (by |with )?(a |the )?(snapshot|it)|LAUNCH: ?(SUCCESS|FAILED)|hermes_(launch_app|office_task|file_task|cancel_turn|run_command) (succeeded|completed|returned|ran)/i;
if (!called && claims.test(visible)) { /* actionable notice */ }
```

## Tests Added or Updated

- `test_hermes_run_gate.py::test_locale_asks_map_to_systeminfo` — "show my system locale setting" (the exact reported ask) → ok `systeminfo`.
- Node-harness re-validation (the assessment's contract) against **all seven recorded drafts**: fabricated-newtab-1/2/3 → **BLOCKED**; fabricated-0853 → **BLOCKED** (via the new `the tool returned` pattern); honest-noemit-locale/disk → **PASSED** (the false accusation is gone); real-ip-turn → **PASSED**.

## Local Verification

- Commands: `pytest tests/unit/test_hermes_run_gate.py tests/unit/test_hermes_run_tool.py tests/unit/test_hermes_launch_gate.py tests/unit/test_hermes_launch_tool.py -q` → **91 passed**.
- Live: hot-patched the gate into the sidecar (`docker cp` + restart, health ok); published the chatflow (drift-checked: no publishes since 08:40:28); Postgres graph `09:14:36` carries the new regex (`t`), the emit-the-call bullet (`t`), and the locale mapping (`t`).
- Harness: the seven-case node validation above — every recorded fabrication still blocked, both honest drafts pass.

## Deviations from Assessment

- One scope expansion, logged per the command rules: while editing the instruction I found that this morning's ANTI-FABRICATION LAW edit had inserted literal `\\n` sequences (parse-visible as `\n` characters instead of newlines) into the live instruction — a defect of my earlier edit, not of the assessment's plan. It was harmless in practice (kimi read and obeyed the law all day, citing it verbatim) but malformed; repaired in the same span this fix already touched. No other departures — all four assessment items applied as proposed.

## Follow-ups

- The kimi-k3 **no-emit flake** (intends a call, narrates it, emits nothing) remains upstream: this fix stops the guard from compounding it into a false-accusation loop and gives blocked users a working path, but occasional dangling "I'll check…" answers may still end a turn honestly-empty. Watch for recurrences; a Dify-side auto-retry would need unsupported topology surgery.
- Disk-space asks are honestly uncovered (the gate ask-backs with the list) — if the owner wants them, a small spec amendment can add a read-only volume command (e.g. `Get-Volume`) to the allowlist.
- Fold this fix into the next lifecycle commit.
