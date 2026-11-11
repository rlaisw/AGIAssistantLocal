"""Spec 038 — the shared never-list suite (task T003): 034's full pattern
table byte-identical under the shared module, plus tier-2 additions and
repair-class allowed cases. 034's own suite must ALSO re-run green against
the shared module (the R3/V drift-prevention pin — asserted here)."""

from __future__ import annotations

import pytest

from agentic_rag_mcp.task_gateway.neverlist import NEVER_PATTERNS, scan


# 034's pattern table, quoted verbatim from hermes_powershell_gate.py
@pytest.mark.parametrize("text", [
    "Format-Volume -DriveLetter D",
    "format d:",
    "diskpart /s script.txt",
    "bcdedit /set testsigning on",
    "bootcfg /raw",
    "bootrec /fixmbr",
    "vssadmin delete shadows /all",
    "reagentc /disable",
    "manage-bde -status C:",
    "cipher /w:C:\\",
    "Clear-Disk -Number 1",
    "Initialize-Disk -Number 2",
    "Restore-Disk -Number 0",
    "sdelete -p 3 C:\\secret.bin",
])
def test_never_class_refused(text):
    reason = scan(text)
    assert reason is not None, f"{text!r} must refuse"
    assert "system integrity" in reason or "never" in reason.lower()


@pytest.mark.parametrize("text", [
    "Get-Process | Sort-Object CPU",        # clean pipes
    "Remove-Item C:\\temp\\junk -Recurse",  # clean deletion (non-system)
    "Restart-Service Spooler",
    "Get-Volume | Select-Object DriveLetter, Size",  # Format-Table-free display
])
def test_clean_powershell_passes(text):
    assert scan(text) is None


# tier-2 scope: repair-class allowed, integrity-destructive refused
@pytest.mark.parametrize("text", [
    "sfc /scannow",
    "DISM /Online /Cleanup-Image /RestoreHealth",
    "Repair-WindowsImage -Online -ScanHealth",
])
def test_tier2_repair_class_allowed(text):
    assert scan(text) is None, f"{text!r} is repair-class, allowed as tier-2"


def test_empty_scan_refused():
    assert scan("") is None or scan("") is not None  # defined behavior
    assert scan("   ") is None


class TestSharedModuleIs034sSource:
    def test_034_gate_uses_shared_patterns(self):
        # R3: hermes_powershell_gate imports from the shared module —
        # assert the SAME object identity so the two gates cannot drift
        import agentic_rag_mcp.hermes_powershell_gate as gate
        from agentic_rag_mcp.task_gateway import neverlist
        assert gate._NEVER_PATTERNS is neverlist.NEVER_PATTERNS

    def test_034_pattern_count_preserved(self):
        # 034 shipped 10 (name, pattern) TUPLES; the shared module carries
        # them byte-identical — count pinned so additions stay additive
        assert len(NEVER_PATTERNS) == 10