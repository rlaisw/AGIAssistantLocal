"""Spec 033 — the run-command gate: read-only diagnostics allowlist (FR-001/002/003).

The gate is the ONLY route from user text to a shell command: it maps natural
language to at most one allowlisted diagnostic, refuses everything else with
the allowlist shown, and never passes raw user text downstream. The allowlist
lives here, in code — never in a prompt (Constitution IV).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_RUN_SCOPE = ("v1 run-command scope: read-only diagnostics only, "
              "one command per request")
_ALLOWLIST = ("ipconfig, systeminfo, tasklist, whoami, hostname, "
              "ping <host>, nslookup <host>, tracert <host>, "
              "Get-Volume (disk space)")

# bare diagnostics — no arguments in v1
_BARE_PHRASES: dict[str, tuple[str, ...]] = {
    "ipconfig": (r"\bipconfig\b", r"\bip\s+config\b", r"\bip\s+address\b",
                 r"\bmy\s+ip\b"),
    "systeminfo": (r"\bsysteminfo\b", r"\bsystem\s+info(?:rmation)?\b",
                  # spec-033 follow-up (the-local-agent-was-NOT-called,
                  # 2026-11-09): systeminfo output carries the System Locale
                  # and Input Locale lines, so locale asks are servable
                  r"\bsystem\s+locale\b", r"\binput\s+locale\b",
                  r"\blocale\s+setting\b"),
    "tasklist": (r"\btasklist\b", r"\btask\s+list\b", r"\brunning\s+process(?:es)?\b",
                 r"\brunning\s+tasks\b", r"\bwhats\s+running\b",
                 r"\bwhat\s+is\s+running\b"),
    "whoami": (r"\bwhoami\b", r"\bwho\s+am\s+i\b"),
    "hostname": (r"\bhostname\b", r"\bhost\s+name\b", r"\bcomputers?\s+name\b"),
    # spec-033 amendment (disk-space-…, 2026-11-09): a NAMED RECIPE — disk
    # phrases map to the fixed read-only cmdlet Get-Volume; the user's words
    # never become command syntax, and this is the ONLY allowlisted cmdlet
    # (the generic cmdlet refusal stays for everything unlisted)
    "Get-Volume": (r"\bget[-\s]?volume\b", r"\bdisk\s+space", r"\bhard\s?disks?\b",
                   r"\bdisk\s+usage\b", r"\bfree\s+space\b", r"\bdrive\s+space\b",
                   r"\bstorage\s+space\b"),
}
_RECIPE_CMDS = {"get-volume"}  # exempt from the generic cmdlet refusal
# targeted diagnostics — exactly one simple host/IP token
_TARGETED_PHRASES: dict[str, tuple[str, ...]] = {
    "ping": (r"\bping\s+(?:the\s+)?(?:host\s+)?(?P<t>[A-Za-z0-9.-]+)",
             r"\breach\s+(?P<t>[A-Za-z0-9.-]+)"),
    "nslookup": (r"\bnslookup\s+(?:for\s+)?(?P<t>[A-Za-z0-9.-]+)",
                 r"\bdns\s+lookup\s+(?:for\s+)?(?P<t>[A-Za-z0-9.-]+)"),
    "tracert": (r"\btracert\s+(?:to\s+)?(?P<t>[A-Za-z0-9.-]+)",
                r"\btraceroute\s+(?:to\s+)?(?P<t>[A-Za-z0-9.-]+)",
                r"\btrace\s+route\s+(?:to\s+)?(?P<t>[A-Za-z0-9.-]+)"),
}

# shell syntax that never rides along — quoting smuggles included
_RE_SYNTAX = re.compile(r"[|;&<>`\"$%]")
# a standalone apostrophe is a quote, not a contraction ("what's")
_RE_QUOTE_APOS = re.compile(r"(?<![A-Za-z])'|'(?![A-Za-z])")
# a whitespace-led -/ token is a flag ("tasklist /v", "ping a -l 1")
_RE_FLAG = re.compile(r"\s[-/][A-Za-z0-9]")
# CamelCase cmdlets (Get-NetIPAddress, Invoke-Command) — lowercase variants
# ride the refused-word set; this must NOT match "windows-mcp" (the framing
# guard below skips it, including the capitalized "Windows-MCP" spelling)
_RE_CMDLET = re.compile(r"\b[A-Z][A-Za-z]*(?:-[A-Za-z]+)+\b")

# words that can only mean a refused command (never a filler); "powershell"
# and friends are framing words exempted here so FR-009's "use powershell to
# show my ip" routes to the allowlisted intent instead of refusing
_FRAMING = {"powershell", "powershell.exe", "pwsh", "shell", "command",
            "commands", "command-line", "windows-mcp", "terminal", "cli"}
_REFUSED_WORDS = {
    "cmd", "cmd.exe", "bash", "sh", "zsh", "del", "delete", "erase", "rm",
    "rmdir", "rd", "format", "shutdown", "restart", "reboot", "reg",
    "regedit", "netsh", "net", "sc", "taskkill", "kill", "copy", "xcopy",
    "move", "rename", "ren", "mkdir", "md", "curl", "wget", "python",
    "python3", "pip", "node", "npm", "echo", "set", "export", "diskpart",
    "wsl", "ssh", "ftp", "telnet", "invoke-command", "invoke-expression",
    "remove-item", "new-item", "stop-process", "start-process",
    "restart-computer", "stop-service", "start-service",
}

_FILLERS = {
    "show", "me", "my", "the", "a", "an", "on", "in", "at", "to", "for",
    "of", "is", "are", "am", "what", "whats", "can", "could", "would",
    "you", "i", "please", "run", "execute", "help", "and", "windows",
    "computer", "computers", "pc", "machine", "desktop", "current",
    "today", "now", "do", "does", "did", "give", "list", "tell", "use",
    "with", "also", "it", "that", "this", "some", "want", "need", "like",
    "try", "address", "info", "information", "process", "processes",
    "running", "tasks", "up",
} | _FRAMING


@dataclass
class RunVerdict:
    decision: str            # "ok" | "blocked" | "ask-back"
    command: str | None      # the allowlisted command on "ok"
    target: str | None        # the single host/IP for targeted commands
    reason: str | None        # verbatim refusal / ask-back text otherwise


def _blocked(reason: str) -> RunVerdict:
    return RunVerdict("blocked", None, None, reason)


def _ask_back(reason: str) -> RunVerdict:
    return RunVerdict("ask-back", None, None, reason)


def _not_allowed(word: str) -> RunVerdict:
    return _blocked(f"Blocked: '{word}' is not on the run-command allowlist — "
                    f"read-only diagnostics only, one command per request. "
                    f"Allowed: {_ALLOWLIST}")


def _tokens(text: str) -> list[str]:
    return [t.strip(",.!?;:()[]{}") for t in text.split()]


def gate_run_command(task: str) -> RunVerdict:
    """Map one request to at most one allowlisted command, or refuse.

    Pipeline (deterministic, spec FR-001/002/003):
    1. empty → ask-back; quote-like apostrophes, shell syntax, flags → refused.
    2. CamelCase cmdlets and refused words → not-on-allowlist (mixed prompts
       naming one allowed + one refused element refuse wholesale — the
       refused part never executes, spec US2 scenario 3).
    3. allowlist intent match: two commands → ask-back; exactly one →
       bare commands take no dotted argument; targeted commands take
       exactly one simple host/IP with filler-only leftovers.
    4. no intent → ask-back offering the list (the gate never guesses).
    """
    text = (task or "").strip().lower()
    if not text:
        return _ask_back(f"Ask-back: which read-only diagnostic do you want? "
                        f"The run-command lane runs only: {_ALLOWLIST}")
    if _RE_QUOTE_APOS.search(text) or _RE_SYNTAX.search(text):
        return _blocked(f"Blocked: pipes, redirection, separators, quotes, and "
                        f"similar shell syntax are refused — one clean command "
                        f"per request ({_RUN_SCOPE}). Allowed: {_ALLOWLIST}")
    # contractions ("what's") are natural text, not quotes — strip after the
    # quote-like check so "what's running" maps while '8.8.8.8' refuses
    text = re.sub(r"(?<=[A-Za-z])'(?=[A-Za-z])", "", text)
    # a named refused command outranks the generic flag refusal — the reason
    # must name it ("taskkill /im …" refuses taskkill, not the flag)
    m = _RE_CMDLET.search(task or "")
    if (m and m.group(0).lower() not in _FRAMING
            and m.group(0).lower() not in _RECIPE_CMDS):
        return _not_allowed(m.group(0))
    for tok in _tokens(text):
        if tok and tok not in _FRAMING and tok in _REFUSED_WORDS:
            return _not_allowed(tok)
    if _RE_FLAG.search(text):
        return _blocked(f"Blocked: flags and switches are refused — one bare "
                        f"command per request ({_RUN_SCOPE}). Allowed: {_ALLOWLIST}")

    # intent extraction
    matched: dict[str, re.Match | None] = {}
    for cmd, phrases in _BARE_PHRASES.items():
        for pat in phrases:
            m = re.search(pat, text)
            if m:
                matched[cmd] = m
                break
    for cmd, phrases in _TARGETED_PHRASES.items():
        for pat in phrases:
            m = re.search(pat, text)
            if m:
                matched[cmd] = m
                break
    if len(matched) > 1:
        return _ask_back(f"Ask-back: more than one command named — one command "
                         f"per request. Which one? Allowed: {_ALLOWLIST}")
    if not matched:
        return _ask_back(f"Ask-back: which read-only diagnostic do you want? "
                         f"The run-command lane runs only: {_ALLOWLIST}")
    cmd, m = next(iter(matched.items()))
    if cmd in _BARE_PHRASES:
        # bare commands take no arguments in v1 — any dotted non-filler token
        # (hostname/IP/path) or drive-letter token ("C:", "C:\…") is a
        # smuggled argument; colons are kept here because _tokens strips them
        for raw in text.split():
            tok = raw.strip(",.!?;()[]{}")
            if tok and tok not in _FILLERS and (
                    "." in tok or re.match(r"^[a-z]:", tok)):
                return _blocked(f"Blocked: {cmd} takes no arguments in v1 "
                                f"({_RUN_SCOPE}). Allowed: {_ALLOWLIST}")
        return RunVerdict("ok", cmd, None, None)
    # targeted: exactly one simple host/IP, filler-only leftovers after it
    target = (m.group("t") or "").strip(".-")
    end = m.end()
    for tok in _tokens(text[end:]):
        if tok and tok not in _FILLERS and tok not in _FRAMING:
            return _blocked(f"Blocked: ping/nslookup/tracert take exactly one "
                            f"simple host or IP (letters, digits, dots, "
                            f"hyphens — one token, no flags). "
                            f"Allowed: {_ALLOWLIST}")
    if not target:
        return _ask_back(f"Ask-back: {cmd} needs exactly one host or IP — "
                         f"which one? Allowed: {_ALLOWLIST}")
    return RunVerdict("ok", cmd, target, None)
