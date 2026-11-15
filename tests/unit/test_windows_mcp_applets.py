"""Spec 041 — the applet-tier unit battery (the quickstart test plan's
part A). All four tiers pinned: the open launcher's bounds, the read
allowlist's refusals, the never-list extension's both-phase binding with
the clarified firewall-rule boundary, and the GUI gate's stop conditions."""

import asyncio
import json

from agentic_rag_mcp.hermes_audit import HermesAudit
from agentic_rag_mcp.task_gateway.neverlist import scan
from agentic_rag_mcp.windows_mcp.read_gate import match_query
from agentic_rag_mcp.windows_mcp.targets import resolve_target


class TestOpenTier:
    """T006: bounded launcher — membership, ask-back, one-target,
    identifier-only execution, audit class windows-mcp-open."""

    def test_known_targets_resolve(self):
        res = resolve_target("device manager")
        assert res["status"] == "ok"
        assert res["target"]["identifier"] == "devmgmt.msc"
        res = resolve_target("Display Settings")
        assert res["status"] == "ok"
        assert res["target"]["identifier"] == "desk.cpl"

    def test_unknown_target_asks_back_with_the_list(self):
        res = resolve_target("open the flux capacitor panel")
        assert res["status"] == "ask-back"
        assert "device manager" in res["reason"]

    def test_empty_target_asks_back(self):
        assert resolve_target("")["status"] == "ask-back"

    def test_launcher_executes_identifier_only(self, monkeypatch):
        from agentic_rag_mcp.windows_mcp import open as _open_mod
        captured = {}

        async def fake_call(tool, args, cid, audit=None):
            captured["tool"] = tool
            captured["args"] = args
            return {"status": "ok", "tool": tool, "text": "launched",
                    "truncated": False}

        monkeypatch.setattr(_open_mod, "call_tool", fake_call)
        out = asyncio.run(_open_mod.open_settings(
            "device manager", "conv-open-test", audit=None))
        assert out["status"] == "ok"
        assert captured["tool"] == "PowerShell"
        assert captured["args"]["command"] == ("Start-Process cmd.exe -ArgumentList '/c','control','devmgmt.msc'")
        assert set(captured["args"]) <= {"command", "timeout"}  # nothing beyond

    def test_launcher_settings_page_identifier(self, monkeypatch):
        from agentic_rag_mcp.windows_mcp import open as _open_mod
        captured = {}

        async def fake_call(tool, args, cid, audit=None):
            captured["args"] = args
            return {"status": "ok", "tool": tool, "text": "launched",
                    "truncated": False}

        monkeypatch.setattr(_open_mod, "call_tool", fake_call)
        asyncio.run(_open_mod.open_settings(
            "apps and features", "conv-open-test"))
        assert captured["args"]["command"] == ("Start-Process cmd.exe -ArgumentList '/c','start','ms-settings:appsfeatures'")

    def test_unknown_target_blocked_and_audited(self, monkeypatch, tmp_path):
        from agentic_rag_mcp.windows_mcp import open as _open_mod

        async def fake_call(tool, args, cid, audit=None):
            raise AssertionError("must not reach the service")

        monkeypatch.setattr(_open_mod, "call_tool", fake_call)
        audit = HermesAudit(tmp_path / "a.jsonl")
        out = asyncio.run(_open_mod.open_settings(
            "the flux capacitor panel", "conv-x", audit=audit))
        assert out["status"] == "blocked"
        row = json.loads((tmp_path / "a.jsonl").read_text().splitlines()[0])
        assert row["decision"] == "blocked"
        assert row["operation"] == "windows-mcp-open"
        assert row["conversation_id"] == "conv-x"


