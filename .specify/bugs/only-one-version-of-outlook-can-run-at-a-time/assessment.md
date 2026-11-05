# Bug Assessment: "Only one version of Outlook" dialog — recurrence with a worse second layer: Outlook left COM-unreachable

- **Slug**: `only-one-version-of-outlook-can-run-at-a-time`
- **Created**: 2026-11-05 (overwrites the 2026-11-04 assessment of the same symptom — the prior mitigation did not hold; git history preserves the original)
- **Source**: pasted text ("sorry we re having trouble starting outlook only one version of outlook can run at a time" / "cannot open another Outlook session, thus officemcp cannot open outlook session")
- **Verdict**: valid — recurrence of the 2026-11-04 bug **plus a new, deeper failure layer** the prior fix's escape hatch cannot handle
- **Severity**: high — the Outlook/email lane is fully blocked; a Windows error dialog appears on the user's desktop; Outlook is left running but unreachable for automation, and the standard recovery does not clear it

## Report (verbatim or summarized)

> "sorry we re having trouble starting outlook only one version of outlook can run at a time"
> "cannot open another Outlook session, thus officemcp cannot open outlook session"

## Symptom

Outlook (PID 22252) is running and shows the Drafts folder, but OfficeMCP can neither attach to it (`GetActiveObject: 0x800401E3 Operation unavailable`, `Dispatch: 0x80080005 Server execution failed`) nor start another instance — Windows blocks the second launch with the "Sorry, we're having trouble starting Outlook. Only one version of Outlook can run at a time" dialog. The Office/email lane is therefore dead: no attach, no launch, no compose.

## Reproduction

Today's audit trail (UTC):

1. **05:39:50** — email task: STEP 1 RunningApps reported *"Word, Excel, PowerPoint running; Outlook was not"* — **bad data** (the exact Nov-4 corruption signature; RunningApps missed a running Outlook). STEP 2 `Launch Outlook` was called on that bad data and "returned true" — the second-instance dialog appeared on the desktop, and Outlook ended up in a half-open state.
2. **05:45:33** — channel probe: RunningApps returned "no running Office applications" (also bad), `Launch Word` failed, RunPython args dropped — the known #148459 degradation, **intermittent**: broken at 05:45,
3. **05:54:06** — but working again at 05:54: a RunPython **process probe found OUTLOOK.EXE running (PID 22252, window "Drafts - raymond.lai@tvb.com.hk - Outlook")**. The Nov-4 attach-first fallback then ran exactly as designed — `GetActiveObject`/`Dispatch/EnsureDispatch` — and **both failed with COM errors** (0x800401E3 / 0x80080005). STEP 3 compose failed: no draft was created.
4. Current state: exactly one OUTLOOK.EXE in tasklist (PID 22252) plus the dialog report; OfficeMCP SSE healthy (200).

## Suspected Code Paths

