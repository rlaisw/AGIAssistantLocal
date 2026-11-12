"""Spec 029 — the Hermes program-launch gate.

Pure verb classification + target extraction + launch-rule enforcement
(research R2, contracts §2). One request may launch ONE program — by bare
application name or by full ``.exe`` path; never with launch arguments,
never shell/PowerShell phrasing, never scripts or shortcuts
(executables-only). A task naming no target — or two targets — is blocked
with an ask-back (FR-011): never assumed. The verdict is the only signal
that reaches the Hermes client: blocked verdicts never produce a call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .hermes_gate import _RE_PATH_TOKEN, normalize_path

OP_LAUNCH_APP = "launch-app"
OP_ASK_BACK = "ask-back"
OP_UNSUPPORTED = "unsupported"

_LAUNCH_SCOPE = ("v1 launch scope: one program by name or full .exe path only — "
                 "never arguments, never shell/PowerShell, never scripts or shortcuts")

_RE_SHELL = re.compile(
    r"\b(powers?hell|pwsh|(?<!\.)cmd(\.exe)?|command[-\s]?(?:prompt|line)|terminal|bash)\b",
    re.IGNORECASE)
_RE_WITH_ARGS = re.compile(r"\b(with|using|passing)\b", re.IGNORECASE)
_RE_CHAINING = re.compile(r"[;|&]")
_RE_QUOTED = re.compile(r"'([^']+)'|\"([^\"]+)\"")
# the trailing desktop-automation clause: "… and/then/comma type/click/press …"
# (typing-search bug, 2026-11-06: comma-separated clause lists must split too;
#  blocked-…-named-20261108: search/find/look up are the most common companions,
#  and a bare-space verb ("open chrome search x") splits when a launch head
#  precedes it — otherwise "open search" stays a (ask-back) name request;
#  the-launcher-…-at-a-time, 2026-11-08: observe verbs (show me/display/view)
#  join the comma/and/then form only — no bare-space, to protect app names)
_RE_GUI_CLAUSE = re.compile(
    r"(?:\b(?:and|then)\s+|,\s*)"
    r"(type|click|press|enter|scroll|type\s+into|search|find|look\s+up|google|show|display|view|check|read|tell\s+me)\b.*$"
    r"|\s+(search|find|look\s+up|google)\b.*$",
    re.IGNORECASE)

# canonical multiword Windows app names -> their launch targets
# (the-launcher-…-at-a-time, 2026-11-08: "control panel" is ONE app, not two).
# Matched as consecutive extracted-name pairs; unknown pairs still ask back.
_COMPOUND_APPS = {
    "control panel": "control",
    "file explorer": "explorer",
    "task manager": "taskmgr",
    "device manager": "devmgmt",
    "registry editor": "regedit",
    # the-launch-was-blocked... (2026-11-12): "MS Word" parsed as TWO apps
    # (names ['MS','Word']) -> honest-but-pointless MULTI ask-back; the
    # whole Microsoft family was missing from the compound map
    "ms word": "word",
    "ms excel": "excel",
    "ms powerpoint": "powerpoint",
    "ms outlook": "outlook",
    "ms access": "access",
    "ms edge": "edge",
    "ms teams": "teams",
    "ms paint": "mspaint",
    "ms onenote": "onenote",
    "microsoft onenote": "onenote",
    "microsoft word": "word",
    "microsoft excel": "excel",
    "microsoft powerpoint": "powerpoint",
    "microsoft outlook": "outlook",
    "microsoft edge": "edge",
    "microsoft teams": "teams",
}
# secondary imperative clauses that are desktop actions, not launch targets
# ("open a new tab" after the real launch target) — routed to the followup
_RE_SECONDARY_OPEN = re.compile(
    r",\s*(?:and\s+)?(?:open|launch|start|go\s+to)\s+a?\s*"
    r"(new\s+tab|new\s+window|incognito\s+tab|private\s+tab)\b",
    re.IGNORECASE)

_FILLERS = {
    "open", "launch", "start", "run", "begin", "execute", "go", "please",
    "can", "could", "would", "should", "will", "shall", "may", "might",
    "you", "i", "me", "my", "the", "a", "an", "on", "in", "at", "to", "for",
    "of", "up", "now", "it", "that", "this", "and", "also", "or", "then",
    "computer", "windows", "pc", "machine", "desktop", "app", "application",
    "program", "just", "really", "some", "there", "here", "want", "need",
    "like", "help", "try", "do", "does", "did",
    # context nouns around a real app name (blocked-…-named-20261108:
    # "open a new session chrome browser" parsed session/browser as apps).
    # "default browser" is matched as a compound BEFORE filler filtering,
    # so adding "browser" here is safe.
    "new", "session", "browser",
}

# objects that are not applications — a launch prompt whose only object is
# one of these asks back (launching files/documents is out of scope, FR-011)
_NON_APP_NOUNS = {
    "file", "files", "folder", "folders", "directory", "document", "documents",
    "doc", "docs", "pdf", "spreadsheet", "sheet", "presentation", "deck",
    "image", "photo", "picture", "video", "song", "music", "email",
    "message", "link", "url", "website", "page",
}

_NO_APP = (f"Blocked: no application named in the task — ask the user which "
           f"application to launch ({_LAUNCH_SCOPE})")
_MULTI = (f"Blocked: more than one application named — ask the user which one "
          f"to launch ({_LAUNCH_SCOPE})")
_ARGS = (f"Blocked: launch arguments are refused — launch one program by name "
         f"or full .exe path only ({_LAUNCH_SCOPE})")
_EXE_ONLY = (f"Blocked: only program executables (.exe) can be launched by path — "
             f"scripts, shortcuts, and non-executable targets are refused ({_LAUNCH_SCOPE})")


@dataclass
class LaunchVerdict:
    decision: str              # "ok" | "blocked"
    reason: str | None         # set when blocked — names the violated rule
    operation: str             # launch-app | ask-back | unsupported
    target: str | None         # bare name as typed, or canonical host path
    kind: str | None           # "name" | "path"
    sanitized_task: str | None  # "Launch the program …" — the only text sent downstream
    desktop_followup: str | None = None  # "and type/click …" clause (blocked-…-named, 2026-11-06)


def _blocked(reason: str, target: str | None = None,
             kind: str | None = None) -> LaunchVerdict:
    return LaunchVerdict("blocked", reason, OP_UNSUPPORTED, target, kind, None)


def _ask_back(reason: str) -> LaunchVerdict:
    return LaunchVerdict("blocked", reason, OP_ASK_BACK, None, None, None)


def _is_arg_token(tok: str) -> bool:
    if tok.startswith("-"):
        return True
    if tok.startswith("/") and "/" not in tok.lstrip("/") and not tok.lower().startswith("/mnt"):
        return True
    return "=" in tok


# no-response-test-playwright (2026-11-11, spec 037): a typing/search/reading
# followup on a BROWSER is a WEB intent, not desktop automation — GUI-typing
# into a browser stalls (focus/idle policies) and dies silently inside the
# ~300 s tool window. The launch lane refuses it with an honest re-route to
# the browser lanes; the DSL carries the same rule (its prompt-level twin).
_BROWSER_PROGRAMS = {"chrome", "msedge", "edge", "firefox", "brave",
                      "browser", "safari", "opera", "vivaldi",
                      "default browser"}

# why-not-officemcp (2026-11-12): a typing/writing/clicking followup on an
# OFFICE program is a DOCUMENT operation, not desktop automation — the
# office lane (hermes_office_task -> OfficeMCP COM) serves it directly with
# no GUI automation and no USER_CONTROL consent waits (the measured launch+
# GUI-typing path: 196 s; the office gate accepts the same task as
# document-write). The launch lane refuses with an honest re-route.
# owner decision 2026-11-12 ("at this phase ignore OneNote and others"):
# the office lane routes ONLY Word/Excel/PowerPoint/Outlook — Access and
# OneNote stay ORDINARY desktop apps (launch + followup) until a later
# phase routes them, so they must NOT be refused here
_OFFICE_PROGRAMS = {"word", "excel", "powerpoint", "outlook",
                     "ms word", "ms excel", "ms powerpoint",
                     "ms outlook", "microsoft word", "microsoft excel",
                     "microsoft powerpoint", "microsoft outlook"}
_OFFICE_FOLLOWUP_REFUSAL = (
    "Blocked: '{app}' is an Office application — typing, writing, or "
    "clicking in it is a DOCUMENT task (the office lane controls Word, "
    "Excel, PowerPoint, and Outlook directly via COM: faster, no desktop "
    "automation, no consent waits). Re-route: call "
    "hermes_office_task(task, conversation_id) with the full task text "
    "unchanged. The launch lane only starts the bare program; document "
    "work in Office apps never rides GUI typing.")
_BROWSER_FOLLOWUP_REFUSAL = (
    "Blocked: '{app}' is a browser — typing, searching, or reading in it is a "
    "web/browser task (spec 037), not a program launch or desktop automation; "
    "re-ask it as a browser request (e.g. \"search for today's weather in Hong "
    "Kong\" / \"open this page and tell me what it says\") and it will route to "
    "the browser lane, which types into the page and reports what it observes. "
    "GUI-typing into a browser is never performed from the launch lane.")


def gate_launch(task: str, home: str = "/home/administrator") -> LaunchVerdict:
    """The launch gate pipeline (contracts §2, in order).

    1. empty task → ask-back; shell/command-line phrasing → refused (FR-005).
    2. explicit argument passing ("with/using") and chaining (; | &) → refused.
    3. quoted phrases are valid only as THE single target.
    4. path tokens (reusing the file gate's normalization) must end ``.exe``
       — scripts/shortcuts/non-executables refused (FR-004); bare ``/word``
       tokens are argument flags, not paths.
    5. two targets → ask-back which one; no target → ask-back (FR-011).
    6. a bare name may carry no extension or ``.exe`` — anything else is an
       executables-only refusal.

    blocked-more-than-one-application-named (2026-11-06): a launch-plus-GUI
    request ("open chrome and type www.google.com") is NOT two applications.
    Split it at the GUI clause — the launch half runs the full scope checks
    above, the trailing "type/click/press …" clause rides along as
    ``desktop_followup`` for the agent's WindowsMCP tools. Shell/argument/
    chaining rules still apply to BOTH halves.
    """
    task = (task or "").strip()
    if not task:
        return _ask_back(_NO_APP)
    # GUI-clause split: "… (and|then|,) (type|click|press|enter|scroll|say) …"
    # plus secondary desktop imperatives ("open a new tab") → followup
    followup = None
    m = _RE_GUI_CLAUSE.search(task)
    m2 = _RE_SECONDARY_OPEN.search(task)
    cut = min(x.start() for x in (m, m2) if x) if (m or m2) else None
    if cut is not None:
        followup = task[cut:].lstrip(" ,.").strip()
        task = task[:cut].strip(" ,.;")
    if _RE_SHELL.search(task) or _RE_SHELL.search(followup or ""):
        # spec 033: the refusal stands (this gate stays shell-free) but now
        # points users at the command lanes — 033 read-only diagnostics and
        # 034 confirmed PowerShell (spec 034 pointer)
        return _blocked(f"Blocked: shell/PowerShell/command-line requests are "
                        f"refused ({_LAUNCH_SCOPE}) — for read-only diagnostics "
                        f"(ipconfig, systeminfo, tasklist, whoami, hostname, "
                        f"ping/nslookup/tracert with one host or IP), ask for "
                        f"the command by name and the run-command lane will run "
                        f"it; for general PowerShell commands, ask for the "
                        f"command and confirm it in chat — the PowerShell lane "
                        f"runs confirmed commands")
    if _RE_WITH_ARGS.search(task):
        return _blocked(f"Blocked: launch arguments and documents are refused — "
                        f"launch one program by name or full .exe path only "
                        f"({_LAUNCH_SCOPE})")
    if _RE_CHAINING.search(task) or _RE_CHAINING.search(followup or ""):
        return _blocked(f"Blocked: chained commands are refused — one program "
                        f"per request ({_LAUNCH_SCOPE})")

    quoted = [(a or b) for a, b in _RE_QUOTED.findall(task)]
    if len(quoted) > 1:
        return _ask_back(_MULTI)

    path_targets: list[str] = []
    for tok in _RE_PATH_TOKEN.findall(task):
        norm = normalize_path(tok, home)
        if norm is None:
            continue
        if norm.lower().endswith(".exe"):
            path_targets.append(norm)
            continue
        if tok.startswith("/") and "/" not in tok.lstrip("/"):
            return _blocked(_ARGS)          # single-segment /word = argument flag
        return _blocked(_EXE_ONLY, target=norm, kind="path")

    if len(path_targets) > 1 or (path_targets and quoted):
        return _ask_back(_MULTI)
    if path_targets:
        target = path_targets[0]
        return LaunchVerdict("ok", None, OP_LAUNCH_APP, target, "path",
                             f"Launch the program at '{target}' — no arguments.",
                             desktop_followup=followup)

    # ---- bare-name extraction (no path tokens)
    text = _RE_QUOTED.sub(" ", task)
    tokens = [t.strip(".,!?;:()[]{}\"") for t in text.split()]
    names: list[str] = []
    # "default browser" is one compound target (blocked-…-named, 2026-11-06):
    # the agent resolves which browser is default rather than the gate guessing
    if [t.lower() for t in tokens if t] and [t.lower() for t in tokens if t][-2:] == ["default", "browser"]:
        names = ["default browser"]
    else:
        for tok in tokens:
            if not tok or tok.lower() in _FILLERS:
                continue
            if _is_arg_token(tok):
                return _blocked(_ARGS)
            names.append(tok)
        if names and names[0].lower() == "default" and len(names) > 1 and names[1].lower() == "browser":
            names = ["default browser"]

    if quoted:
        target = quoted[0]
        if names:
            return _ask_back(_MULTI)
        low = target.lower()
        if low in _BROWSER_PROGRAMS and followup:
            return _blocked(_BROWSER_FOLLOWUP_REFUSAL.format(app=target),
                            target=target)
        if low in _OFFICE_PROGRAMS and followup:
            return _blocked(_OFFICE_FOLLOWUP_REFUSAL.format(app=target),
                            target=target)
        if "." in low and not low.endswith(".exe"):
            return _blocked(_EXE_ONLY, target=target)
        return LaunchVerdict("ok", None, OP_LAUNCH_APP, target, "name",
                            f"Launch the program '{target}' — no arguments.",
                            desktop_followup=followup)

    if not names:
        return _ask_back(_NO_APP)
    # compound app names (the-launcher-…-at-a-time, 2026-11-08): merge
    # consecutive-name pairs that match a canonical multiword app ("control
    # panel" -> "control"); unknown pairs stay two names -> honest MULTI ask-back
    merged: list[str] = []
    i = 0
    while i < len(names):
        if i + 1 < len(names):
            mapped = _COMPOUND_APPS.get(f"{names[i].lower()} {names[i+1].lower()}")
            if mapped:
                merged.append(mapped)
                i += 2
                continue
        merged.append(names[i])
        i += 1
    names = merged
    if len(names) > 1:
        return _ask_back(_MULTI)
    target = names[0]
    low = target.lower()
    if low in _NON_APP_NOUNS:
        return _ask_back(_NO_APP)
    # no-response-test-playwright (2026-11-11): browser + followup is a web
    # intent — refuse with the re-route, never a stalled silent GUI attempt
    if low in _BROWSER_PROGRAMS and followup:
        return _blocked(_BROWSER_FOLLOWUP_REFUSAL.format(app=target),
                        target=target)
    if low in _OFFICE_PROGRAMS and followup:
        return _blocked(_OFFICE_FOLLOWUP_REFUSAL.format(app=target),
                        target=target)
    if "." in low and not low.endswith(".exe"):
        return _blocked(_EXE_ONLY, target=target)
    return LaunchVerdict("ok", None, OP_LAUNCH_APP, target, "name",
                        f"Launch the program '{target}' — no arguments.",
                        desktop_followup=followup)