class TestReadTier:
    """T009: the strict allowlist — one fixed shape per query; unmapped
    and write-shaped refused with the list; the wrapper audits."""

    def test_known_queries_map(self):
        for text, name in (
                ("which network adapters do I have", "network-adapters"),
                ("what's my current power plan", "power-plan"),
                ("show firewall rules", "firewall-rules"),
                ("disk space", "volumes")):
            res = match_query(text)
            assert res["status"] == "ok" and res["name"] == name

    def test_fixed_command_shape(self):
        res = match_query("what network adapters do I have")
        assert res["command"].startswith("Get-NetAdapter")

    def test_unmapped_refused_with_the_list(self):
        res = match_query("what's my screen refresh rate")
        assert res["status"] == "blocked"
        assert "network-adapters" in res["reason"]

    def test_write_shaped_routed_to_tier3(self):
        res = match_query("change my dns server")
        assert res["status"] == "blocked"
        assert "confirmed two-phase" in res["reason"]

    def test_wrapper_runs_the_fixed_command(self, monkeypatch, tmp_path):
        from agentic_rag_mcp.windows_mcp import read_gate
        captured = {}

        async def fake_call(tool, args, cid, audit=None):
            captured.update(tool=tool, args=args)
            return {"status": "ok", "tool": tool,
                    "text": "Name Status", "truncated": False}

        monkeypatch.setattr(read_gate, "call_tool", fake_call)
        audit = HermesAudit(tmp_path / "a.jsonl")
        out = asyncio.run(read_gate.run_read(
            "what network adapters do I have", "conv-read", audit=audit))
        assert out["status"] == "ok"
        assert captured["args"]["command"].startswith("Get-NetAdapter")
        row = json.loads((tmp_path / "a.jsonl").read_text().splitlines()[0])
        assert row["operation"] == "windows-mcp-read"
        assert row["decision"] == "executed"

    def test_wrapper_blocked_not_audited_as_executed(self, monkeypatch,
                                                     tmp_path):
        from agentic_rag_mcp.windows_mcp import read_gate

        async def fail_call(tool, args, cid, audit=None):
            raise AssertionError("no service call for unmapped reads")

        monkeypatch.setattr(read_gate, "call_tool", fail_call)
        audit = HermesAudit(tmp_path / "a.jsonl")
        out = asyncio.run(read_gate.run_read(
            "what's my screen refresh rate", "conv-read", audit=audit))
        assert out["status"] == "blocked"
        row = json.loads((tmp_path / "a.jsonl").read_text().splitlines()[0])
        assert row["decision"] == "blocked"


class TestNeverListExtension:
    """T012: the remote-access-cutting class binds at draft AND confirm;
    the clarified boundary: firewall RULE changes are confirmed-only."""

    def test_adapter_disable_never(self):
        assert scan("Disable-NetAdapter -Name 'Ethernet'") is not None

    def test_adapter_enable_never(self):
        assert scan("Enable-NetAdapter -Name 'Wi-Fi'") is not None

    def test_ip_gateway_changes_never(self):
        assert scan("New-NetIPAddress -IPAddress 10.0.0.5") is not None
        assert scan("Set-DnsClientServerAddress -ServerAddresses 1.1.1.1") is not None

    def test_firewall_profile_disable_never(self):
        assert scan("Set-NetFirewallProfile -Profile Domain -Enabled False") is not None

    def test_firewall_rule_changes_confirmed_only(self):
        assert scan("New-NetFirewallRule -DisplayName x -Direction Inbound") is None
        assert scan("Set-NetFirewallRule -DisplayName x -Action Allow") is None

    def test_remote_access_config_never(self):
        assert scan("Set-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\"
                    "Control\\Terminal Server' -Name fDenyTSConnections") is not None

    def test_account_changes_never(self):
        assert scan("net user admin /add") is not None
        assert scan("New-LocalUser -Name svc -Password $p") is not None

    def test_bare_net_user_listing_passes(self):
        assert scan("net user") is None


