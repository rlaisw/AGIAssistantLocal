# Quickstart: Office Save Anywhere (spec 031)

Validation guide — proves the amendment end-to-end. Contract delta: [contracts/hermes-office-save-anywhere.md](contracts/hermes-office-save-anywhere.md); entities: [data-model.md](data-model.md).

## Prerequisites

- The spec 030 stack: OfficeMCP service running on Windows, the gateway wired (`hermes mcp add` per 030's quickstart), Office installed, WSL interop enabled, the sidecar up with this feature's code hot-patched.
- A second writable location for the live probes — the owner's own case uses `C:\temp\test` (the file lane's root, reached at `/mnt/c/temp/test`).

## 1. Unit suites (deterministic, no network)

```bash
.venv/bin/python -m pytest tests/unit/test_office_gate.py tests/unit/test_hermes_office_tool.py -q
```

Expected: green — the widened matrix (`c:\temp\test` named → ok; `D:\projects\` → ok; punctuation-tolerant paths → ok), the retired-refusal check (no "outside the Office work folder" reason), the unchanged content rules (macro/DDE/formula refusals wherever the target lives), the named-location directive assertion, and the OS-permission-error relay (client mocked).

## 2. Existing suites stay green (Constitution I)

```bash
.venv/bin/python -m pytest tests/unit tests/integration tests/contract -q
```

Expected: green (the two known pre-existing failures — web-research cap, onedrive staleness — reproduce in the old workspace; out of scope). The one updated assertion: the retired out-of-folder refusal now expects the named location to pass.

## 3. Live battery (deployed stack + Office)

```bash
.venv/bin/python -m agentic_rag_mcp.deploy verify
```

Expected: the office scenario green with the amended matrix:

| # | Probe | Expected |
|---|-------|----------|
| O1–O5, W1, P1 | The existing 030 matrix | unchanged — all green (the work-folder cases keep working: the default is unchanged) |
| **S1 (new)** | *"create a PowerPoint with the text 'Hello', file name test1, save to c:\temp\test"* — the owner's exact previously-impossible request | `ok`; `/mnt/c/temp/test/test1.pptx` exists with "Hello" in its slide XML (stdlib `zipfile` check); the answer names the full saved path; the audit records the target |
| O6 (amended) | The refusal matrix keeps 4 of 5: macros, DDE, address-less compose, mailbox-delete | all `blocked` with the same reasons; the out-of-folder case is retired |
| O7 | Audit cross-check | per-step entries, `allowed_root = C:\OfficeMCP` (the default, the lane discriminator), `normalized_path` = the actual target |

## 4. Manual chat check (end-user view)

In the Chat UI: *"create a Word document with the text 'project notes' and save it to D:\docs\"* (any drive you like) → the file appears at exactly that location, the answer names the full path. Then re-ask the same → the existing file is replaced and the answer says so honestly.

## 5. Error handling checks (each a unit case or battery probe)

- Save into a permission-protected location (e.g. `C:\Windows\System32\...`) → the OS's exact permission error relayed; never a fabricated success; audited.
- A deep path whose parents don't exist → created as needed, or the honest creation failure.
- An existing named file with unsaved changes open in the application → ask-back before writing.
- A removable drive that isn't present → honest failure naming the location.

## 6. Cleanup

The live probes leave files at `c:\temp\test\test1.pptx` and any manual-check locations — delete at will; the audit log is never pruned.

## Recorded outcomes (implementation + analyze, 2026-11-03)

- Full live run: **S1 named-location-save ok** (`c:\temp\test\test1.pptx` verified in the slide XML — the owner's exact previously-impossible request), **X1 overwrite-honesty ok** ("v2" in the docx + "replaced" in the step report), **O6 4/4 refusals** (out-of-folder case retired), W1/P1/O3–O5 green, O7 audit truthful. O1/O2 hit the documented gateway→OfficeMCP transport flakiness on the first run; the DEPLOY.md recovery (`hermes mcp remove/add + gateway restart`) restored them — both re-ran green.
- Error handling (T015): `C:\Windows\System32` → honest "Permission denied" relayed; `Q:\nowhere` → honest failure naming the location.
- Regression (T012): 470 tests green (the two known pre-existing environmental failures unchanged).
- **Analyze pass (2026-11-03)**: 0 critical/high findings; SC-002 amended (finding U1 — this machine has a single drive, so the "second drive" acceptance was reworded to the live-verified equivalents: any named location + the honest OS-error paths); U2 (unsaved-changes ask-back) remains instruction-enforced per the 030 honesty protocol, live-unverified — verify manually with a dirty Word doc when convenient; I1 (UNC paths) falls to the default folder safely, acceptable as designed.
