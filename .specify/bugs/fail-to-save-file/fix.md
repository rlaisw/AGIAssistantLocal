# Bug Fix: Trailing-punctuation false refusals — "C:\OfficeMCP." refused as outside C:\OfficeMCP

- **Slug**: `fail-to-save-file`
- **Fixed**: 2026-11-03
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The shared `normalize_path` now rstrips the trailing characters that cannot terminate a legal Windows path (sentence/markup punctuation: `.,;:!?)]}>»‹*` + backtick — after the existing whitespace/quote strip), closing the false-refusal class in **all three Hermes gates at once**. The user's exact retry — *"…save it to C:\OfficeMCP."* — now passes the gate and the file was created and verified: `C:\OfficeMCP\test1.pptx` exists with "Hello" in its slide XML.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/agentic_rag_mcp/hermes_gate.py` | modified | `_TRAILING_PUNCT` constant + one `.rstrip(_TRAILING_PUNCT)` in `normalize_path` — with the one-line why comment (Windows paths can't legally end with dots/spaces; the strip is lossless) |
| `tests/unit/test_hermes_gate.py` | added tests | file-lane trailing period → ok (path normalizes to the root exactly); `C:\Other.` → still blocked (containment not weakened) |
| `tests/unit/test_hermes_launch_gate.py` | added test | `run C:\Windows\System32\notepad.exe.` → ok (the period no longer defeats the `.exe` check) |
| `tests/unit/test_office_gate.py` | added tests | the user's exact prompt → ok; `open C:\Other. and write A1` → still blocked |

## Diff Highlights (optional)

```python
# Windows paths cannot legally end with dots or spaces, so stripping
# sentence punctuation the token regex swallows is lossless for every
# real path — without it "C:\OfficeMCP." fails containment
_TRAILING_PUNCT = ".,;:!?)]}>»‹*`"
token = (token or "").strip().strip("\"'").rstrip(_TRAILING_PUNCT)
```

## Tests Added or Updated

- `test_hermes_gate.py::test_trailing_punctuation_is_not_a_false_refusal` — the file lane accepts "C:\temp."
- `test_hermes_gate.py::test_trailing_punctuation_does_not_weaken_containment` — "C:\Other." stays blocked
- `test_hermes_launch_gate.py::test_trailing_period_after_exe_path_tolerated` — "notepad.exe." launches
- `test_office_gate.py::test_work_folder_named_with_sentence_punctuation_is_accepted` — the user's exact prompt passes
- `test_office_gate.py::test_trailing_punctuation_does_not_weaken_office_containment` — the office containment holds

## Local Verification

- Commands: all gate + tool suites → **105 passed** (7 new assertions incl. the negative controls); hot-patched `hermes_gate.py` to the sidecar + restart
- Live re-probe — the user's exact retry: `hermes_office_task("…save it to C:\OfficeMCP.")` → **`ok` in 90 s** — STEP reports show the full pipeline (RunningApps check, Launch PowerPoint, create, save, verify-by-reopen), and the artifact check confirms **`C:\OfficeMCP\test1.pptx` exists with "Hello" in its slide XML** — the user's actual goal, delivered by the fix verification itself
- The pre-fix probes from the assessment (office/file/launch all falsely blocking `C:\OfficeMCP.` / `C:\temp.` / `notepad.exe.`) now pass

## Deviations from Assessment

- The first version of the file-lane test asserted the gate concatenates the folder name into the normalized path — wrong model (the gate normalizes the *location* token; the agent creates the named folder inside it). The assertion was corrected to `normalized_path == "/mnt/c/temp"`; no code deviation, test-only.

## Follow-ups

- Fold this fix into the held T022 commit (same uncommitted working tree; the fix touches the shared 028 file lane — its contract tests are green).
- The live file `C:\OfficeMCP\test1.pptx` is the user's requested deliverable — leave it or delete it at will.
- The already-documented MCP-transport flakiness (DEPLOY.md row from bug `no-powerpoint-tool`) remains the separate residual; this fix is deterministic gate code, unaffected by it.
