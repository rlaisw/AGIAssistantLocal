"""Spec 028 — the Hermes file-task gate.

Pure path normalization + containment + operation allowlist (research R6,
contracts/hermes-file-task.md §2). Every path in a task is normalized to a
canonical host form BEFORE any check; the op-set is an allowlist (create-dir,
write-file, read-file, list-dir); a task naming no location is blocked with
an ask-back (FR-014) — never assumed. The verdict is the only signal that
reaches Hermes: blocked verdicts never produce a call.

Windows semantics honored: drive paths are case-insensitive and ``..``
clamps at the drive root (``C:\\temp\\..\\..\\Windows`` == ``C:\\Windows``).
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass

DEFAULT_ALLOWED_ROOT = "/mnt/c/temp"

# v1 scope (FR-011): anything not in this set is blocked with the scope named.
OP_CREATE_DIR = "create-dir"
OP_WRITE_FILE = "write-file"
OP_READ_FILE = "read-file"
OP_LIST_DIR = "list-dir"
OP_UNSUPPORTED = "unsupported"
OP_ASK_BACK = "ask-back"

_RE_WINDOWS_DRIVE = re.compile(r"^([A-Za-z]):[\\/](.*)$")
# trailing characters that cannot terminate a legal Windows path —
# sentence/markup punctuation the path-token regex may capture
_TRAILING_PUNCT = ".,;:!?)]}>»‹*`"
# Path-like tokens: windows drive style, /mnt/..., ~/..., ~, absolute POSIX
# (including bare "/"). Bare relative filenames are deliberately NOT matched
# (FR-014 ask-back). The lookbehinds stop mid-word picks like "a/b" in prose.
_RE_PATH_TOKEN = re.compile(
    r"[A-Za-z]:[\\/]\S+"
    r"|(?<![\w.])/mnt/\S+"
    r"|~/\S+"
    r"|(?<![\w.])~(?![\w/])"
    r"|(?<![\w.])/\S*"
)

_RE_DESTRUCTIVE = re.compile(
    r"\b(delete|remove|rm|unlink|shred|wipe|erase|clear)\b", re.IGNORECASE)
_RE_RENAME_MOVE = re.compile(r"\b(rename|move|mv)\b", re.IGNORECASE)
_RE_MKDIR = re.compile(
    r"\bmkdir\b"
    r"|\b(create|make|new)\b[^.;!?]{0,24}\b(folder|directory|dir)\b",
    re.IGNORECASE)
_RE_LIST = re.compile(
    r"\b(list|ls)\b"
    r"|\bshow\b[^.;!?]{0,24}\b(files?|folders?|director(?:y|ies)|contents?)\b"
    r"|\bwhat'?s in\b"
    r"|\bcontents? of\b",
    re.IGNORECASE)
_RE_READ = re.compile(r"\b(read|cat|open|tell me about)\b", re.IGNORECASE)
_RE_WRITE = re.compile(
    r"\b(write|save|put|append|store)\b"
    r"|\b(create|make|new)\b[^.;!?]{0,24}\bfile\b",
    re.IGNORECASE)

_SCOPE_NOTE = ("v1 scope: create/write/read/list inside the active root only — "
              "no delete/rename/move/bulk operations")


@dataclass
class SafetyVerdict:
    decision: str            # "ok" | "blocked"
    reason: str | None       # set when blocked — names the active root
    operation: str           # OP_* — "ask-back"/"unsupported" for the FR-014/011 blocks
    normalized_path: str | None


def normalize_path(token: str, home: str, allowed_root: str = DEFAULT_ALLOWED_ROOT) -> str | None:
    """Normalize one path token to a canonical host-side POSIX form.

    Windows drive style (``C:\\x``, case-insensitive) maps to ``/mnt/c/x``
    with ``..`` clamped at the drive root; ``~`` expands; relative tokens
    anchor to the active root; POSIX ``..`` resolves via posixpath BEFORE any
    containment comparison. Paths under ``/mnt/`` are lowercased (drvfs
    semantics); other paths keep their case.
    """
    # Windows paths cannot legally end with dots or spaces, so stripping
    # sentence punctuation the token regex swallows is lossless for every
    # real path — without it "C:\OfficeMCP." fails containment (bug
    # fail-to-save-file, 2026-11-03)
    token = (token or "").strip().strip("\"'").rstrip(_TRAILING_PUNCT)
    if not token:
        return None
    m = _RE_WINDOWS_DRIVE.match(token)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).replace("\\", "/")
        out: list[str] = []
        for seg in rest.split("/"):
            if seg in ("", "."):
                continue
            if seg == "..":
                if out:
                    out.pop()          # clamp: ".." at the drive root stays there
                continue
            out.append(seg)
        return (f"/mnt/{drive}/" + "/".join(out)).lower() if out else f"/mnt/{drive}"
    token = token.replace("\\", "/")
    if token == "~":
        return posixpath.normpath(home)
    if token.startswith("~"):
        token = home + token[1:]
    if not token.startswith("/"):
        token = posixpath.join(allowed_root, token)
    token = posixpath.normpath(token) or "/"
    if token.startswith("/mnt/"):
        token = token.lower()
    return token


def to_windows(path: str) -> str:
    """Display form for answers: ``/mnt/c/temp/x`` → ``C:\\temp\\x`` (FR-008)."""
    m = re.match(r"^/mnt/([A-Za-z])/(.*)$", path)
    if not m:
        return path
    return f"{m.group(1).upper()}:\\{m.group(2).replace('/', chr(92))}"


def _classify_operation(task: str) -> str:
    if _RE_DESTRUCTIVE.search(task) or _RE_RENAME_MOVE.search(task):
        return OP_UNSUPPORTED
    if _RE_MKDIR.search(task):
        return OP_CREATE_DIR
    if _RE_LIST.search(task):
        return OP_LIST_DIR
    if _RE_READ.search(task):
        return OP_READ_FILE
    if _RE_WRITE.search(task):
        return OP_WRITE_FILE
    return OP_UNSUPPORTED


def gate_task(task: str, allowed_root: str | None = None,
              home: str = "/home/administrator") -> SafetyVerdict:
    """The full gate pipeline (contracts §2, in order).

    1. active root = ``allowed_root`` argument (freely settable — clarify Q1)
       normalized, else the default.
    2. normalize every path token in the task; resolve/clamp ``..`` first.
    3. no path tokens at all → ask-back (FR-014), nothing assumed.
    4. op-set allowlist (FR-011) — unsupported ops blocked everywhere.
    5. containment against the active root (FR-004) — after resolution.
    """
    active_root = normalize_path(allowed_root or DEFAULT_ALLOWED_ROOT, home) or DEFAULT_ALLOWED_ROOT

    tokens = _RE_PATH_TOKEN.findall(task or "")
    paths = [p for p in (normalize_path(t, home, active_root) for t in tokens) if p]

    if not paths:
        return SafetyVerdict(
            decision="blocked",
            reason=(f"Blocked: no location named in the task — ask the user where "
                    f"under {active_root} the file or folder should go ({_SCOPE_NOTE})"),
            operation=OP_ASK_BACK,
            normalized_path=None,
        )

    op = _classify_operation(task or "")
    if op == OP_UNSUPPORTED:
        return SafetyVerdict(
            decision="blocked",
            reason=f"Blocked: {_SCOPE_NOTE} — active root {active_root}",
            operation=OP_UNSUPPORTED,
            normalized_path=paths[0],
        )

    prefix = active_root.rstrip("/") + "/"
    outside = [p for p in paths if p != active_root and not p.startswith(prefix)]
    if outside:
        return SafetyVerdict(
            decision="blocked",
            reason=(f"Blocked: {outside[0]} is outside "
                    f"the active root {active_root} ({to_windows(active_root)}) "
                    f"({_SCOPE_NOTE})"),
            operation=op,
            normalized_path=outside[0],
        )

    return SafetyVerdict(decision="ok", reason=None, operation=op,
                         normalized_path=paths[0])
