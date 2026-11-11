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

# Spec 038 (R3): the never-list moved to the SHARED module —
# task_gateway.neverlist.NEVER_PATTERNS is this gate's own pattern table
# (object-identical import; the suite re-pins against the shared source).
from .task_gateway.neverlist import NEVER_PATTERNS as _NEVER_PATTERNS


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
    # never-list first (FR-002 outranks the one-per-request ask-back): a
    # smuggled system-integrity command must refuse with the integrity rule
    # named even when it also happens to be a second statement
    for name, pattern in _NEVER_PATTERNS:
        m = pattern.search(draft)
        if m:
            return _blocked(
                f"Blocked: the drafted command targets system integrity "
                f"(matched: {name}; near {m.group(0)!r}) — disk-level "
                f"destruction and boot/recovery/encryption-state operations "
                f"are never executable from chat, even with confirmation.")
    # FR-006 (analysis C1, 2026-11-10): one command per request — a draft
    # with statement separators outside string/block/comment context is a
    # smuggled second command; ask back for one command. A `;` directly after
    # a closing `}` is a pipeline continuation (legal), not a separator.
    # strings, blocks, and comments are scrubbed WITH their content; a `;`
    # inside (or closing) a block is continuation syntax, not a separator —
    # the [^{}\n]* scrub erases the content, so the closing `};` becomes
    # part of the same scrub when the block span includes it
    rough = re.sub(r"'[^'\n]*'|\"[^\"\n]*\"|\{[^{}\n]*\}\s*;?|#.*", " ", draft)
    if ";" in rough or len(rough.splitlines()) > 1:
        return _blocked("Blocked: the drafted text contains more than one "
                        "command (statement separators or multiple lines) — "
                        "one command per request; draft a single command and "
                        "show it for confirmation.")
    return PSVerdict("ok", None)