class TestGuiTier:
    """T015: the UI gate — sequence drafts in plain words, credential
    fields refused BEFORE any call (value absent from audit), UAC stop,
    cascade re-confirm, never-list-via-click refused verbatim."""

    def test_credential_target_refused_pre_call(self, monkeypatch):
        from agentic_rag_mcp.windows_mcp import gui
        audit_log = []

        class FakeAudit:
            def write_attempt(self, **kw):
                audit_log.append(kw)

        async def fail_call(tool, args, cid, audit=None):
            raise AssertionError("credential steps must never reach the service")

        monkeypatch.setattr(gui, "call_tool", fail_call)
        out = gui.draft_sequence(
            [{"action": "type", "target": "Password field",
              "value": "hunter2-secret"}],
            "click OK on the VPN password dialog",
            "conv-gui", audit=FakeAudit())
        assert out["status"] == "blocked"
        assert "credential" in out["reason"].lower()
        # the refusal row exists and contains NO typed value
        row = next(r for r in audit_log if r.get("decision") == "blocked")
        assert "hunter2-secret" not in json.dumps(row)

    def test_neverlist_click_refused(self):
        from agentic_rag_mcp.windows_mcp import gui
        out = gui.draft_sequence(
            [{"action": "click", "target": "Format volume button"}],
            "click the Format D: button in the dialog", "conv-gui")
        assert out["status"] == "blocked"
        assert "never" in out["reason"].lower() or "system integrity" in out["reason"]

    def test_valid_sequence_drafts_with_plain_text(self):
        from agentic_rag_mcp.windows_mcp import gui
        out = gui.draft_sequence(
            [{"action": "click", "target": "Uninstall",
              "expect": "the Zoom uninstall dialog"},
             {"action": "click", "target": "Uninstall button",
              "expect": "the uninstall completes"}],
            "uninstall Zoom from Programs and Features", "conv-gui")
        assert out["status"] == "pending-confirmation"
        assert "Uninstall" in out["sequence_text"]
        assert "Zoom" in out["sequence_text"]

    def test_confirm_executes_steps_and_stops_on_missing(self, monkeypatch):
        from agentic_rag_mcp.windows_mcp import gui
        calls = []

        async def fake_call(tool, args, cid, audit=None):
            calls.append(tool)
            if tool == "Click" and args.get("label") == "Uninstall button":
                # simulate a click that hits an unreachable elevated dialog
                return {"status": "error",
                        "reason": "error:windows-mcp-tool-error — element "
                                  "not interactable (secure desktop)"}
            return {"status": "ok", "tool": tool, "text": "done",
                    "truncated": False}

        monkeypatch.setattr(gui, "call_tool", fake_call)
        gui.GuiState().set_pending("conv-gui2", [
            {"action": "click", "target": "Uninstall"},
            {"action": "click", "target": "Uninstall button"}])
        out = asyncio.run(gui.confirm_sequence("conv-gui2", "conv-gui2"))
        assert out["status"] == "blocked"          # honest stop, no claim
        assert "elevation" in out["reason"].lower() or "secure desktop" in out["reason"]
        assert out["completed_steps"] == 1          # the first click ran

    def test_cascade_stops_and_reconfirms(self, monkeypatch):
        from agentic_rag_mcp.windows_mcp import gui

        async def fake_call(tool, args, cid, audit=None):
            if tool == "Snapshot":
                return {"status": "ok", "tool": tool,
                        "text": "Window: 'Unexpected: SystemPropertiesProtection'",
                        "truncated": False}
            return {"status": "ok", "tool": tool, "text": "done",
                    "truncated": False}

        monkeypatch.setattr(gui, "call_tool", fake_call)
        gui.GuiState().set_pending("conv-gui3", [
            {"action": "click", "target": "OK", "expect": "the power plan applies"},
        ])
        out = asyncio.run(gui.confirm_sequence("conv-gui3", "conv-gui3"))
        assert out["status"] == "blocked"
        assert "Unexpected" in out["reason"] or "re-confirm" in out["reason"].lower()
