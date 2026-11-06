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
# (typing-search bug, 2026-11-06: comma-separated clause lists must split too)
_RE_GUI_CLAUSE = re.compile(
    r"(?:\b(?:and|then)\s+|,\s*)(type|click|press|enter|scroll|type\s+into)\b.*$",
    re.IGNORECASE)
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
        return _blocked(f"Blocked: shell/PowerShell/command-line requests are "
                        f"refused ({_LAUNCH_SCOPE})")
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
        if "." in low and not low.endswith(".exe"):
            return _blocked(_EXE_ONLY, target=target)
        return LaunchVerdict("ok", None, OP_LAUNCH_APP, target, "name",
                            f"Launch the program '{target}' — no arguments.",
                            desktop_followup=followup)

    if not names:
        return _ask_back(_NO_APP)
    if len(names) > 1:
        return _ask_back(_MULTI)
    target = names[0]
    low = target.lower()
    if low in _NON_APP_NOUNS:
        return _ask_back(_NO_APP)
    if "." in low and not low.endswith(".exe"):
        return _blocked(_EXE_ONLY, target=target)
    return LaunchVerdict("ok", None, OP_LAUNCH_APP, target, "name",
                        f"Launch the program '{target}' — no arguments.",
                        desktop_followup=followup)
