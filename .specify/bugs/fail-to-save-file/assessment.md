# Bug Assessment: Trailing-punctuation false refusals — "C:\OfficeMCP." treated as outside C:\OfficeMCP

- **Slug**: `fail-to-save-file`
- **Created**: 2026-11-03
- **Source**: pasted text (chat transcript + user summary "i cannot save file to BOTH folders c:\temp\test and default folder C:\OfficeMCP")
- **Verdict**: valid — deterministically reproduced, unit-level, in our gate code
- **Severity**: high

## Report (verbatim or summarized)

After the `no-powerpoint-tool` fix made the containment refusal actionable, the user retried: *"help to re-try save to default folder C:\OfficeMCP"*. The chat agent's own reasoning identified the trigger: *"the previous block was caused by a trailing period artifact in my task text"* — the path token was captured as **`C:\OfficeMCP.` (with the trailing dot)**, which the gate treated as a *different* path outside the work folder. The user's summary: **"i cannot save file to BOTH folders c:\temp\test and default folder C:\OfficeMCP"** — the `c:\temp\test` half is the by-design containment refusal (documented, bug `no-powerpoint-tool`); the `C:\OfficeMCP` half is the false refusal this bug is about: the user named the exact work folder and was still refused.

## Symptom

A natural-sentence prompt ending a path with punctuation — *"…save it to C:\OfficeMPC."* (period), *",", ")"* — extracts the path token with the trailing punctuation attached; normalization keeps it (`/mnt/c/officemcp.`), and the prefix-based containment check fails, refusing the task as "outside the work folder" **even though the user named the work folder exactly**. Expected: the work-folder path in a sentence is recognized and the task proceeds. The same false refusal exists in the **file lane** ("create a folder in C:\temp.") and the **launch lane** ("run C:\tools\mytool.exe." → the dot defeats the `.exe` check).

## Reproduction

Deterministic, reproduced in this assessment (no network, no agent):

1. `gate_office("create a PowerPoint file named test1 with the text Hello and save it to C:\\OfficeMCP.", "C:\\OfficeMCP")` → **blocked**: *"Blocked: C:\OfficeMCP. is outside the Office work folder C:\OfficeMCP"* — the false refusal, while the identical prompt **without** the period → **ok**.
2. Token-level evidence: `normalize_path("C:\\OfficeMCP.")` → **`'/mnt/c/officemcp.'`** — the trailing dot survives; `normalize_path("C:\\OfficeMCP")` → `'/mnt/c/officemcp'`.
3. File lane: `gate_task("create a folder probe_dot in C:\\temp.")` → **blocked**: *"/mnt/c/temp. is outside the active root /mnt/c/temp"*.
4. Trailing comma `C:\OfficeMCP,` and closing paren `(C:\OfficeMCP)` → **blocked** — the same class.
5. The user's live transcript confirms the end-to-end behavior: the chat relayed the blocked verdict after the user asked to save to the default folder.

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_gate.py` — `_RE_PATH_TOKEN` (`[A-Za-z]:[\\/]\S*`-style capture) swallows trailing punctuation into the token; **`normalize_path` never strips it**, and the shared containment checks (`startswith(root)`) then fail on the punctuated form. This function is shared by all three gates — one defect, three lanes.
- `src/agentic_rag_mcp/office_gate.py` — inherits `_RE_PATH_TOKEN`/`normalize_path` from `hermes_gate` (no separate defect).
- `src/agentic_rag_mcp/hermes_launch_gate.py` — same inheritance; the trailing dot also defeats its `.exe` suffix check.

## Root Cause Hypothesis

**High confidence (proven, not hypothesized).** The path-token regex captures `\S*` including sentence punctuation; `normalize_path` preserves it; Windows paths cannot legally end with dots, spaces, or most punctuation in a filename — so the punctuated token denotes a nonexistent path that fails the prefix containment. Every natural-language prompt that ends a sentence with the folder name gets falsely refused. The failure is fail-safe (over-refusal, never over-allowance), but it blocks the *designed* save location and makes the containment appear broken to the user — the exact "cannot save to either folder" experience.

## Proposed Remediation

**Preferred**: strip Windows-illegal trailing characters in `normalize_path` (one place, all three lanes): rstrip the token with the set of characters that cannot terminate a real Windows path — whitespace plus `.,;:!?'"»‹)]}` (never backslash or `/`). This is lossless for every legal path and closes the false-refusal class at the root. Add a trailing-punctuation case to each gate's unit tests, hot-patch the sidecar, and re-probe live (the exact user prompt → ok).

**Alternatives**:
- Strip punctuation at each gate's token-extraction site (three places, more code — dominated by the shared-normalize fix).
- Instruct the agent to strip punctuation before calling tools (behavioral, unreliable — the transcript shows the agent's own relayed text carried the period; the gate must be the enforcement point, per spec 028/029 precedent).

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_gate.py` (`normalize_path` — the rstrip)
- `tests/unit/test_hermes_gate.py` · `tests/unit/test_hermes_launch_gate.py` · `tests/unit/test_office_gate.py` (one trailing-punctuation case each)

**Tests to add or update**:
- File gate: "create a folder probe in C:\temp." → ok (in-root after strip)
- Office gate: the exact user prompt ("…save it to C:\OfficeMCP.") → ok
- Launch gate: "run C:\Windows\System32\notepad.exe." → recognized as the .exe (allowed), not an executables-only refusal
- Negative control: out-of-root with punctuation ("C:\Other." → still blocked; the strip must not weaken containment)

## Risks & Considerations

- Security review of the strip: removing only *trailing* punctuation cannot turn an outside path into an inside one (containment is prefix-based; the strip shortens the tail toward the legal path). The negative-control test pins this.
- The fix lands in the shared file-lane normalizer — the 028 contract tests must stay green (they use clean paths; the strip is a no-op for them).
- The transcript's retry (no path at all) may additionally have failed for the already-documented MCP-transport flakiness — separate, documented in DEPLOY.md; this bug covers the deterministic false refusal only.
- Hot-patch + republish: the gate is sidecar code (docker cp + restart); no DSL change needed.

## Open Questions

- [NEEDS CLARIFICATION: none blocking — the reproduction is deterministic and the fix is mechanically safe.]