- `src/agentic_rag_mcp/hermes_client.py` — `OFFICE_INSTRUCTIONS`: contains the Nov-4 fix's attach-first rule and the RunningApps-corruption fallback ("try Dispatch/GetComObject to attach"). The fallback assumes **attach always succeeds**; there is no protocol for the attach-fails-but-process-running case. This is the gap.
- `src/agentic_rag_mcp/office_gate.py` — no classification for a user's "restart Outlook" consent path (a follow-up approval to close/relaunch Outlook would currently need ad-hoc interpretation).
- Upstream (`~/.hermes/hermes-agent/`, issue [#148459](https://github.com/NousResearch/hermes-agent/issues/148459)) — RunningApps result corruption recurred (05:39:50, 05:45:33 missed a running Outlook/Word); the degradation is now **intermittent within minutes** (broken 05:45 → healthy 05:54), and the session remove/add+restart recovery no longer clears it.
- OfficeMCP `Launch` — when its application argument is dropped under the degraded session it falls back to its Excel default; when the argument arrives it launches whatever was asked **without an outlook.exe process cross-check**, which is how the second-instance dialog was triggered.

## Root Cause Hypothesis

**High confidence, two stacked causes.** (1) The upstream #148459 degradation corrupted RunningApps again (missed the running Outlook), so the lane launched a second Outlook → the Windows "only one version" dialog — the same mechanism as Nov 4. (2) **New layer:** the blocked second launch left Outlook in a state where its process runs but its COM server is not registered/reachable (0x800401E3/0x80080005 — the classic signature of a launch from a mismatched integrity level or a half-initialized instance blocked by the single-instance mutex). The Nov-4 mitigation (attach on RunningApps doubt) was followed to the letter at 05:54:06 and could not work — attaching is impossible in this state, and retrying Launch just re-shows the dialog. Without a dedicated protocol, the lane has no way out that does not either pop dialogs or kill the user's Outlook with their unsaved draft open.

## Proposed Remediation

**Preferred**: extend the office-lane instructions with an **Outlook attach-failure protocol** (the missing third leg of the Nov-4 fix): when the process probe shows `outlook.exe` running but every attach attempt fails with 0x800401E3/0x80080005 — (a) NEVER call `Launch` again (it can only produce the dialog); (b) report honestly that Outlook is running but its COM server is unreachable, almost certainly from the earlier blocked second launch; (c) offer exactly two user choices in-chat: **"close Outlook yourself and tell me to try again"**, or **"say 'restart Outlook' and I will close it and relaunch it"** — the restart path must require explicit user confirmation (an open Draft with unsaved text is data-loss territory) and then runs taskkill+Launch once. Post the recurrence + intermittency evidence on upstream issue #148459.

**Alternatives**:
- Have OfficeMCP's `Launch` cross-check an outlook.exe process probe itself and refuse with a reason when one is already running but attachable-state is unknown — moves the guard into the Windows service, but OfficeMCP is an upstream package (we already carry local patch notes; one more patch increases drift). Instruction-level is our code and auditable.
- Auto-kill the zombie Outlook — rejected: the user may have an unsaved draft open; silent kills are exactly the class of surprise this stack is designed never to do.

**Files likely to change**:
- `src/agentic_rag_mcp/hermes_client.py` — the attach-failure protocol in `OFFICE_INSTRUCTIONS`
- `src/agentic_rag_mcp/office_gate.py` — only if the "restart Outlook" consent phrase needs a dedicated allowed operation (likely not needed: it flows as a normal office task; keep the gate untouched unless it blocks taskkill-shaped phrasing — verify)
- `tests/unit/test_hermes_office_tool.py` — assert the protocol text is present and matches the audit vocabulary

**Tests to add or update**:
- Unit: the instructions contain the never-launch-when-attach-failed rule and the two consent options verbatim
- Battery (manual, when channel is healthy): with Outlook in the broken state, an email task must end in the honest ask-back, not a Launch retry, and the audit must record the COM error pair

## Risks & Considerations

- The restart-with-consent path kills a user application — must be consent-gated exactly like email sending, and the consent phrase must be unambiguous (avoid matching "restart" chit-chat)
- The upstream degradation is the enabler; until #148459 is fixed upstream, RunningApps can still lie and re-create the broken Outlook state after any recovery
- The dialog itself remains on the user's desktop until dismissed — the tool cannot see or dismiss Windows dialogs
- Immediate user-facing unblock (today): close Outlook manually (the Drafts window is the working instance — closing it clears the dialog if it is still up), reopen it once, then retry the email task; if the channel is also degraded at that moment, the honest error path fires

## Open Questions

- [NEEDS CLARIFICATION: does the "trouble starting Outlook" dialog still sit on the desktop now, or was it dismissed? The kill+relaunch consent path should only be offered when the probe confirms the COM-unreachable state]
- The 05:39:50 "Launch returned true" suggests the second launch partially succeeded before being blocked — whether the surviving PID 22252 is the user's original instance or the half-started second one is unknown (window title suggests a functional instance; the COM errors suggest otherwise)
