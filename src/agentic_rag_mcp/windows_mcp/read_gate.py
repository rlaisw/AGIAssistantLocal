"""Spec 041 — the tier-2 settings read-allowlist (FR-003).

A strict fixed-shape allowlist (the spec-033 pattern): each entry maps
intent keywords to ONE exact query; unmapped or write-shaped requests
are refused with the list shown; one query per request; no confirmation
(queries cannot change state — E2E proves it before/after)."""

from __future__ import annotations

import re
import time

from .client import call_tool

# (name, keywords, exact query) — the ONLY queries tier 2 executes
ENTRIES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("network-adapters",
     ("adapter", "adapters", "network cards", "nic", "link speed",
      "wifi status", "ethernet status"),
     ("Get-NetAdapter | Select-Object Name, InterfaceDescription, Status, "
      "LinkSpeed | Format-Table -AutoSize | Out-String")),
    ("power-plan",
     ("power plan", "power scheme", "power mode", "active plan"),
     "powercfg /getactivescheme"),
    ("firewall-rules",
     ("firewall rules", "firewall rule list", "which ports are open",
      "open ports", "inbound rules", "outbound rules"),
     ("Get-NetFirewallRule -Enabled True | Select-Object -First 25 "
      "DisplayName, Direction, Action | Format-Table -AutoSize "
      "| Out-String")),
    ("volumes",
     ("disk space", "volumes", "free space", "drive space", "partitions"),
     ("Get-Volume | Select-Object DriveLetter, FileSystemLabel, "
      "@{n='SizeGB';e={[math]::Round($_.Size/1GB)}}, "
      "@{n='FreeGB';e={[math]::Round($_.SizeRemaining/1GB)}} | "
      "Format-Table -AutoSize | Out-String")),
    ("system-summary",
     ("system info", "machine info", "computer info", "hostname",
      "os version", "windows version"),
     ("Get-ComputerInfo -Property OsName, OsVersion, OsArchitecture, "
      "CsManufacturer, CsModel, WindowsVersion | Format-List "
      "| Out-String")),
    ("locale-settings",
     ("locale", "time zone", "timezone", "region setting", "language"),
     ("Get-TimeZone; Get-Culture | Select-Object Name, DisplayName | "
      "Format-List | Out-String")),
)

_WRITE_SHAPED = re.compile(
    r"\b(set|change|enable|disable|turn (on|off)|add|remove|delete|"
    r"create|new|update|modify|uninstall|install|rename|reset|clear)\b",
    re.IGNORECASE)

_LIST = ", ".join(name for name, _, _ in ENTRIES)


def match_query(text: str) -> dict:
    """Resolve a settings question to ONE allowlisted query.

    {status: ok, name, command} on a match; otherwise the refusal
    naming the list — write-shaped requests refused with the
    write-shaped reason (they belong to tier 3's confirmed flow)."""
    low = (text or "").strip().lower()
    if not low:
        return {"status": "blocked",
                "reason": ("blocked: name the settings fact you want "
                           f"({_LIST})")}
    if _WRITE_SHAPED.search(low):
        return {"status": "blocked",
                "reason": ("blocked: that reads like a settings CHANGE — "
                           "changes go through the confirmed two-phase "
                           "flow (say what to change and I will draft the "
                           "exact command for your confirmation); tier-2 "
                           "reads only: " + _LIST)}
    for name, keywords, command in ENTRIES:
        if any(k in low for k in keywords):
            return {"status": "ok", "name": name, "command": command}
    return {"status": "blocked",
            "reason": ("blocked: unmapped settings question — tier-2 "
                       f"reads only: {_LIST} ")}


async def run_read(question: str, conversation_id: str,
                   audit=None) -> dict:
    """Answer one settings question with the fixed query. Audits every
    attempt as `windows-mcp-read` (executed/blocked/error); the wrapper
    is the only tier-2 execution path — unmapped questions never reach
    the service."""
    t0 = time.monotonic()
    res = match_query(question)
    if res["status"] != "ok":
        if audit:
            audit.write_attempt(
                decision="blocked", operation="windows-mcp-read",
                normalized_path=None, allowed_root="",
                reason=res["reason"], conversation_id=conversation_id,
                duration_s=time.monotonic() - t0)
        return {"status": "blocked", "reason": res["reason"]}
    out = await call_tool("PowerShell",
                          {"command": res["command"], "timeout": 30},
                          conversation_id, audit=None)
    ok = out.get("status") == "ok"
    if audit:
        audit.write_attempt(
            decision="executed" if ok else "error",
            operation="windows-mcp-read", normalized_path=None,
            allowed_root="",
            outcome=out.get("text", "")[:200] if ok else None,
            reason=None if ok else out.get("reason"),
            conversation_id=conversation_id,
            duration_s=time.monotonic() - t0)
    if ok:
        return {"status": "ok", "query": res["name"],
                "text": out.get("text", "")}
    return out
