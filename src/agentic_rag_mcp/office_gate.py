"""Spec 030 — the Office task gate.

Pure classification + policy (contract §2). Kinds: document-write /
document-read / compose-email / send-confirmation / cancel / continue.
Policy: save/read at any location the user names (spec 031 — any drive,
any folder; unnamed saves use the default work folder); prompt-borne
code-execution refused (macro/VBA/DDE/external-link content — v1 writes
literal values only); mailbox-destructive operations refused; compose
requires an explicit recipient address — never guessed from contacts.
A "send" instruction with a recipient COMPOSES (confirm-before-send,
FR-009); a bare confirmation phrase only resolves against the recorded
pending draft at the tool layer. Blocked verdicts never reach the agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .hermes_gate import _RE_PATH_TOKEN, normalize_path

OP_DOCUMENT_WRITE = "document-write"
OP_DOCUMENT_READ = "document-read"
OP_COMPOSE_EMAIL = "compose-email"
OP_SEND_CONFIRMATION = "send-confirmation"
OP_CANCEL = "cancel"
OP_CONTINUE = "continue"
OP_ASK_BACK = "ask-back"
OP_UNSUPPORTED = "unsupported"

_LITERAL_ONLY = ("Blocked: executable document content (macros, VBA, DDE, "
                 "external-link formulas, scripts) is refused — v1 writes "
                 "literal values only (spec 030 FR-004)")
_MAILBOX = ("Blocked: mailbox-destructive operations are out of v1 scope "
            "(spec 030 — email scope is compose + send only)")
_FORMATTING = ("Blocked: formatting (bold, fonts, colors, number formats, "
               "column widths) is not in v1 — literal content only; "
               "formatting is a named follow-up version (owner decision, "
               "clarify pass 2)")

_RE_CONFIRM = re.compile(
    r"^(?:please\s+)?(?:yes|y|ok|okay|confirmed|confirm|approved|go ahead|"
    r"send it(?: now)?|send the email|send)$", re.IGNORECASE)
_RE_CANCEL = re.compile(
    r"^(?:please\s+)?(?:cancel(?:\s+(?:that|the)\s+(?:email|draft|message))?|"
    r"don'?t send(?:\s+it)?|do not send(?:\s+it)?|never\s?mind)$", re.IGNORECASE)
_RE_CONTINUE = re.compile(
    r"^(?:please\s+)?(?:continue|resume|keep going|go on|"
    r"finish(?:\s+(?:the|it)(?:\s+rest)?)?|do the rest)$", re.IGNORECASE)
_RE_MAILBOX_DESTRUCTIVE = re.compile(
    r"\b(delete|clear|purge|remove|wipe)\b.{0,40}\b"
    r"(e-?mails?|inbox|mailbox|mail\s+folder|drafts?)\b", re.IGNORECASE | re.DOTALL)
_RE_CODE_EXEC = re.compile(
    r"\b(macro|macros|vba|dde\b|run\s+a?\s*script|execute\s+code|"
    r"powershell|cmd\.exe)\b|=\S*!|=\w+\|", re.IGNORECASE)
_RE_FORMATTING = re.compile(
    r"\b(bold|italics?|underline|fonts?|colou?rs?|number\s+format|"
    r"column\s+widths?)\b|"
    r"\b(make|set|apply|change|adjust|format|turn)\b.{0,30}\b"
    r"(style|format|border|font|colou?r)\b", re.IGNORECASE)
_RE_ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_RE_CELL_REF = re.compile(r"\b[A-Za-z]{1,3}\d{1,7}\b")
_RE_OUTLOOK = re.compile(r"\b(e-?mail|mail|outlook|inbox)\b", re.IGNORECASE)
_RE_EXCEL = re.compile(r"\b(excel|workbook|spreadsheet|cell|sheet)\b", re.IGNORECASE)
_RE_WORD = re.compile(r"\b(word|docx?|document)\b", re.IGNORECASE)
_RE_POWERPOINT = re.compile(r"\b(powerpoint|slide|slides|deck|pptx?)\b", re.IGNORECASE)
_RE_READ = re.compile(r"\b(what\s+is|read|show|tell\s+me|check)\b", re.IGNORECASE)


@dataclass
class OfficeGateVerdict:
    decision: str            # "ok" | "blocked"
    reason: str | None       # set when blocked — names the violated rule
    operation: str           # blocked: ask-back|unsupported; ok: the kind
    kind: str | None        # the classified kind (None when blocked)
    app: str | None          # excel | word | powerpoint | outlook | None


def _ok(kind: str, app: str | None) -> OfficeGateVerdict:
    return OfficeGateVerdict("ok", None, kind, kind, app)


def _blocked(reason: str, operation: str = OP_UNSUPPORTED) -> OfficeGateVerdict:
    return OfficeGateVerdict("blocked", reason, operation, None, None)


def _ask_back(reason: str) -> OfficeGateVerdict:
    return OfficeGateVerdict("blocked", reason, OP_ASK_BACK, None, None)


def _infer_app(task: str) -> str | None:
    if _RE_OUTLOOK.search(task):
        return "outlook"
    if _RE_POWERPOINT.search(task):
        return "powerpoint"
    if _RE_EXCEL.search(task) or _RE_CELL_REF.search(task):
        return "excel"
    if _RE_WORD.search(task):
        return "word"
    return None


def gate_office(task: str, office_root: str = "C:\\OfficeMCP",
               home: str = "/home/administrator") -> OfficeGateVerdict:
    """The Office gate pipeline (contract §2, in order)."""
    task = (task or "").strip()
    if not task:
        return _ask_back("Blocked: no Office task stated — ask the user what "
                         "to do in Word, Excel, PowerPoint, or Outlook")

    # mailbox-destructive operations are out of v1 scope
    if _RE_MAILBOX_DESTRUCTIVE.search(task):
        return _blocked(_MAILBOX)

    # prompt-borne code execution — never stored, never executed
    if _RE_CODE_EXEC.search(task):
        return _blocked(_LITERAL_ONLY)

    # formatting is out of v1 — literal content only (owner decision)
    if _RE_FORMATTING.search(task):
        return _blocked(_FORMATTING)

    # spec 031: the work folder is a DEFAULT, not a boundary — named
    # locations anywhere (any drive) pass; content rules still fire wherever
    # the target lives. No path check here anymore.

    # confirmation / cancel resolve against the recorded pending draft;
    # continue resumes the conversation's interrupted task (FR-005)
    has_address = bool(_RE_ADDRESS.search(task))
    if not has_address:
        if _RE_CONFIRM.match(task):
            return _ok(OP_SEND_CONFIRMATION, None)
        if _RE_CANCEL.match(task):
            return _ok(OP_CANCEL, None)
        if _RE_CONTINUE.match(task):
            return _ok(OP_CONTINUE, None)

    # email compose — needs an explicit recipient, never guessed
    if _RE_OUTLOOK.search(task):
        if not has_address:
            return _ask_back("Blocked: no recipient address in the email task — "
                             "ask the user which exact address the email should "
                             "go to (never guess from contacts, spec 030 FR-008)")
        return _ok(OP_COMPOSE_EMAIL, "outlook")

    app = _infer_app(task)
    if _RE_OUTLOOK.search(task) or app == "outlook":
        return _ok(OP_COMPOSE_EMAIL, "outlook")

    kind = OP_DOCUMENT_READ if _RE_READ.search(task) else OP_DOCUMENT_WRITE
    return _ok(kind, app)
