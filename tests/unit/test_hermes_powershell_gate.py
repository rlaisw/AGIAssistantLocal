"""Unit: the PowerShell-lane never-list gate (spec 034, FR-002 + test-plan §1a).

Failing-first: written before hermes_powershell_gate exists. The never-list
is the floor no prompt or confirmation can get under — enforced in gate code,
scanned over the COMPLETE exact draft text. Clean real-PowerShell drafts
(pipes, filters, Remove-Item, service/process control) must pass: only
system-integrity destruction refuses.
"""

from __future__ import annotations

from agentic_rag_mcp.hermes_powershell_gate import gate_powershell


def blocked(v):
    return v.decision == "blocked" and v.reason is not None


def ok(v):
    return v.decision == "ok" and v.reason is None


# --------------------------------------------------------- direct never-list

def test_direct_never_list_refused_with_rule_named():
    cases = [
        "format D:",
        "Format-Volume -DriveLetter C",
        "diskpart",
        "bcdedit /set {bootmgr} timeout 10",
        "bootrec /fixmbr",
        "bootcfg /default",
        "vssadmin delete shadows /all",
        "reagentc /disable",
        "manage-bde -off C:",
        "cipher /w:C:\\",
        "Clear-Disk -Number 0",
        "Initialize-Disk 1",
        "sdelete C:\\pagefile.sys",
    ]
    for draft in cases:
        v = gate_powershell(draft)
        assert blocked(v), (draft, v)
        assert "never executable from chat" in v.reason, draft
        assert "even with confirmation" in v.reason, draft


# ------------------------------------------------------------------ smuggling

def test_smuggled_never_list_refused_by_whole_text_scan():
    cases = [
        "Get-Service; format D:",
        "Get-ChildItem > x.txt & diskpart",
        "Get-Process | Where-Object {$_.Name} ; vssadmin delete shadows /all",
        "& { format C: }",
        "Get-Service | format d:",
        "Restart-Service Spooler; bootrec /fixmbr",
    ]
    for draft in cases:
        v = gate_powershell(draft)
        assert blocked(v), (draft, v)
        assert "never executable from chat" in v.reason, draft


# ------------------------------------------------------- clean drafts pass

def test_clean_real_powershell_drafts_pass():
    cases = [
        "Get-Service | Where-Object {$_.StartType -eq 'Automatic'}",
        "Remove-Item C:\\temp\\junk.txt",
        "Remove-Item C:\\temp\\junk.txt -Recurse",
        "Get-ChildItem C:\\Users -Recurse -File | Format-Table Name, Length",
        "Get-ChildItem C:\\ | Format-List",
        "Restart-Service Spooler",
        "Stop-Process -Name notepad",
        "Get-Volume | Sort-Object SizeRemaining -Descending | Format-Table",
    ]
    for draft in cases:
        assert ok(gate_powershell(draft)), draft


def test_display_format_cmdlets_are_not_volume_format():
    # false-positive guards: Format-Table/List/Wide/Custom display cmdlets
    for draft in ["Get-Process | Format-Table", "Get-Service | Format-Wide",
                  "Get-ChildItem | Format-List", "Get-Volume | Format-Custom"]:
        assert ok(gate_powershell(draft)), draft


def test_empty_draft_is_blocked():
    v = gate_powershell("")
    assert blocked(v)
    assert "no command drafted" in v.reason.lower()
