"""Spec 034 — the PowerShell-lane never-list gate (FR-002).

The floor no prompt or confirmation can get under: a closed pattern set,
enforced in gate code, scanned over the COMPLETE exact draft text at
registration shape and re-scannable at execution. Clean real PowerShell
(pipes, filters, Remove-Item, service/process control) passes — only
system-integrity destruction refuses. The list is amendment territory by
spec change only, never a prompt (Constitution IV).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (class name, pattern) — case-insensitive, scanned against the whole draft
_NEVER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pat, re.IGNORECASE))
    for name, pat in [
        # volume format/wipe: classic "format D:" and the Format-Volume cmdlet
        # (display cmdlets Format-Table/List/Wide/Custom do NOT match — they
        # lack the volume target / cmdlet name)
        ("volume format/wipe", r"\bformat-volume\b"),
        ("volume format/wipe", r"\bformat\s+[a-z]:"),
        ("disk partitioning (diskpart)", r"\bdiskpart\b"),
        ("boot configuration", r"\b(bcdedit|bootcfg|bootrec)\b"),
        ("shadow-copy deletion", r"\bvssadmin\b[^;|&]*\bdelete\b"),
        ("Windows recovery (reagentc)", r"\breagentc\b"),
        ("disk encryption state (BitLocker)", r"\bmanage-bde\b"),
        ("disk wipe (cipher /w)", r"\bcipher\b[^;|&]*\s/w"),
        ("disk initialization/clear", r"\b(clear-disk|initialize-disk|restore-disk)\b"),
        ("secure-delete wiping", r"\bsdelete\b"),
    ]
)


@dataclass
class PSVerdict:
    decision: str            # "ok" | "blocked"
    reason: str | None       # names the matched class on blocked


def _blocked(reason: str) -> PSVerdict:
    return PSVerdict("blocked", reason)


def gate_powershell(draft: str) -> PSVerdict:
    """Scan one exact draft against the never-list (spec FR-002).

    The scan covers the complete draft text — chained operators, pipes,
    redirections, and nested calls included — so a never-list element
    smuggled anywhere refuses the whole draft. Confirmation can never
    override this gate (the tool re-scans at execution as defense-in-depth).
    """
    draft = (draft or "").strip()
    if not draft:
        return _blocked("Blocked: no command drafted — draft the exact "
                        "command first and show it to the user for "
                        "confirmation.")
    for name, pattern in _NEVER_PATTERNS:
        m = pattern.search(draft)
        if m:
            return _blocked(
                f"Blocked: the drafted command targets system integrity "
                f"(matched: {name}; near {m.group(0)!r}) — disk-level "
                f"destruction and boot/recovery/encryption-state operations "
                f"are never executable from chat, even with confirmation.")
    return PSVerdict("ok", None)
