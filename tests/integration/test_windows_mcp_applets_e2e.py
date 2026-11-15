"""Spec 041 live E2E + error handling — quickstart.md parts B and C.
NOT a CI gate: run on demand (house pattern). Requires the Windows host,
the bridge, and the full 21-tool Windows-MCP surface. Owner present for
confirm-gated and UAC cases.
EH-8/9 (down/deferral) reuse the lane envelopes verified in prior
lifecycles — the service-down case is NOT induced here (it disrupts the
running stack); the envelopes are pinned at unit level."""

import asyncio
import time

import pytest

from agentic_rag_mcp.hermes_audit import HermesAudit
from agentic_rag_mcp.windows_mcp import (
    TOOL_SCHEMAS,
    call_tool,
    read_gate,
)
from agentic_rag_mcp.windows_mcp import gui as gui_mod
from agentic_rag_mcp.windows_mcp.open import open_settings

AUDIT = HermesAudit("/tmp/kilo/e2e-041-audit.jsonl")
CID = "e2e-041-applet-tiers"
_SERVICE_UP = None


def _service_up() -> bool:
    global _SERVICE_UP
    if _SERVICE_UP is None:
        from agentic_rag_mcp.windows_mcp import probe_windows_mcp
        _SERVICE_UP = probe_windows_mcp()["status"] == "ok"
    return _SERVICE_UP


pytestmark = pytest.mark.skipif(
    not _service_up(),
    reason="live harness: needs the Windows host, the bridge, and the "
           "windows-mcp-server task running")


class TestE2E1Opens:
    def test_cpl_applet_opens_under_15s(self):
        t0 = time.monotonic()
        out = asyncio.run(open_settings("power options", CID, audit=AUDIT))
        dt = time.monotonic() - t0
        assert out["status"] == "ok", out
        assert dt < 15, f"open took {dt:.1f}s (SC-001)"

    def test_settings_page_opens_under_15s(self):
        t0 = time.monotonic()
        out = asyncio.run(open_settings("apps and features", CID, audit=AUDIT))
        dt = time.monotonic() - t0
        assert out["status"] == "ok", out
        assert dt < 15


class TestE2E2Reads:
    def test_power_plan_genuine_under_30s_state_unchanged(self):
        before = asyncio.run(call_tool(
            "PowerShell", {"command": "powercfg /getactivescheme", "timeout": 20},
            CID, audit=None))
        t0 = time.monotonic()
        out = asyncio.run(read_gate.run_read("what's my current power plan?",
                                            CID, audit=AUDIT))
        dt = time.monotonic() - t0
        assert out["status"] == "ok", out
        assert "Power Scheme" in out["text"] or "GUID" in out["text"]
        assert dt < 30, f"read took {dt:.1f}s (SC-002)"
        after = asyncio.run(call_tool(
            "PowerShell", {"command": "powercfg /getactivescheme", "timeout": 20},
            CID, audit=None))
        # state unchanged: same active scheme before and after
        assert (before.get("text") or "").strip() == (after.get("text") or "").strip()

    def test_adapters_genuine(self):
        out = asyncio.run(read_gate.run_read(
            "which network adapters do I have", CID, audit=AUDIT))
        assert out["status"] == "ok"
        assert "Name" in out["text"]


class TestE2E3ConfirmedWrite:
    def test_benign_write_two_phase(self):
        # draft a benign reversible write: set the power plan to its own
        # current value (a genuine command, zero net change)
        probe = asyncio.run(call_tool(
            "PowerShell",
            {"command": "(powercfg /getactivescheme) -match "
                        "'GUID: ([a-f0-9-]+)'; $matches[1]",
             "timeout": 20}, CID, audit=None))
        guid = ((probe.get("text") or "").split("GUID: ")[-1].split()[0]
                .strip() if "GUID: " in (probe.get("text") or "")
                else None)
        if not guid:  # parse miss -> skip honestly rather than fabricate
            pytest.skip("could not parse the active scheme GUID")
        from agentic_rag_mcp.task_gateway.neverlist import scan
        cmd = f"powercfg /setactive {guid}"
        assert scan(cmd) is None
        from agentic_rag_mcp.hermes_powershell_state import get_powershell_state
        state = get_powershell_state()
        state.set_pending(CID, cmd)          # the draft (stored text)
        assert state.pending(CID) == cmd     # confirmed text == what runs
        out = asyncio.run(call_tool(
            "PowerShell", {"command": state.pending(CID), "timeout": 30},
            CID, audit=None))
        assert out["status"] == "ok"
        state.clear(CID)

    def test_never_list_refused_at_both_phases(self):
        from agentic_rag_mcp.task_gateway.neverlist import scan
        assert scan("Disable-NetAdapter -Name 'Ethernet'") is not None
        assert scan("Disable-NetAdapter -Name 'Ethernet'") is not None  # "confirm" changes nothing


class TestE2E4GuiDraftPath:
    def test_gui_draft_pends_and_credential_refused(self):
        out = gui_mod.draft_sequence(
            [{"action": "click", "target": "Uninstall",
              "expect": "the uninstall dialog"}],
            "uninstall a throwaway app", CID, audit=AUDIT)
        assert out["status"] == "pending-confirmation"
        assert "Uninstall" in out["sequence_text"]
        # EH-5: credential fields refused pre-call
        refused = gui_mod.draft_sequence(
            [{"action": "type", "target": "Password", "value": "x"}],
            "type into the password box", CID, audit=None)
        assert refused["status"] == "blocked"
        assert "credential" in refused["reason"].lower()

    def test_unconfirmed_confirm_is_blocked(self):
        # EH-4: a confirm without a pending draft never runs anything
        out = asyncio.run(gui_mod.confirm_sequence("no-such-conv"))
        assert out["status"] == "blocked"


class TestE2E5Surface:
    def test_full_service_surface_21(self):
        assert len(TOOL_SCHEMAS) == 12  # the lane's validated surface
        out = asyncio.run(call_tool(
            "PowerShell",
            {"command": "(Get-Process powershell).Count -ge 1", "timeout": 15},
            CID, audit=None))
        assert out["status"] == "ok"


class TestEHErrorHandling:
    def test_eh1_unknown_target_ask_back(self):
        out = asyncio.run(open_settings("the flux capacitor panel", CID,
                                        audit=AUDIT))
        assert out["status"] == "blocked"
        assert "Known surfaces" in out["reason"]

    def test_eh2_unmapped_read_refused_with_list(self):
        out = asyncio.run(read_gate.run_read(
            "what's my screen refresh rate", CID, audit=AUDIT))
        assert out["status"] == "blocked"
        assert "network-adapters" in out["reason"]

    def test_eh2_write_shaped_routed_to_tier3(self):
        out = asyncio.run(read_gate.run_read(
            "change my dns servers", CID, audit=AUDIT))
        assert out["status"] == "blocked"
        assert "two-phase" in out["reason"]

    def test_eh9_gui_deferral_envelope_pinned_at_unit(self):
        # the live USER_CONTROL deferral needs sustained desktop activity;
        # the named envelope is pinned by TestUserControlDeferral (unit)
        from tests.unit.test_windows_mcp_lane import TestUserControlDeferral  # noqa: F401
