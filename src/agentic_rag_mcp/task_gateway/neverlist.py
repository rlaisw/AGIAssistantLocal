"""Spec 038 — the SHARED never-list (R3): one source for both gates.

034's PowerShell-lane patterns live here byte-identical —
`hermes_powershell_gate.py` imports NEVER_PATTERNS from this module
(object-identical, so the two gates cannot drift) and its suite re-runs
green unchanged. The refused class is system-integrity destruction
(volume format/wipe, diskpart, boot config, shadow-copy deletion,
recovery, BitLocker state, disk wipes). Repair-class operations
(sfc /scannow, DISM /RestoreHealth without /ResetBase) pass — that is
the tier-2 lane's raison d'être (research R3).

Amendment territory: spec change only, never a prompt (Constitution IV).
"""

from __future__ import annotations

import re

# (class name, pattern) — case-insensitive, scanned against whole text
NEVER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
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
        # spec 041 (2026-11-15, FR-005 + clarification): the
        # remote-access-cutting class — these can sever the owner's remote
        # session (recovery may need physical access) or alter the
        # machine's security boundary; refused ALWAYS, draft and confirm.
        # Boundary per the 2026-11-15 clarification: individual firewall
        # RULE additions/changes are confirmed-only tier-3 operations —
        # only the PROFILE disable matches below.
        ("network adapter disable/enable",
         r"\b(disable|enable)-netadapter\b"),
        ("IP/gateway/route changes",
         (r"\b(new-netipaddress|set-netipaddress|remove-netipaddress"
          r"|new-netroute|remove-netroute|set-netipinterface"
          r"|set-dnsclientserveraddress)\b")),
        ("firewall profile disable",
         r"\bset-netfirewallprofile\b[^;|&]*-enabled\s*:?\s*false\b"),
        ("remote-access configuration",
         (r"\b(fdenytsconnections|set-item\b[^;|&]*terminal"
          r"-?server[^;|&]*fdenytsconnections"
          r"|(enable|disable)-remotedesktop)\b")),
        ("user account changes",
         (r"\b(net\s+user\b[^;|&]*(/add|/delete|/active|password)"
          r"|new-localuser|remove-localuser|set-localuser\b"
          r"[^;|&]*\b-password\b)")),
    ]
)


def scan(text: str) -> str | None:
    """Scan text against the never-list: returns the refusal reason naming
    the matched class, or None when clean. The scan covers the complete
    text — chained operators, pipes, redirections included — so a
    never-list element smuggled anywhere refuses the whole operation,
    regardless of lane, recommendation, or confirmation (FR-003)."""
    for name, pattern in NEVER_PATTERNS:
        m = pattern.search(text or "")
        if m:
            return (f"Blocked: the operation targets system integrity "
                    f"(matched: {name}; near {m.group(0)!r}) — disk-level "
                    f"destruction and boot/recovery/encryption-state "
                    f"operations are never executable from chat, even with "
                    f"a tier-2 recommendation and user confirmation.")
    return None