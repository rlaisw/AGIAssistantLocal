"""Spec 040 live E2E — quickstart.md E2E-1..E2E-4 against the real
Windows-MCP service through the repaired lane. NOT a CI gate: run on
demand (house pattern for integration harnesses). Requires the WSL
bridge active and the windows-mcp-server Scheduled Task running.

E2E-2 stops the task briefly and ALWAYS restores it (try/finally) —
never leave the lane down."""

import asyncio
import os
import subprocess
import time

import pytest

from agentic_rag_mcp.hermes_audit import HermesAudit
from agentic_rag_mcp.windows_mcp import call_tool, probe_windows_mcp, process_list

_SCHTASKS = "/mnt/c/Windows/System32/schtasks.exe"
_ON_WINDOWS = os.path.exists(_SCHTASKS)

# the real audit trail is container-owned (append denied from WSL) — the
# funnel integration is unit-pinned against tmp paths; this harness
# audits to its own local file
AUDIT = HermesAudit("/tmp/kilo/e2e-040-audit.jsonl")
CID = "e2e-040-windowsmcp-lane"


def _schtasks(*args):
    return subprocess.run([_SCHTASKS, *args], capture_output=True, timeout=30)


def _lane_up() -> bool:
    return probe_windows_mcp()["status"] == "ok"


pytestmark = pytest.mark.skipif(
    not _ON_WINDOWS or not _lane_up(),
    reason="live harness: needs the Windows host, the bridge, and "
           "the windows-mcp-server task running")


class TestE2E1Acceptance:
    def test_top5_processes_genuine_output_under_30s(self):
        t0 = time.monotonic()
        out = asyncio.run(process_list(sort_by="memory", limit=5,
                                       conversation_id=CID, audit=AUDIT))
        dt = time.monotonic() - t0
        assert out["status"] == "ok", out
        assert "PID" in out["text"]          # genuine process table
        assert len([l for l in out["text"].splitlines()
                    if l.strip() and l.strip()[0].isdigit()]) >= 1
        assert out["truncated"] is False
        assert dt < 30, f"round-trip {dt:.1f}s exceeds SC-001 budget"
        assert len(out["text"]) <= 4000       # the bound always holds


class TestE2E3ErrorHandling:
    def test_invalid_args_blocked_no_service_call(self):
        out = asyncio.run(call_tool("Registry", {"mode": "read"},
                                    CID, audit=AUDIT))
        assert out["status"] == "blocked"
        assert "path" in out["reason"]

    def test_service_error_relayed_verbatim(self):
        out = asyncio.run(call_tool(
            "Registry", {"mode": "read",
                         "path": "HKLM\\SOFTWARE\\AGIAssistantNoSuchKey"},
            CID, audit=AUDIT))
        assert out["status"] == "error"
        assert "windows-mcp-tool-error" in out["reason"]


class TestE2E4Bounding:
    def test_large_listing_never_exceeds_the_bound(self):
        out = asyncio.run(call_tool(
            "Process", {"mode": "list", "limit": 500},
            CID, audit=AUDIT))
        assert out["status"] == "ok"
        assert len(out["text"]) <= 4000
        if out["truncated"]:
            assert "truncated at" in out["note"]


def _kill_port_8800_owner():
    """schtasks /end leaves the service's child process holding :8800
    (the playwright-lane lesson, 2026-11-14) — the true down-state needs
    the ordered kill of the listener, then /run restores a clean one."""
    netstat = "/mnt/c/Windows/System32/netstat.exe"
    taskkill = "/mnt/c/Windows/System32/taskkill.exe"
    r = subprocess.run([netstat, "-ano"], capture_output=True, timeout=30)
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        if ":8800" in line and "LISTENING" in line:
            pid = line.split()[-1].strip("\r")
            if pid.isdigit():
                subprocess.run([taskkill, "/PID", pid, "/T", "/F"],
                               capture_output=True, timeout=30)


class TestE2E2DownState:
    def test_down_envelope_under_5s_then_restored(self):
        _schtasks("/end", "/tn", "windows-mcp-server")
        _kill_port_8800_owner()
        time.sleep(2)
        try:
            t0 = time.monotonic()
            out = probe_windows_mcp()
            dt = time.monotonic() - t0
            assert out["status"] == "error"
            assert out["windows_mcp"]["reachable"] is False
            assert "windows-mcp-lane-unavailable" in out["reason"]
            assert "windows-mcp-server" in out["reason"]   # real recovery
            assert dt < 5, f"honest failure took {dt:.1f}s (SC-002)"
        finally:
            _schtasks("/run", "/tn", "windows-mcp-server")
        # restored: the lane answers again
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if _lane_up():
                break
            time.sleep(1)
        assert _lane_up()
