"""Spec 047 T020/T039: owner-present printer and Word live journeys.

Run only with the owner at the interactive Windows desktop after deployment::

    RUN_MCP_ACTION_E2E=1 .venv/bin/python -m pytest \
        tests/integration/test_mcp_action_e2e.py -q -s

Microsoft Print to PDF and one other installed printer are required. The sole
non-PDF printer discovered through read-only CIM is used automatically; when
there are several, ``MCP_ACTION_TEST_PRINTER`` must name the owner-approved one
exactly. Word cases use ``MCP_ACTION_DUPLEX_PRINTER`` (default ``HP LaserJet
M610 TCPIP``), which must be an installed, owner-approved duplex test printer.
The harness never installs a printer, prints a page, writes the registry,
auto-elevates, saves/closes Word, or rolls back through ad-hoc PowerShell.
Original default/duplex values are restored through ``ReviewedActions`` in
``finally``. The disposable Word marker remains open and unsaved for the owner.

Dify helpers are reused from T012. Direct service cases use real reviewed
actions/OfficeProxy/display/screenshot dependencies and an isolated real audit.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Self
from urllib.parse import urlsplit

import httpx
import pytest
import test_mcp_action_dify_contract as dify_probe

from agentic_rag_mcp.hermes_audit import HermesAudit
from agentic_rag_mcp.windows_mcp.client import call_tool

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MCP_ACTION_E2E") != "1",
    reason="owner-present live tests: set RUN_MCP_ACTION_E2E=1",
)

# Reuse the deployed-Dify credential/console fixtures and its sanitized event
# parser rather than growing a second Dify client in this battery.
dcfg = dify_probe.dcfg
console = dify_probe.console

ACTION_ID = "windows_default_printer"
WORD_ACTION_ID = "word_printer_duplex"
DUPLEX_PRINTER = os.environ.get(
    "MCP_ACTION_DUPLEX_PRINTER", "HP LaserJet M610 TCPIP"
).strip()
DUPLEX_MODES = {
    "long-edge": "TwoSidedLongEdge",
    "short-edge": "TwoSidedShortEdge",
}
MODE_ORIENTATIONS = {mode: orientation for orientation, mode in DUPLEX_MODES.items()}
PDF_PRINTER = "Microsoft Print to PDF"
OFFER = "Do you want me to do it automatically for you?"
READ_MARKER = "MCP_ACTION_E2E_JSON:"
DUPLEX_READ_MARKER = "MCP_DUPLEX_E2E_JSON:"
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])")

# Independent evidence: this fixed script only enumerates CIM printers and reads
# the managed-default value. It has no name interpolation and no mutation verb.
READ_STATE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$printers = @(Get-CimInstance -ClassName Win32_Printer | ForEach-Object {
    @{ name = [string]$_.Name; is_default = [bool]$_.Default }
})
$managed = @{ status = 'absent'; value = $null }
try {
    $key = Get-Item -LiteralPath `
        'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Windows' -ErrorAction Stop
    $value = $key.GetValue('LegacyDefaultPrinterMode', $null)
    if ($null -ne $value) {
        $managed.status = 'ok'
        $managed.value = [int]$value
    }
} catch {
    $managed.status = 'error'
    $managed.value = $null
}
$json = @{ printers = $printers; managed = $managed } |
    ConvertTo-Json -Depth 4 -Compress
Write-Output ('MCP_ACTION_E2E_JSON:' +
    [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json)))
"""


# Independent Word evidence. The printer name crosses only as UTF-8 Base64;
# every operation is a read, including the print-job snapshot.
READ_DUPLEX_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$requestedName = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String('__PRINTER_NAME_BASE64__'))
$payload = @{
    printers = @()
    matches = @()
    is_admin = $false
    print_management = $false
    configuration = @{ status = 'error'; duplex = $null }
    jobs_status = 'error'
    jobs = @()
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
$payload.is_admin = $principal.IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
$payload.print_management = ($null -ne (
    Get-Module -ListAvailable -Name PrintManagement))
$all = @(Get-CimInstance -ClassName Win32_Printer)
$payload.printers = @($all | ForEach-Object {
    @{
        name = [string]$_.Name
        duplex_capable = [bool](@($_.Capabilities) -contains 3)
    }
})
$payload.matches = @($all | Where-Object {
    [string]$_.Name -eq $requestedName
} | ForEach-Object {
    @{
        name = [string]$_.Name
        duplex_capable = [bool](@($_.Capabilities) -contains 3)
    }
})
try {
    $configuration = Get-PrintConfiguration -PrinterName $requestedName -ErrorAction Stop
    $payload.configuration.status = 'ok'
    $payload.configuration.duplex = [string]$configuration.DuplexingMode
} catch {
    $payload.configuration.status = 'error'
    $payload.configuration.duplex = $null
}
try {
    $jobs = @(Get-PrintJob -PrinterName $requestedName -ErrorAction Stop)
    $payload.jobs = @($jobs | ForEach-Object { [string]$_.ID })
    $payload.jobs_status = 'ok'
} catch {
    $payload.jobs_status = 'error'
    $payload.jobs = @()
}
$json = $payload | ConvertTo-Json -Depth 6 -Compress
Write-Output ('MCP_DUPLEX_E2E_JSON:' +
    [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json)))
"""


# Test-only, bounded OfficeMCP RunPython template. It is idempotent, attaches
# before creating Word, and returns metadata only (never document names/text).
# There is deliberately no document save/close, application quit, or print call.
WORD_MARKER_SCRIPT = r"""
import json
import subprocess
import ctypes
import pythoncom
import win32com.client

d = json.loads(data)
initialized = False
try:
    pythoncom.CoInitialize()
    initialized = True
    try:
        word = win32com.client.GetActiveObject('Word.Application')
    except Exception:
        processes = subprocess.check_output(
            ['tasklist', '/FO', 'CSV', '/NH'], text=True, timeout=5)
        if 'WINWORD.EXE' in processes.upper():
            raise RuntimeError('Word is running but COM attach failed')
        word = win32com.client.DispatchEx('Word.Application')
    word.Visible = True
    marker = str(d['marker'])
    matches = []
    for index in range(1, word.Documents.Count + 1):
        candidate = word.Documents.Item(index)
        if marker in str(candidate.Content.Text):
            matches.append(candidate)
    if not matches and bool(d['create']):
        document = word.Documents.Add()
        document.Content.Text = marker
        matches = [document]
    saved_flags = [
        bool(word.Documents.Item(index).Saved)
        for index in range(1, word.Documents.Count + 1)
    ]
    window = word.ActiveWindow
    hwnd = int(window.Hwnd)
    user32 = ctypes.windll.user32
    result = {
        'status': 'ok',
        'document_count': int(word.Documents.Count),
        'saved_flags': saved_flags,
        'marker_count': len(matches),
        'marker_saved': bool(matches[0].Saved) if len(matches) == 1 else None,
        'marker_text_ok': (
            len(matches) == 1 and marker in str(matches[0].Content.Text)
        ),
        'preview': bool(word.PrintPreview),
        'view_type': int(window.View.Type),
        'window_visible': bool(word.Visible) and bool(user32.IsWindowVisible(hwnd)),
        'foreground': user32.GetForegroundWindow() == hwnd,
    }
    output = json.dumps(result)
except Exception as exc:
    output = json.dumps({'status': 'error', 'error_type': type(exc).__name__})
finally:
    if initialized:
        pythoncom.CoUninitialize()
"""


def _default_printer(state: dict) -> str | None:
    defaults = [p["name"] for p in state["printers"] if p.get("is_default")]
    assert len(defaults) <= 1, "CIM reported more than one per-user default printer"
    return defaults[0] if defaults else None


def _same_printer(left: str | None, right: str | None) -> bool:
    return left is not None and right is not None and left.casefold() == right.casefold()


def _visible_text(text: str) -> str:
    return re.sub(r"<think>[\s\S]*?</think>", "", text)


def _managed_semantics(state: dict) -> str:
    managed = state.get("managed", {})
    status = managed.get("status")
    value = managed.get("value")
    if status == "absent" or (status == "ok" and value == 0):
        return "managed"
    if status == "ok" and value == 1:
        return "disabled"
    return "unknown"


async def _read_state(conversation_id: str) -> dict:
    out = None
    for attempt in range(3):
        out = await call_tool(
            "PowerShell",
            {"command": READ_STATE_SCRIPT, "timeout": 30},
            conversation_id,
            audit=None,
        )
        if out.get("status") == "ok":
            break
        if attempt < 2:
            await asyncio.sleep(2 * (attempt + 1))
    assert out is not None and out.get("status") == "ok", (
        "Independent read-only CIM query failed after three bounded attempts"
    )
    assert out.get("truncated") is False, "Printer discovery exceeded the safe output bound"
    match = re.search(re.escape(READ_MARKER) + r"([A-Za-z0-9+/=]+)", out.get("text", ""))
    assert match, "Independent CIM query returned no marked structured state"
    try:
        state = json.loads(base64.b64decode(match.group(1), validate=True).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise AssertionError("Independent CIM state was malformed") from None
    assert isinstance(state.get("printers"), list)
    assert all(isinstance(p.get("name"), str) and p["name"] for p in state["printers"])
    assert state.get("managed", {}).get("status") in {"absent", "ok", "error"}
    return state


async def _read_duplex_state(conversation_id: str, printer: str) -> dict:
    encoded = base64.b64encode(printer.encode("utf-8")).decode("ascii")
    script = READ_DUPLEX_SCRIPT.replace("__PRINTER_NAME_BASE64__", encoded)
    out = None
    for attempt in range(3):
        out = await call_tool(
            "PowerShell",
            {"command": script, "timeout": 30},
            conversation_id,
            audit=None,
        )
        if out.get("status") == "ok":
            break
        if attempt < 2:
            await asyncio.sleep(2 * (attempt + 1))
    assert out is not None and out.get("status") == "ok", (
        "Independent Get-PrintConfiguration read failed after three bounded attempts"
    )
    assert out.get("truncated") is False, "Duplex read exceeded the safe output bound"
    match = re.search(
        re.escape(DUPLEX_READ_MARKER) + r"([A-Za-z0-9+/=]+)", out.get("text", "")
    )
    assert match, "Independent duplex query returned no marked structured state"
    try:
        state = json.loads(base64.b64decode(match.group(1), validate=True).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise AssertionError("Independent duplex state was malformed") from None
    assert isinstance(state.get("printers"), list)
    assert isinstance(state.get("matches"), list)
    assert type(state.get("is_admin")) is bool
    assert type(state.get("print_management")) is bool
    assert state.get("configuration", {}).get("status") in {"ok", "error"}
    assert state.get("jobs_status") in {"ok", "error"}
    assert isinstance(state.get("jobs"), list)
    assert all(isinstance(job, str) for job in state["jobs"])
    return state


def _duplex_mode(state: dict) -> str | None:
    configuration = state["configuration"]
    return configuration["duplex"] if configuration["status"] == "ok" else None


def _assert_no_new_jobs(before: dict, after: dict) -> None:
    assert before["jobs_status"] == after["jobs_status"] == "ok", (
        "Get-PrintJob could not prove that no print job was created"
    )
    assert set(after["jobs"]) == set(before["jobs"]), "Word automation created a print job"


class LivePrinterHarness:
    """Capture targets and restore the original per-user default on every exit."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.read_cid = f"t020-read-{uuid.uuid4().hex}"
        self.audit_path = root / "audit.jsonl"
        self.initial: dict
        self.original: str
        self.other: str
        self.target_b: str
        self.target_c: str
        self.ambiguous: str | None = None

    async def __aenter__(self) -> Self:
        self.initial = await self.read()
        original = _default_printer(self.initial)
        if original is None:
            pytest.skip("live restoration requires an existing per-user default printer")
        self.original = original

        names = [p["name"] for p in self.initial["printers"]]
        if len(names) < 2:
            pytest.skip("fewer than two installed printers; no printer will be invented")
        pdf = [name for name in names if _same_printer(name, PDF_PRINTER)]
        if len(pdf) != 1:
            pytest.skip("exactly one installed Microsoft Print to PDF printer is required")
        self.pdf = pdf[0]

        groups: dict[str, list[str]] = {}
        for name in names:
            groups.setdefault(name.casefold(), []).append(name)
        self.ambiguous = next((members[0] for members in groups.values() if len(members) > 1), None)

        alternates = [name for name in names if not _same_printer(name, self.pdf)]
        approved = os.environ.get("MCP_ACTION_TEST_PRINTER", "").strip()
        if approved:
            matches = [name for name in alternates if _same_printer(name, approved)]
            if len(matches) != 1:
                pytest.skip("MCP_ACTION_TEST_PRINTER is not one exact installed non-PDF printer")
            self.other = matches[0]
        else:
            if len(alternates) != 1:
                pytest.skip(
                    "multiple non-PDF printers discovered; set MCP_ACTION_TEST_PRINTER "
                    "to the owner-approved installed printer"
                )
            self.other = alternates[0]

        # B always differs from the captured original. C differs from B; with
        # only two printers C can be the original, which also exercises changed:false.
        self.target_b = self.other if not _same_printer(self.other, self.original) else self.pdf
        self.target_c = self.pdf if _same_printer(self.target_b, self.other) else self.other

        # Import the future T022/T023 surface only after the opt-in and live
        # prerequisites, so ordinary collection never needs those implementations.
        from agentic_rag_mcp.mcp_action.actions import ReviewedActions
        from agentic_rag_mcp.mcp_action.screenshots import get_screenshot_store
        from agentic_rag_mcp.mcp_action.service import (
            McpActionService,
            ScreenshotCapture,
            WindowsDisplay,
        )

        self.actions = ReviewedActions()
        audit = HermesAudit(self.audit_path)
        self.service = McpActionService(
            actions=self.actions,
            display=WindowsDisplay(audit=audit),
            screenshots=ScreenshotCapture(store=get_screenshot_store(), audit=audit),
            audit=audit,
        )
        return self

    async def read(self) -> dict:
        return await _read_state(self.read_cid)

    async def __aexit__(self, exc_type, exception, traceback) -> bool:
        """Restore through the reviewed action, and report restoration separately."""
        original = self.original
        try:
            current = await self.read()
        except Exception:  # noqa: BLE001 - restoration must still be attempted
            current = None

        restoration = "not-needed"
        restore_result = None
        restore_exception = ""
        if current is None or not _same_printer(_default_printer(current), original):
            restoration = "attempted"
            try:
                restore_result = await self.actions.execute_default_printer(original)
            except Exception as exc:  # noqa: BLE001 - report only the sanitized type
                restore_exception = type(exc).__name__

        final = None
        final_error = ""
        try:
            final = await self.read()
        except Exception as exc:  # noqa: BLE001 - do not leak transport/host details
            final_error = type(exc).__name__

        # Registry/CLIXML reads are known to fail transiently. Retry only the
        # independent read; never mutate the managed-default setting itself.
        if final is not None:
            for _ in range(3):
                if final.get("managed", {}).get("status") != "error":
                    break
                await asyncio.sleep(1)
                try:
                    final = await self.read()
                except Exception as exc:  # noqa: BLE001 - sanitized type only
                    final_error = type(exc).__name__

        failures = []
        final_default = _default_printer(final) if final is not None else None
        if final is None or not _same_printer(final_default, original):
            failures.append(
                f"default restore failed: original={original!r}, observed={final_default!r}, "
                f"action_status={(restore_result or {}).get('status')!r}, "
                f"action_error={restore_exception!r}, read_error={final_error!r}"
            )
        if final is None or _managed_semantics(final) != _managed_semantics(self.initial):
            failures.append("managed-default registry value changed or could not be read back")
        if failures:
            pytest.fail("T020 RESTORATION FAILURE; OWNER ATTENTION REQUIRED: " + "; ".join(failures))

        print(f"T020 restoration: {restoration}; default={final_default!r}; managed=unchanged")
        return False


@pytest.fixture
def live_printers(tmp_path: Path) -> LivePrinterHarness:
    return LivePrinterHarness(tmp_path)


class LiveWordHarness:
    """Own one unsaved marker and restore the approved printer's original duplex."""

    def __init__(self, root: Path, test_name: str = "") -> None:
        self.root = root
        self.test_name = test_name
        self.read_cid = f"t039-read-{uuid.uuid4().hex}"
        self.audit_path = root / "word-audit.jsonl"
        self.marker = f"T039 disposable unsaved marker {uuid.uuid4().hex}"
        self.initial: dict
        self.original_mode: str
        self.original_orientation: str
        self.printer: str

    async def __aenter__(self) -> Self:
        self.initial = await self.read()
        matches = self.initial["matches"]
        if len(matches) != 1:
            pytest.skip("MCP_ACTION_DUPLEX_PRINTER is not one exact installed printer")
        match = matches[0]
        if not match.get("duplex_capable"):
            pytest.skip("the named test printer does not advertise duplex capability")
        if not self.initial["print_management"]:
            pytest.skip("PrintManagement is unavailable on the Windows host")
        if self.initial["jobs_status"] != "ok":
            pytest.skip("Get-PrintJob cannot prove the no-test-page invariant")
        self.printer = match["name"]
        original_mode = _duplex_mode(self.initial)
        if original_mode not in MODE_ORIENTATIONS:
            pytest.skip(
                "the original duplex mode is not restorable through the two reviewed actions"
            )
        self.original_mode = original_mode
        self.original_orientation = MODE_ORIENTATIONS[original_mode]

        # Import the future T041/T042/T043 surface only after live prerequisites.
        from agentic_rag_mcp.mcp_action.actions import ReviewedActions
        from agentic_rag_mcp.mcp_action.screenshots import get_screenshot_store
        from agentic_rag_mcp.mcp_action.service import McpActionService, ScreenshotCapture
        from agentic_rag_mcp.office_lanes.proxy import OfficeProxy

        try:
            self.office = OfficeProxy(timeout_s=20)
        except Exception:  # noqa: BLE001 - unavailable Office is an environment skip
            pytest.skip("OfficeMCP is unavailable; no Word action was attempted")
        self.actions = ReviewedActions()
        self.audit = HermesAudit(self.audit_path)
        self.display = self.office
        self.screenshots = ScreenshotCapture(store=get_screenshot_store(), audit=self.audit)
        self._service_type = McpActionService
        self.service = self.make_service()

        self.initial_word = await self._word_marker(create=True)
        self._check_word(self.initial_word, preview=False)
        return self

    def make_service(
        self, *, actions=None, display=None, screenshots=None, store=None, clock=None
    ):
        return self._service_type(
            store=store,
            actions=self.actions if actions is None else actions,
            display=self.display if display is None else display,
            screenshots=self.screenshots if screenshots is None else screenshots,
            audit=self.audit,
            clock=clock,
        )

    async def read(self) -> dict:
        return await _read_duplex_state(self.read_cid, DUPLEX_PRINTER)

    async def _word_marker(self, *, create: bool) -> dict:
        try:
            out = await asyncio.to_thread(
                self.office.call,
                "RunPython",
                {
                    "code": WORD_MARKER_SCRIPT,
                    "data": json.dumps({"marker": self.marker, "create": create}),
                },
            )
        except Exception:  # noqa: BLE001 - raw host/transport details stay out of output
            if create:
                pytest.skip("Word is unavailable for bounded COM automation")
            raise AssertionError("Word marker verification transport failed") from None
        if out.get("status") != "ok":
            if create:
                pytest.skip("OfficeMCP could not create the disposable Word marker")
            raise AssertionError("Word marker verification was rejected")
        payload = self.office._payload_json(out.get("text", ""))
        assert isinstance(payload, dict), "Word marker helper returned malformed output"
        if payload.get("status") != "ok":
            if create:
                pytest.skip("Word/COM is unavailable for the disposable marker")
            raise AssertionError("Word marker helper could not verify document preservation")
        return payload

    def _check_word(self, word: dict, *, preview: bool) -> None:
        assert word.get("document_count") == self.initial_word["document_count"], (
            "Word document count changed"
        )
        assert word.get("saved_flags") == self.initial_word["saved_flags"], (
            "a Word document Saved flag changed"
        )
        assert word.get("marker_count") == 1
        assert word.get("marker_text_ok") is True
        assert word.get("marker_saved") is False, "the disposable marker was saved"
        if preview:
            assert word.get("preview") is True, "Word Print Preview is not active"
            assert word.get("view_type") == 4, "Word is not in Print Preview view"
            assert word.get("window_visible") is True, "Word Print Preview is not visible"
            assert word.get("foreground") is True, "Word Print Preview is not foreground"

    async def assert_preserved(self, *, preview: bool = False) -> dict:
        state = await self.read()
        _assert_no_new_jobs(self.initial, state)
        word = await self._word_marker(create=False)
        self._check_word(word, preview=preview)
        return state

    def unsupported_printer(self) -> str | None:
        candidates = [
            row["name"]
            for row in self.initial["printers"]
            if not row.get("duplex_capable")
            and not _same_printer(row["name"], self.printer)
        ]
        if not candidates:
            return None
        return next(
            (name for name in candidates if _same_printer(name, PDF_PRINTER)),
            candidates[0],
        )

    async def __aexit__(self, exc_type, exception, traceback) -> bool:
        """Restore via the reviewed action; never save or close the marker."""
        restoration = "not-needed"
        restore_result = None
        restore_exception = ""
        try:
            current = await self.read()
        except Exception:  # noqa: BLE001 - restoration must still be attempted
            current = None
        if current is None or _duplex_mode(current) != self.original_mode:
            restoration = "attempted"
            try:
                restore_result = await self.actions.execute_word_printer_duplex(
                    self.printer, self.original_orientation
                )
            except Exception as exc:  # noqa: BLE001 - sanitized exception type only
                restore_exception = type(exc).__name__

        final = None
        final_error = ""
        try:
            final = await self.read()
        except Exception as exc:  # noqa: BLE001 - sanitized exception type only
            final_error = type(exc).__name__

        failures = []
        if final is None or _duplex_mode(final) != self.original_mode:
            failures.append(
                f"duplex restore failed: original={self.original_mode!r}, "
                f"observed={_duplex_mode(final) if final is not None else None!r}, "
                f"action_status={(restore_result or {}).get('status')!r}, "
                f"action_error={restore_exception!r}, read_error={final_error!r}"
            )
        if final is not None:
            try:
                _assert_no_new_jobs(self.initial, final)
            except AssertionError as exc:
                failures.append(str(exc))
        try:
            word = await self._word_marker(create=False)
            self._check_word(word, preview=False)
        except Exception as exc:  # noqa: BLE001 - report a visible preservation failure
            failures.append(f"Word marker/document preservation failed: {type(exc).__name__}")
        if failures:
            pytest.fail(
                "T039 RESTORATION/PRESERVATION FAILURE; OWNER ATTENTION REQUIRED: "
                + "; ".join(failures)
            )
        observed = _duplex_mode(final) if final is not None else None
        print(
            f"T039 restoration: {restoration}; duplex={observed!r}; "
            "marker=open+unsaved; print_jobs=unchanged"
        )
        return False


@pytest.fixture
def live_word(tmp_path: Path, request: pytest.FixtureRequest) -> LiveWordHarness:
    return LiveWordHarness(tmp_path, test_name=request.node.name)


async def _draft(harness: LivePrinterHarness, cid: str, printer: str, count: int = 10) -> dict:
    return await harness.service.handle(
        phase="draft",
        conversation_id=cid,
        dialogue_count=count,
        action_id=ACTION_ID,
        parameters={"printer": printer},
    )


async def _word_draft(
    service,
    cid: str,
    printer: str,
    orientation: str,
    count: int = 10,
) -> dict:
    return await service.handle(
        phase="draft",
        conversation_id=cid,
        dialogue_count=count,
        action_id=WORD_ACTION_ID,
        parameters={"printer": printer, "orientation": orientation},
    )


async def _resolve(
    harness: LivePrinterHarness,
    phase: str,
    cid: str,
    count: int,
    query: str,
) -> dict:
    return await harness.service.handle(
        phase=phase,
        conversation_id=cid,
        dialogue_count=count,
        query=query,
    )


def _assert_pending(result: dict, printer: str) -> None:
    assert result["status"] == "pending-confirmation"
    assert result["action_id"] == ACTION_ID
    assert result["offer"] == OFFER
    assert result["expires_in_s"] == 900
    assert printer in result["effect"]
    assert isinstance(result.get("caveats"), list)


def _assert_timing(timing: dict) -> None:
    assert isinstance(timing, dict)
    for key in ("queue_wait_s", "execution_s", "total_s"):
        assert type(timing.get(key)) in (int, float) and timing[key] >= 0
    assert timing["total_s"] >= timing["execution_s"]


def _assert_screenshot(screenshot: dict, *, required: bool) -> None:
    assert isinstance(screenshot, dict) and screenshot.get("status")
    if screenshot["status"] != "captured":
        assert "image_url" not in screenshot
        if required:
            pytest.fail(f"expected captured visual evidence, got {screenshot['status']!r}")
        return

    url = screenshot.get("image_url", "")
    parsed = urlsplit(url)
    assert parsed.scheme in {"http", "https"} and parsed.netloc
    assert re.fullmatch(r"/mcp-action/screenshots/[A-Za-z0-9_-]{43}", parsed.path)
    assert 0 < screenshot.get("expires_in_s", 0) <= 900
    try:
        response = httpx.get(url, timeout=30, follow_redirects=False)
    except httpx.HTTPError:
        raise AssertionError("captured screenshot URL did not load") from None
    if response.status_code == 404:
        # Direct host-side fixtures own their temporary store, while the public
        # route belongs to the deployed container. Dify/container results have
        # no host-store copy and therefore must still return HTTP 200.
        from agentic_rag_mcp.mcp_action.screenshots import get_screenshot_store

        local = get_screenshot_store().resolve(parsed.path.rsplit("/", 1)[-1])
        if local is not None:
            assert local.mime_type in {"image/png", "image/jpeg"}
            assert local.data.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"))
            return
    assert response.status_code == 200, "captured screenshot URL did not return image bytes"
    assert "no-store" in response.headers.get("cache-control", "").casefold()
    body = response.content
    assert 8 < len(body) <= 10 * 1024 * 1024
    if response.headers.get("content-type", "").split(";", 1)[0] == "image/png":
        assert body.startswith(b"\x89PNG\r\n\x1a\n")
    else:
        assert response.headers.get("content-type", "").split(";", 1)[0] == "image/jpeg"
        assert body.startswith(b"\xff\xd8")
    print(f"T020 screenshot: captured; loaded_bytes={len(body)}; cache=no-store")


def _assert_execution(
    result: dict,
    *,
    before: str,
    target: str,
    changed: bool,
    evidence_required: bool = True,
) -> None:
    assert result["status"] in {"ok", "partial"}, result.get("reason", result["status"])
    assert result["action_id"] == ACTION_ID
    assert result["changed"] is changed
    assert _same_printer(result["before"]["default_printer"], before)
    assert _same_printer(result["after"]["default_printer"], target)
    assert result["verification"] == "verified"
    assert isinstance(result.get("display"), dict) and result["display"].get("status")
    assert isinstance(result.get("caveats"), list)
    _assert_timing(result["timing"])
    if result["status"] == "ok":
        assert result["display"]["status"] == "displayed"
    _assert_screenshot(result["screenshot"], required=evidence_required)
    print(
        f"T020 outcome: status={result['status']}; changed={result['changed']}; "
        f"verification={result['verification']}; display={result['display']['status']}; "
        f"screenshot={result['screenshot']['status']}; timing={result['timing']}"
    )


def _assert_word_pending(result: dict, printer: str, orientation: str) -> None:
    assert result["status"] == "pending-confirmation"
    assert result["action_id"] == WORD_ACTION_ID
    assert result["offer"] == OFFER
    assert result["expires_in_s"] == 900
    effect = result["effect"]
    lowered = effect.casefold()
    assert printer in effect and orientation in lowered
    assert "printer-wide" in lowered and "outside" in lowered
    assert "print preview" in lowered
    assert "blank unsaved document" in lowered


def _assert_word_execution(
    result: dict,
    *,
    before: str,
    target: str,
    changed: bool,
    evidence_required: bool = True,
) -> None:
    assert result["status"] in {"ok", "partial"}, result.get("reason", result["status"])
    assert result["action_id"] == WORD_ACTION_ID
    assert result["changed"] is changed
    assert result["before"]["duplex"] == before
    assert result["after"]["duplex"] == target
    assert result["verification"] == "verified"
    assert isinstance(result.get("display"), dict) and result["display"].get("status")
    _assert_timing(result["timing"])
    if result["status"] == "ok":
        assert result["display"]["status"] == "displayed"
    _assert_screenshot(result["screenshot"], required=evidence_required)
    print(
        f"T039 outcome: status={result['status']}; changed={result['changed']}; "
        f"verification={result['verification']}; display={result['display']['status']}; "
        f"screenshot={result['screenshot']['status']}; timing={result['timing']}"
    )


def _assert_sanitized_audit(
    harness: LivePrinterHarness | LiveWordHarness,
    cid: str,
    action_id: str = ACTION_ID,
) -> None:
    assert harness.audit_path.exists(), "no real audit file was written"
    entries = [
        json.loads(line)
        for line in harness.audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = [entry for entry in entries if entry.get("conversation_id") == cid]
    assert rows and any(row.get("operation") == "mcp-action" for row in rows)
    assert any(action_id in json.dumps(row) for row in rows)
    assert any("duration_s" in row or "timing" in row for row in rows)
    rendered = json.dumps(rows, ensure_ascii=False)
    for forbidden in (
        str(harness.root),
        "/mcp-action/screenshots/",
        READ_MARKER,
        DUPLEX_READ_MARKER,
        "MCP_ACTION_JSON:",
        "Get-CimInstance",
        "Get-PrintConfiguration",
        "Set-PrintConfiguration",
        "Get-PrintJob",
        "SetDefaultPrinter",
        "FromBase64String",
        "RunPython",
        "CLIXML",
    ):
        assert forbidden not in rendered
    assert not TOKEN_RE.search(rendered), "a screenshot capability token reached the audit"
    assert all("query" not in row for row in rows)
    print(
        f"Live audit: rows={len(rows)}; operation=mcp-action; "
        f"action={action_id}; sanitized=true"
    )


async def _dify_turn(
    dcfg,
    *,
    user: str,
    query: str,
    conversation_id: str = "",
    ai_model: str = "cloud",
):
    return await asyncio.to_thread(
        dify_probe._stream_turn,
        dcfg,
        user=user,
        query=query,
        ai_model=ai_model,
        conversation_id=conversation_id,
    )


async def _enrich(console, dcfg, *turns) -> None:
    for turn in turns:
        await asyncio.to_thread(dify_probe._enrich_from_console, console, dcfg, turn)


def _dify_calls(turn, phase: str) -> list:
    return [call for call in turn.calls if dify_probe._phase(call) == phase]


def _turn_tool_names(turn) -> set[str]:
    names = set()
    evidence_keys = {"tool_response", "tool_responses", "tool_call_response"}
    for item in dify_probe._walk_dicts(turn.events):
        name = dify_probe._tool_name(item)
        if name and any(key in item for key in evidence_keys):
            names.add(name)
    return names


def _assert_no_desktop_side_effects(turn) -> None:
    forbidden = {
        name
        for name in _turn_tool_names(turn)
        if name.startswith(("windows_mcp_", "hermes_office", "hermes_run_", "hermes_file"))
    }
    assert not forbidden, f"unexpected desktop tool activity: {sorted(forbidden)}"
    assert "/mcp-action/screenshots/" not in turn.answer


def _assert_no_mcp_or_skill_detour(turn) -> None:
    names = _turn_tool_names(turn)
    assert "mcp_action" not in names
    assert not any(name.startswith("skill_") for name in names), (
        f"unexpected skill-loop detour: {sorted(names)}"
    )
    assert not turn.calls
    _assert_no_desktop_side_effects(turn)


def _assert_dify_draft(turn, printer: str) -> int:
    assert turn.conversation_id
    calls = _dify_calls(turn, "draft")
    assert calls and calls[-1].output.get("status") == "pending-confirmation"
    counts = set()
    for call in calls:
        assert call.inputs["conversation_id"] == turn.conversation_id
        assert call.inputs["query"] == turn.query
        assert call.inputs["action_id"] == ACTION_ID
        if call.output.get("status") == "pending-confirmation":
            assert call.inputs["parameters"] == {"printer": printer}
            _assert_pending(call.output, printer)
        counts.add(call.inputs["dialogue_count"])
    assert len(counts) == 1 and type(counts.pop()) is int
    paragraphs = re.split(r"\n\s*\n", turn.answer.strip())
    assert paragraphs[-1].strip() == OFFER
    manual = "\n\n".join(paragraphs[:-1])
    assert re.search(r"(?m)^\s*(?:\d+[.)]|[-*])\s+", manual), "manual steps must precede offer"
    assert "printer" in manual.lower()
    _assert_no_desktop_side_effects(turn)
    return calls[-1].inputs["dialogue_count"]


def _assert_dify_cancel(turn, cid: str, draft_count: int) -> None:
    calls = _dify_calls(turn, "cancel")
    assert calls and calls[-1].output.get("status") == "cancelled"
    for call in calls:
        assert call.inputs["conversation_id"] == cid
        assert call.inputs["query"] == "no"
        assert call.inputs["dialogue_count"] == draft_count + 1
        assert call.inputs.get("action_id") in (None, "")
        assert call.inputs.get("parameters") is None
    _assert_no_desktop_side_effects(turn)


def _draft_query(printer: str, lane: str = "general") -> str:
    prefix = (
        "For the Hermes Local Agent on my Windows computer: "
        if lane == "hermes"
        else (
            "For a written Windows how-to answer, not a PowerShell, file, launch, "
            "or Office task: "
        )
    )
    return (
        prefix
        + f"the exact target printer is {printer}. Give tailored manual steps for making "
        "it the default printer, then create the reviewed mcp_action draft for "
        "windows_default_printer. The request is complete; do not ask for more context, "
        "and do not confirm, open Settings, capture, or execute anything."
    )


@pytest.mark.asyncio
async def test_e01_dify_decline_leaves_original_default(live_printers, dcfg, console) -> None:
    async with live_printers as harness:
        user = f"t020-e01-{uuid.uuid4().hex}"
        draft = await _dify_turn(dcfg, user=user, query=_draft_query(harness.target_b))
        cancel = await _dify_turn(
            dcfg, user=user, query="no", conversation_id=draft.conversation_id
        )
        await _enrich(console, dcfg, draft, cancel)

        count = _assert_dify_draft(draft, harness.target_b)
        _assert_dify_cancel(cancel, draft.conversation_id, count)
        dify_probe._assert_guard(draft, None, dcfg)
        dify_probe._assert_guard(cancel, None, dcfg)
        assert _default_printer(await harness.read()) == harness.original


@pytest.mark.asyncio
async def test_e02_confirmed_service_changes_a_to_b_and_e08_repeat_is_safe(
    live_printers,
) -> None:
    async with live_printers as harness:
        cid = f"t020-e02-{uuid.uuid4().hex}"
        _assert_pending(await _draft(harness, cid, harness.target_b), harness.target_b)
        assert _default_printer(await harness.read()) == harness.original

        result = await _resolve(harness, "confirm", cid, 11, "yes")
        _assert_execution(
            result, before=harness.original, target=harness.target_b, changed=True
        )
        assert _same_printer(_default_printer(await harness.read()), harness.target_b)

        repeated = await _resolve(harness, "confirm", cid, 12, "yes")
        assert repeated["status"] == "blocked"
        assert repeated.get("changed") is not True
        assert _same_printer(_default_printer(await harness.read()), harness.target_b)
        _assert_sanitized_audit(harness, cid)


@pytest.mark.asyncio
async def test_e03_dify_modified_yes_never_executes_old_proposal(
    live_printers, dcfg, console
) -> None:
    async with live_printers as harness:
        user = f"t020-e03-{uuid.uuid4().hex}"
        draft = await _dify_turn(dcfg, user=user, query=_draft_query(harness.target_b))
        modified_query = f"yes, but use {harness.target_c}"
        modified = await _dify_turn(
            dcfg, user=user, query=modified_query, conversation_id=draft.conversation_id
        )
        await _enrich(console, dcfg, draft, modified)
        _assert_dify_draft(draft, harness.target_b)

        # The modified turn may explicitly invalidate B or supersede it with C;
        # either way no execution outcome is permitted before a fresh plain yes.
        assert all(
            call.output.get("status") not in {"ok", "partial"} for call in modified.calls
        )
        revised = [
            call
            for call in _dify_calls(modified, "draft")
            if call.output.get("status") == "pending-confirmation"
            and call.inputs.get("parameters") == {"printer": harness.target_c}
        ]
        assert revised, "modified confirmation did not require a fresh proposal for C"
        for call in _dify_calls(modified, "confirm"):
            assert call.output.get("status") == "blocked"
        revised_count = revised[-1].inputs["dialogue_count"]
        assert harness.target_c in modified.answer
        assert _default_printer(await harness.read()) == harness.original

        confirmed = await _dify_turn(
            dcfg, user=user, query="yes", conversation_id=draft.conversation_id
        )
        await _enrich(console, dcfg, confirmed)
        confirms = [
            call
            for call in _dify_calls(confirmed, "confirm")
            if call.inputs.get("dialogue_count") == revised_count + 1
            and call.inputs.get("query") == "yes"
        ]
        assert confirms, "fresh yes did not confirm the revised proposal on N+1"
        result = confirms[-1].output
        _assert_execution(
            result,
            before=harness.original,
            target=harness.target_c,
            changed=not _same_printer(harness.original, harness.target_c),
        )
        if result["screenshot"]["status"] == "captured":
            visible_answer = re.sub(r"<think>[\s\S]*?</think>", "", confirmed.answer)
            assert visible_answer.count(result["screenshot"]["image_url"]) == 1
        assert harness.target_c in confirmed.answer
        assert _same_printer(_default_printer(await harness.read()), harness.target_c)
        dify_probe._assert_guard(modified, None, dcfg)
        dify_probe._assert_guard(confirmed, None, dcfg)


@pytest.mark.asyncio
async def test_e08_orphan_confirmation_is_blocked_without_host_activity(live_printers) -> None:
    async with live_printers as harness:
        orphan = await _resolve(
            harness, "confirm", f"t020-orphan-{uuid.uuid4().hex}", 1, "yes"
        )
        assert orphan["status"] == "blocked"
        assert orphan.get("changed") is not True
        assert "screenshot" not in orphan
        assert _default_printer(await harness.read()) == harness.original


@pytest.mark.parametrize("response", ["yes", "no"])
@pytest.mark.asyncio
async def test_e08_generic_follow_up_yes_no_is_not_hijacked(
    live_printers, dcfg, console, response: str
) -> None:
    async with live_printers as harness:
        user = f"t020-e08-generic-{uuid.uuid4().hex}"
        follow_up = "Want me to explain Rayleigh scattering in more detail?"
        first = await _dify_turn(
            dcfg,
            user=user,
            query=(
                "Without using tools, explain in two sentences why the sky is blue. "
                f"End with the standalone ordinary follow-up question: {follow_up}"
            ),
        )
        second = await _dify_turn(
            dcfg, user=user, query=response, conversation_id=first.conversation_id
        )
        await _enrich(console, dcfg, first, second)

        assert follow_up in first.answer
        assert OFFER not in _visible_text(first.answer) and OFFER not in _visible_text(second.answer)
        assert not first.calls and not second.calls
        assert second.answer.strip()
        assert "no eligible proposal" not in second.answer.lower()
        if response == "yes":
            assert "scatter" in second.answer.lower()
        _assert_no_desktop_side_effects(first)
        _assert_no_desktop_side_effects(second)
        assert _default_printer(await harness.read()) == harness.original


@pytest.mark.asyncio
async def test_e09_nonexistent_target_never_selects_a_substitute(live_printers) -> None:
    async with live_printers as harness:
        cid = f"t020-e09-missing-{uuid.uuid4().hex}"
        missing = f"T020 nonexistent printer {uuid.uuid4().hex}"
        result = await _draft(harness, cid, missing)
        assert result["status"] == "error"
        assert "exactly one" in result.get("reason", "").lower()
        assert "offer" not in result
        blocked = await _resolve(harness, "confirm", cid, 11, "yes")
        assert blocked["status"] == "blocked"
        assert _default_printer(await harness.read()) == harness.original


@pytest.mark.asyncio
async def test_e09_ambiguous_installed_target_never_selects_one(live_printers) -> None:
    async with live_printers as harness:
        if harness.ambiguous is None:
            pytest.skip("no case-insensitive duplicate printer is installed; none will be created")
        cid = f"t020-e09-ambiguous-{uuid.uuid4().hex}"
        result = await _draft(harness, cid, harness.ambiguous)
        assert result["status"] == "error"
        assert "exactly one" in result.get("reason", "").lower()
        assert "offer" not in result
        assert _default_printer(await harness.read()) == harness.original


@pytest.mark.asyncio
async def test_e10_already_active_is_verified_changed_false(live_printers) -> None:
    async with live_printers as harness:
        cid = f"t020-e10-{uuid.uuid4().hex}"
        _assert_pending(await _draft(harness, cid, harness.original), harness.original)
        result = await _resolve(harness, "confirm", cid, 11, "yes")
        _assert_execution(
            result, before=harness.original, target=harness.original, changed=False
        )
        assert _default_printer(await harness.read()) == harness.original
        _assert_sanitized_audit(harness, cid)


@pytest.mark.asyncio
async def test_e11_managed_default_caveat_and_no_registry_write(live_printers) -> None:
    async with live_printers as harness:
        managed = harness.initial["managed"]
        if managed["status"] == "ok" and managed.get("value") == 1:
            pytest.skip("Windows managed-default mode is disabled (LegacyDefaultPrinterMode=1)")
        expected = (
            "let windows manage"
            if managed["status"] == "absent" or managed.get("value") == 0
            else "unknown"
        )
        cid = f"t020-e11-{uuid.uuid4().hex}"
        draft = await _draft(harness, cid, harness.original)
        _assert_pending(draft, harness.original)
        assert expected in " ".join(draft["caveats"]).lower()

        result = await _resolve(harness, "confirm", cid, 11, "yes")
        _assert_execution(
            result,
            before=harness.original,
            target=harness.original,
            changed=False,
            evidence_required=False,
        )
        assert expected in " ".join(result["caveats"]).lower()
        after = await harness.read()
        assert after["managed"] == managed, "managed-default registry state changed"
        assert _default_printer(after) == harness.original
        _assert_sanitized_audit(harness, cid)


@pytest.mark.asyncio
async def test_e04_word_long_edge_is_verified_visible_and_document_safe(live_word) -> None:
    async with live_word as harness:
        cid = f"t039-e04-{uuid.uuid4().hex}"
        target = DUPLEX_MODES["long-edge"]
        draft = await _word_draft(
            harness.service, cid, harness.printer, "long-edge"
        )
        _assert_word_pending(draft, harness.printer, "long-edge")
        unchanged = await harness.assert_preserved()
        assert _duplex_mode(unchanged) == harness.original_mode

        result = await _resolve(harness, "confirm", cid, 11, "yes")
        _assert_word_execution(
            result,
            before=harness.original_mode,
            target=target,
            changed=harness.original_mode != target,
        )
        after = await harness.assert_preserved(preview=True)
        assert _duplex_mode(after) == target
        _assert_sanitized_audit(harness, cid, WORD_ACTION_ID)


@pytest.mark.asyncio
async def test_e05_word_short_edge_cancel_and_already_active_are_honest(live_word) -> None:
    async with live_word as harness:
        cancel_cid = f"t039-e05-cancel-{uuid.uuid4().hex}"
        _assert_word_pending(
            await _word_draft(harness.service, cancel_cid, harness.printer, "short-edge"),
            harness.printer,
            "short-edge",
        )
        cancelled = await _resolve(harness, "cancel", cancel_cid, 11, "no")
        assert cancelled["status"] == "cancelled"
        unchanged = await harness.assert_preserved()
        assert _duplex_mode(unchanged) == harness.original_mode

        cid = f"t039-e05-{uuid.uuid4().hex}"
        target = DUPLEX_MODES["short-edge"]
        _assert_word_pending(
            await _word_draft(harness.service, cid, harness.printer, "short-edge"),
            harness.printer,
            "short-edge",
        )
        result = await _resolve(harness, "confirm", cid, 11, "yes")
        _assert_word_execution(
            result,
            before=harness.original_mode,
            target=target,
            changed=harness.original_mode != target,
        )
        after = await harness.assert_preserved(preview=True)
        assert _duplex_mode(after) == target

        active_cid = f"t039-e05-active-{uuid.uuid4().hex}"
        _assert_word_pending(
            await _word_draft(
                harness.service, active_cid, harness.printer, "short-edge"
            ),
            harness.printer,
            "short-edge",
        )
        active = await _resolve(harness, "confirm", active_cid, 11, "yes")
        _assert_word_execution(active, before=target, target=target, changed=False)
        still_active = await harness.assert_preserved(preview=True)
        assert _duplex_mode(still_active) == target
        _assert_sanitized_audit(harness, cid, WORD_ACTION_ID)
        _assert_sanitized_audit(harness, active_cid, WORD_ACTION_ID)


@pytest.mark.asyncio
async def test_e06_hermes_default_printer_and_general_local_behavior(
    live_printers, dcfg, console
) -> None:
    async with live_printers as harness:
        decline_user = f"t039-e06-decline-{uuid.uuid4().hex}"
        draft = await _dify_turn(
            dcfg,
            user=decline_user,
            query=_draft_query(harness.target_b, lane="hermes"),
        )
        cancel = await _dify_turn(
            dcfg,
            user=decline_user,
            query="no",
            conversation_id=draft.conversation_id,
        )
        await _enrich(console, dcfg, draft, cancel)
        count = _assert_dify_draft(draft, harness.target_b)
        _assert_dify_cancel(cancel, draft.conversation_id, count)
        dify_probe._assert_guard(draft, None, dcfg)
        dify_probe._assert_guard(cancel, None, dcfg)
        assert _default_printer(await harness.read()) == harness.original

        confirm_user = f"t039-e06-confirm-{uuid.uuid4().hex}"
        confirmed_draft = await _dify_turn(
            dcfg,
            user=confirm_user,
            query=_draft_query(harness.target_b, lane="hermes"),
        )
        confirmed = await _dify_turn(
            dcfg,
            user=confirm_user,
            query="yes",
            conversation_id=confirmed_draft.conversation_id,
        )
        repeated = await _dify_turn(
            dcfg,
            user=confirm_user,
            query="yes",
            conversation_id=confirmed_draft.conversation_id,
        )
        local = await _dify_turn(
            dcfg,
            user=f"t039-e06-local-{uuid.uuid4().hex}",
            query=(
                "Without tools or an MCP-action offer, answer this ordinary "
                "General-local question in one sentence: what color is clear water?"
            ),
            ai_model="local",
        )
        await _enrich(console, dcfg, confirmed_draft, confirmed, repeated, local)

        confirmed_count = _assert_dify_draft(confirmed_draft, harness.target_b)
        confirms = [
            call
            for call in _dify_calls(confirmed, "confirm")
            if call.inputs.get("dialogue_count") == confirmed_count + 1
            and call.inputs.get("query") == "yes"
        ]
        assert confirms, "Hermes fresh yes did not confirm the stored proposal"
        result = confirms[-1].output
        _assert_execution(
            result, before=harness.original, target=harness.target_b, changed=True
        )
        if result["screenshot"]["status"] == "captured":
            visible_answer = re.sub(r"<think>[\s\S]*?</think>", "", confirmed.answer)
            assert visible_answer.count(result["screenshot"]["image_url"]) == 1
        dify_probe._assert_guard(confirmed_draft, None, dcfg)
        dify_probe._assert_guard(confirmed, None, dcfg)
        repeat_calls = _dify_calls(repeated, "confirm")
        assert repeat_calls, "Hermes repeated yes did not reach the consumed proposal"
        assert all(
            call.output.get("status") == "blocked"
            and call.output.get("changed") is not True
            for call in repeat_calls
        )
        assert "/mcp-action/screenshots/" not in repeated.answer
        dify_probe._assert_guard(repeated, None, dcfg)
        assert _same_printer(_default_printer(await harness.read()), harness.target_b)

        assert local.answer.strip()
        assert OFFER not in local.answer
        _assert_no_mcp_or_skill_detour(local)
        assert _same_printer(_default_printer(await harness.read()), harness.target_b)


@pytest.mark.asyncio
async def test_unsupported_office_procedure_has_no_offer_or_document_effect(
    live_word, dcfg, console
) -> None:
    async with live_word as harness:
        cid = f"t039-unsupported-{uuid.uuid4().hex}"
        unsupported = await harness.service.handle(
            phase="draft",
            conversation_id=cid,
            dialogue_count=10,
            action_id="excel_freeze_panes",
            parameters={},
        )
        assert unsupported["status"] == "unsupported"
        assert "offer" not in unsupported

        turn = await _dify_turn(
            dcfg,
            user=f"t039-unsupported-{uuid.uuid4().hex}",
            query=(
                "For a written Excel how-to answer only, explain how to freeze panes. "
                "This is not a Word duplex request; do not execute or offer an automatic "
                "desktop action."
            ),
        )
        await _enrich(console, dcfg, turn)
        assert turn.answer.strip()
        assert OFFER not in turn.answer
        _assert_no_mcp_or_skill_detour(turn)
        dify_probe._assert_guard(turn, None, dcfg)
        unchanged = await harness.assert_preserved()
        assert _duplex_mode(unchanged) == harness.original_mode


@pytest.mark.asyncio
async def test_e10_unsupported_duplex_capability_is_honest_without_mutation(live_word) -> None:
    async with live_word as harness:
        unsupported_printer = harness.unsupported_printer()
        if unsupported_printer is None:
            pytest.skip("no installed non-duplex printer is available for a read-only check")
        cid = f"t039-e10-capability-{uuid.uuid4().hex}"
        result = await _word_draft(
            harness.service, cid, unsupported_printer, "long-edge"
        )
        assert result["status"] == "error"
        assert "offer" not in result
        reason = result.get("reason", "").casefold()
        assert any(term in reason for term in ("capab", "support", "duplex"))
        blocked = await _resolve(harness, "confirm", cid, 11, "yes")
        assert blocked["status"] == "blocked"
        unchanged = await harness.assert_preserved()
        assert _duplex_mode(unchanged) == harness.original_mode
        _assert_sanitized_audit(harness, cid, WORD_ACTION_ID)


@pytest.mark.asyncio
async def test_e10_access_denied_reports_actual_state_without_fabrication(live_word) -> None:
    async with live_word as harness:
        orientation = "short-edge" if harness.original_orientation == "long-edge" else "long-edge"
        target = DUPLEX_MODES[orientation]
        cid = f"t039-e10-access-{uuid.uuid4().hex}"
        draft = await _word_draft(harness.service, cid, harness.printer, orientation)
        if draft["status"] == "pending-confirmation":
            _assert_word_pending(draft, harness.printer, orientation)
            result = await _resolve(harness, "confirm", cid, 11, "yes")
        else:
            result = draft

        if result["status"] != "error":
            _assert_word_execution(
                result, before=harness.original_mode, target=target, changed=True
            )
            after = await harness.assert_preserved(preview=True)
            assert _duplex_mode(after) == target
            pytest.skip("this approved printer/user has no access-denied condition to observe")

        reason = result.get("reason", "")
        assert 0 < len(reason) <= 500
        assert any(
            term in reason.casefold()
            for term in ("access", "denied", "permission", "administrator")
        )
        assert "offer" not in result
        assert result.get("screenshot", {}).get("status") != "captured"
        assert "image_url" not in result.get("screenshot", {})
        after = await harness.assert_preserved()
        observed = _duplex_mode(after)
        assert observed in {harness.original_mode, target}
        if result.get("after", {}).get("duplex") is not None:
            assert result["after"]["duplex"] == observed
        if result.get("verification") == "verified":
            assert observed == target
            assert result.get("changed") is True
        else:
            assert result.get("changed") is not True
        _assert_sanitized_audit(harness, cid, WORD_ACTION_ID)


@pytest.mark.asyncio
async def test_e12_word_com_busy_has_no_backstage_fallback(live_word, monkeypatch) -> None:
    async with live_word as harness:
        orientation = "short-edge" if harness.original_orientation == "long-edge" else "long-edge"
        target = DUPLEX_MODES[orientation]
        cid = f"t039-e12-{uuid.uuid4().hex}"
        _assert_word_pending(
            await _word_draft(harness.service, cid, harness.printer, orientation),
            harness.printer,
            orientation,
        )
        posts = []

        def busy_frame(*args, **kwargs) -> dict:
            return {"error": {"message": "Word busy: RPC_E_SERVERCALL_RETRYLATER"}}

        def record_post(url, json, timeout):
            posts.append({"url": url, "json": json, "timeout": timeout})
            return object()

        with monkeypatch.context() as injected:
            injected.setattr(harness.office, "_next", busy_frame)
            injected.setattr(
                "agentic_rag_mcp.office_lanes.proxy.httpx.post", record_post
            )
            result = await _resolve(harness, "confirm", cid, 11, "yes")
        _assert_word_execution(
            result,
            before=harness.original_mode,
            target=target,
            changed=True,
            evidence_required=False,
        )
        assert result["status"] == "partial"
        assert result["display"]["status"] == "attempted-but-failed"
        assert result["screenshot"]["status"] == "skipped-display-unverified"
        assert "image_url" not in result["screenshot"]
        assert len(posts) == 1, "busy Word COM must not be retried"
        assert 0 < posts[0]["timeout"] < 180
        code = posts[0]["json"]["params"]["arguments"]["code"]
        assert "ExecuteMso" not in code
        assert "PrintPreviewAndPrint" not in code
        assert "RPC_E_SERVERCALL_RETRYLATER" not in json.dumps(result)
        after = await harness.assert_preserved()
        assert _duplex_mode(after) == target
        _assert_sanitized_audit(harness, cid, WORD_ACTION_ID)


@pytest.mark.asyncio
async def test_e13_display_verification_failure_is_partial_and_skips_screenshot(
    live_word,
) -> None:
    async with live_word as harness:
        class UnverifiedDisplay:
            def __init__(self) -> None:
                self.calls = 0

            def show_word_print(self) -> dict:
                self.calls += 1
                outcome = harness.display.show_word_print()
                return {
                    **outcome,
                    "preview_ok": False,
                    "view_type": None,
                    "visible": False,
                    "foreground": False,
                }

        display = UnverifiedDisplay()
        harness.service = harness.make_service(display=display)
        orientation = "short-edge" if harness.original_orientation == "long-edge" else "long-edge"
        target = DUPLEX_MODES[orientation]
        cid = f"t039-e13-{uuid.uuid4().hex}"
        _assert_word_pending(
            await _word_draft(harness.service, cid, harness.printer, orientation),
            harness.printer,
            orientation,
        )
        result = await _resolve(harness, "confirm", cid, 11, "yes")
        _assert_word_execution(
            result,
            before=harness.original_mode,
            target=target,
            changed=True,
            evidence_required=False,
        )
        assert result["status"] == "partial"
        assert result["display"]["status"] == "unverified"
        assert result["screenshot"]["status"] == "skipped-display-unverified"
        assert "image_url" not in result["screenshot"]
        assert display.calls == 1
        after = await harness.assert_preserved()
        assert _duplex_mode(after) == target
        _assert_sanitized_audit(harness, cid, WORD_ACTION_ID)


@pytest.mark.asyncio
async def test_e14_real_capture_with_storage_failure_is_partial(live_word) -> None:
    async with live_word as harness:
        from agentic_rag_mcp.mcp_action.screenshots import ScreenshotStore
        from agentic_rag_mcp.mcp_action.service import ScreenshotCapture

        class FailingStore(ScreenshotStore):
            def save(self, data: bytes, mime_type: str = ""):
                raise OSError("injected screenshot storage failure")

        store = FailingStore(root=harness.root / "screenshot-store")
        capture = ScreenshotCapture(store=store, audit=harness.audit)
        harness.service = harness.make_service(screenshots=capture)
        orientation = "short-edge" if harness.original_orientation == "long-edge" else "long-edge"
        target = DUPLEX_MODES[orientation]
        cid = f"t039-e14-{uuid.uuid4().hex}"
        _assert_word_pending(
            await _word_draft(harness.service, cid, harness.printer, orientation),
            harness.printer,
            orientation,
        )
        result = await _resolve(harness, "confirm", cid, 11, "yes")
        _assert_word_execution(
            result,
            before=harness.original_mode,
            target=target,
            changed=True,
            evidence_required=False,
        )
        assert result["status"] == "partial"
        assert result["display"]["status"] == "displayed"
        assert result["screenshot"]["status"] == "attempted-but-failed"
        assert "image_url" not in result["screenshot"]
        assert list(store.root.iterdir()) == []
        after = await harness.assert_preserved(preview=True)
        assert _duplex_mode(after) == target
        _assert_sanitized_audit(harness, cid, WORD_ACTION_ID)


@pytest.mark.asyncio
async def test_e15_windows_mcp_offline_before_mutation_has_no_fabricated_result(
    live_word, monkeypatch
) -> None:
    async with live_word as harness:
        from agentic_rag_mcp.windows_mcp import client as windows_client

        cid = f"t039-e15-{uuid.uuid4().hex}"
        with monkeypatch.context() as offline:
            offline.setattr(
                windows_client, "BRIDGE_SSE_URL", "http://127.0.0.1:1/sse"
            )
            result = await _word_draft(
                harness.service, cid, harness.printer, "long-edge"
            )
            assert result["status"] == "error"
            assert "offer" not in result
            assert result.get("changed") is not True
            assert result.get("screenshot", {}).get("status") != "captured"
            blocked = await _resolve(harness, "confirm", cid, 11, "yes")
            assert blocked["status"] == "blocked"
        unchanged = await harness.assert_preserved()
        assert _duplex_mode(unchanged) == harness.original_mode
        _assert_sanitized_audit(harness, cid, WORD_ACTION_ID)


@pytest.mark.asyncio
async def test_e15_office_mcp_offline_before_mutation_has_no_fabricated_result(
    live_word,
) -> None:
    async with live_word as harness:
        from agentic_rag_mcp.office_lanes.proxy import OfficeProxy

        # Defer only the constructor's initial connection. The instance still
        # uses the real bounded OfficeProxy transport inside the service.
        offline_office = OfficeProxy.__new__(OfficeProxy)
        offline_office.base = "http://127.0.0.1:1"
        offline_office.timeout_s = 2
        offline_office._lock = threading.Lock()
        offline_office._endpoint = None
        harness.service = harness.make_service(display=offline_office)

        cid = f"t039-e15-office-{uuid.uuid4().hex}"
        draft = await _word_draft(harness.service, cid, harness.printer, "long-edge")
        if draft["status"] == "pending-confirmation":
            result = await _resolve(harness, "confirm", cid, 11, "yes")
        else:
            result = draft
        assert result["status"] == "partial"
        assert result["verification"] == "verified"
        assert result.get("changed") is False
        assert result["display"]["status"] == "attempted-but-failed"
        assert 0 < len(result["display"].get("reason", "")) <= 500
        assert result.get("screenshot", {}).get("status") == "skipped-display-unverified"
        assert "127.0.0.1" not in json.dumps(result)
        unchanged = await harness.assert_preserved()
        assert _duplex_mode(unchanged) == harness.original_mode
        _assert_sanitized_audit(harness, cid, WORD_ACTION_ID)


@pytest.mark.asyncio
async def test_e16_post_mutation_transport_failure_is_not_retried_or_rolled_back(
    live_word,
) -> None:
    async with live_word as harness:
        class PostMutationFailureActions:
            def __init__(self) -> None:
                self.execute_calls = 0

            async def validate_word_printer_duplex(self, printer: str, orientation: str) -> dict:
                return await harness.actions.validate_word_printer_duplex(printer, orientation)

            async def execute_word_printer_duplex(self, printer: str, orientation: str) -> dict:
                self.execute_calls += 1
                await harness.actions.execute_word_printer_duplex(printer, orientation)
                raise ConnectionError("injected post-mutation transport failure")

        actions = PostMutationFailureActions()
        harness.service = harness.make_service(actions=actions)
        orientation = "short-edge" if harness.original_orientation == "long-edge" else "long-edge"
        target = DUPLEX_MODES[orientation]
        cid = f"t039-e16-{uuid.uuid4().hex}"
        _assert_word_pending(
            await _word_draft(harness.service, cid, harness.printer, orientation),
            harness.printer,
            orientation,
        )
        result = await _resolve(harness, "confirm", cid, 11, "yes")
        assert result["status"] == "error"
        assert result["action_id"] == WORD_ACTION_ID
        assert 0 < len(result.get("reason", "")) <= 500
        assert "injected post-mutation" not in result["reason"]
        assert result.get("verification") in {
            "verified",
            "mismatch",
            "unavailable",
            "not-run",
        }
        assert result.get("screenshot", {}).get("status") != "captured"
        assert actions.execute_calls == 1, "unknown mutation was retried"
        after = await harness.assert_preserved()
        assert _duplex_mode(after) == target, "an automatic rollback hid the actual state"
        if result.get("after", {}).get("duplex") is not None:
            assert result["after"]["duplex"] == target
        if result.get("verification") == "verified":
            assert result.get("changed") is True
        else:
            assert result.get("changed") is not True
        _assert_sanitized_audit(harness, cid, WORD_ACTION_ID)


@pytest.mark.asyncio
async def test_e17_concurrent_word_actions_are_serialized_with_queue_timing(live_word) -> None:
    async with live_word as harness:
        class TrackedActions:
            def __init__(self) -> None:
                self.active = 0
                self.max_active = 0
                self.calls = []
                self.entered = asyncio.Event()

            async def validate_word_printer_duplex(self, printer: str, orientation: str) -> dict:
                return await harness.actions.validate_word_printer_duplex(printer, orientation)

            async def execute_word_printer_duplex(self, printer: str, orientation: str) -> dict:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                self.calls.append(orientation)
                self.entered.set()
                try:
                    await asyncio.sleep(0.2)
                    return await harness.actions.execute_word_printer_duplex(printer, orientation)
                finally:
                    self.active -= 1

        actions = TrackedActions()
        harness.service = harness.make_service(actions=actions)
        first_orientation = (
            "short-edge" if harness.original_orientation == "long-edge" else "long-edge"
        )
        second_orientation = (
            "long-edge" if first_orientation == "short-edge" else "short-edge"
        )
        first_target = DUPLEX_MODES[first_orientation]
        second_target = DUPLEX_MODES[second_orientation]
        first_cid = f"t039-e17-first-{uuid.uuid4().hex}"
        second_cid = f"t039-e17-second-{uuid.uuid4().hex}"
        for cid, orientation in (
            (first_cid, first_orientation),
            (second_cid, second_orientation),
        ):
            _assert_word_pending(
                await _word_draft(harness.service, cid, harness.printer, orientation),
                harness.printer,
                orientation,
            )

        first_task = asyncio.create_task(
            _resolve(harness, "confirm", first_cid, 11, "yes")
        )
        await asyncio.wait_for(actions.entered.wait(), timeout=5)
        second_task = asyncio.create_task(
            _resolve(harness, "confirm", second_cid, 11, "yes")
        )
        first, second = await asyncio.gather(first_task, second_task)
        _assert_word_execution(
            first,
            before=harness.original_mode,
            target=first_target,
            changed=True,
            evidence_required=False,
        )
        assert second["timing"]["queue_wait_s"] > 0
        if second["status"] == "queued-timeout":
            assert second["changed"] is False
            assert second["verification"] == "not-run"
            assert actions.calls == [first_orientation]
            expected = first_target
        else:
            _assert_word_execution(
                second,
                before=first_target,
                target=second_target,
                changed=True,
                evidence_required=False,
            )
            assert actions.calls == [first_orientation, second_orientation]
            expected = second_target
        assert actions.max_active == 1, "two real host actions overlapped"
        after = await harness.assert_preserved()
        assert _duplex_mode(after) == expected
        _assert_sanitized_audit(harness, first_cid, WORD_ACTION_ID)
        _assert_sanitized_audit(harness, second_cid, WORD_ACTION_ID)


@pytest.mark.asyncio
async def test_e18_simultaneous_duplicate_word_confirms_execute_exactly_once(live_word) -> None:
    async with live_word as harness:
        class CountingActions:
            def __init__(self) -> None:
                self.execute_calls = []

            async def validate_word_printer_duplex(
                self, printer: str, orientation: str
            ) -> dict:
                return await harness.actions.validate_word_printer_duplex(printer, orientation)

            async def execute_word_printer_duplex(
                self, printer: str, orientation: str
            ) -> dict:
                self.execute_calls.append((printer, orientation))
                return await harness.actions.execute_word_printer_duplex(printer, orientation)

        actions = CountingActions()
        harness.service = harness.make_service(actions=actions)
        orientation = "short-edge" if harness.original_orientation == "long-edge" else "long-edge"
        target = DUPLEX_MODES[orientation]
        cid = f"t039-e18-{uuid.uuid4().hex}"
        _assert_word_pending(
            await _word_draft(harness.service, cid, harness.printer, orientation),
            harness.printer,
            orientation,
        )

        confirmation = {
            "phase": "confirm",
            "conversation_id": cid,
            "dialogue_count": 11,
            "query": "yes",
        }
        results = await asyncio.gather(
            harness.service.handle(**confirmation),
            harness.service.handle(**confirmation),
        )

        executed = [result for result in results if result["status"] in {"ok", "partial"}]
        blocked = [result for result in results if result["status"] == "blocked"]
        assert len(executed) == 1 and len(blocked) == 1, results
        assert blocked[0]["reason"] == "No eligible proposal is pending."
        assert blocked[0].get("changed") is not True
        assert "display" not in blocked[0] and "screenshot" not in blocked[0]
        assert actions.execute_calls == [(harness.printer, orientation)]
        _assert_word_execution(
            executed[0], before=harness.original_mode, target=target, changed=True
        )
        after = await harness.assert_preserved(preview=True)
        assert _duplex_mode(after) == target
        _assert_sanitized_audit(harness, cid, WORD_ACTION_ID)

    # LiveWordHarness.__aexit__ performs this restoration in its finally path.
    assert _duplex_mode(await harness.read()) == harness.original_mode


@pytest.mark.asyncio
async def test_e19_word_confirmation_expires_at_exactly_900_seconds(live_word) -> None:
    async with live_word as harness:
        from agentic_rag_mcp.mcp_action.state import ProposalStore

        class FakeClock:
            def __init__(self) -> None:
                self.now = 0.0

            def __call__(self) -> float:
                return self.now

            def advance(self, seconds: float) -> None:
                self.now += seconds

        class NoExecutionActions:
            def __init__(self) -> None:
                self.execute_calls = []

            async def validate_word_printer_duplex(
                self, printer: str, orientation: str
            ) -> dict:
                return await harness.actions.validate_word_printer_duplex(printer, orientation)

            async def execute_word_printer_duplex(
                self, printer: str, orientation: str
            ) -> dict:
                self.execute_calls.append((printer, orientation))
                raise AssertionError("expired confirmation reached the executor")

        class NoEvidenceCalls:
            def __init__(self) -> None:
                self.display_calls = 0
                self.screenshot_calls = []

            def show_word_print(self) -> dict:
                self.display_calls += 1
                raise AssertionError("expired confirmation reached Word display")

            async def capture(self, conversation_id: str) -> dict:
                self.screenshot_calls.append(conversation_id)
                raise AssertionError("expired confirmation reached screenshot capture")

        clock = FakeClock()
        actions = NoExecutionActions()
        evidence = NoEvidenceCalls()
        harness.service = harness.make_service(
            store=ProposalStore(clock=clock),
            actions=actions,
            display=evidence,
            screenshots=evidence,
            clock=clock,
        )
        orientation = "short-edge" if harness.original_orientation == "long-edge" else "long-edge"
        cid = f"t039-e19-{uuid.uuid4().hex}"
        _assert_word_pending(
            await _word_draft(harness.service, cid, harness.printer, orientation),
            harness.printer,
            orientation,
        )

        clock.advance(900.0)
        assert clock() == 900.0
        result = await _resolve(harness, "confirm", cid, 11, "yes")

        assert result["status"] == "blocked"
        assert result["reason"] == "No eligible proposal is pending."
        assert result.get("changed") is not True
        assert "display" not in result and "screenshot" not in result
        assert actions.execute_calls == []
        assert evidence.display_calls == []
        assert evidence.screenshot_calls == []
        unchanged = await harness.assert_preserved()
        assert _duplex_mode(unchanged) == harness.original_mode
        _assert_sanitized_audit(harness, cid, WORD_ACTION_ID)


BENCHMARK_RUNS = 20
BENCHMARK_RESULTS_PATH = (
    Path(__file__).resolve().parents[2] / "specs/047-mcp-action/benchmark-results.json"
)


def _nearest_rank_p95(values: list[float]) -> float:
    """Return nearest-rank p95: the 19th sorted value for 20 samples."""
    assert values, "p95 requires at least one sample"
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _new_benchmark_report() -> dict:
    return {
        "state": "failure",
        "count": 0,
        "p95_execution_s": None,
        "p95_queue_wait_s": None,
        "p95_total_s": None,
        "restoration": "pending",
        "samples": [],
    }


def _benchmark_status(value: object) -> str:
    if isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value):
        return value
    return "missing"


def _benchmark_sample(result: dict) -> dict:
    timing = result.get("timing")
    timing = timing if isinstance(timing, dict) else {}
    display = result.get("display")
    display = display if isinstance(display, dict) else {}
    screenshot = result.get("screenshot")
    screenshot = screenshot if isinstance(screenshot, dict) else {}

    def duration(key: str) -> float | None:
        value = timing.get(key)
        if type(value) in (int, float) and math.isfinite(value) and value >= 0:
            return float(value)
        return None

    # Deliberately retain no reasons, targets, URLs, tokens, paths, or image data.
    return {
        "execution_s": duration("execution_s"),
        "queue_wait_s": duration("queue_wait_s"),
        "total_s": duration("total_s"),
        "status": _benchmark_status(result.get("status")),
        "verification": _benchmark_status(result.get("verification")),
        "display": _benchmark_status(display.get("status")),
        "screenshot": _benchmark_status(screenshot.get("status")),
    }


def _assert_benchmark_sample(sample: dict, run: int) -> None:
    assert sample["status"] == "ok", f"T056 run {run}: execution status was not ok"
    assert sample["verification"] == "verified", (
        f"T056 run {run}: after-read verification was not verified"
    )
    assert sample["display"] == "displayed", f"T056 run {run}: display was not displayed"
    assert sample["screenshot"] == "captured", (
        f"T056 run {run}: screenshot was not captured"
    )
    for key in ("execution_s", "queue_wait_s", "total_s"):
        assert type(sample[key]) in (int, float) and sample[key] >= 0, (
            f"T056 run {run}: {key} was not reported"
        )
    assert sample["total_s"] >= sample["execution_s"], (
        f"T056 run {run}: total_s excluded execution_s"
    )


def _finalize_benchmark_report(report: dict) -> None:
    samples = report["samples"]
    report["count"] = len(samples)
    for key in ("execution_s", "queue_wait_s", "total_s"):
        values = [sample[key] for sample in samples if sample[key] is not None]
        report[f"p95_{key}"] = _nearest_rank_p95(values) if values else None


def _write_benchmark_report(action_id: str, report: dict) -> None:
    try:
        document = json.loads(BENCHMARK_RESULTS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        document = {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        document = {}
    if not isinstance(document, dict):
        document = {}
    actions = document.get("actions")
    actions = actions if isinstance(actions, dict) else {}
    actions[action_id] = report
    BENCHMARK_RESULTS_PATH.write_text(
        json.dumps({"actions": actions}, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


async def _printer_restoration_status(harness: LivePrinterHarness) -> str:
    original = getattr(harness, "original", None)
    if original is None:
        return "not-applicable"
    try:
        observed = _default_printer(await harness.read())
    except Exception:  # noqa: BLE001 - only the sanitized restoration state is persisted
        return "unknown"
    return "restored" if _same_printer(observed, original) else "failed"


async def _word_restoration_status(harness: LiveWordHarness) -> str:
    original = getattr(harness, "original_mode", None)
    if original is None:
        return "not-applicable"
    try:
        observed = _duplex_mode(await harness.read())
    except Exception:  # noqa: BLE001 - only the sanitized restoration state is persisted
        return "unknown"
    return "restored" if observed == original else "failed"


@pytest.mark.skipif(
    os.environ.get("RUN_MCP_ACTION_BENCHMARK") != "1",
    reason="owner-present 20-run benchmark: set RUN_MCP_ACTION_BENCHMARK=1",
)
@pytest.mark.asyncio
async def test_t056_default_printer_benchmark(live_printers) -> None:
    report = _new_benchmark_report()
    try:
        async with live_printers as harness:
            other = (
                harness.other
                if not _same_printer(harness.other, harness.original)
                else harness.target_b
            )
            for run in range(1, BENCHMARK_RUNS + 1):
                target = other if run % 2 else harness.original
                before = harness.original if run % 2 else other
                cid = f"t056-printer-{run}-{uuid.uuid4().hex}"
                draft = await _draft(harness, cid, target)
                assert draft.get("status") == "pending-confirmation", (
                    f"T056 run {run}: draft was not pending confirmation"
                )
                result = await _resolve(harness, "confirm", cid, 11, "yes")
                sample = _benchmark_sample(result)
                report["samples"].append(sample)
                _assert_benchmark_sample(sample, run)
                assert result.get("changed") is True, (
                    f"T056 run {run}: alternating target did not change the default"
                )
                assert _same_printer(result["before"]["default_printer"], before)
                assert _same_printer(result["after"]["default_printer"], target)

            assert len(report["samples"]) == BENCHMARK_RUNS
            p95 = _nearest_rank_p95(
                [sample["execution_s"] for sample in report["samples"]]
            )
            assert p95 <= 60, f"T056 default-printer p95 execution_s={p95:.3f} exceeds 60s"
            report["state"] = "pass"
    except pytest.skip.Exception:
        report["state"] = "environment-blocked"
        raise
    except BaseException as exc:
        report["state"] = "failure"
        report["failure_type"] = type(exc).__name__
        raise
    finally:
        _finalize_benchmark_report(report)
        report["restoration"] = await _printer_restoration_status(live_printers)
        _write_benchmark_report(ACTION_ID, report)


@pytest.mark.skipif(
    os.environ.get("RUN_MCP_ACTION_BENCHMARK") != "1",
    reason="owner-present 20-run benchmark: set RUN_MCP_ACTION_BENCHMARK=1",
)
@pytest.mark.asyncio
async def test_t056_word_duplex_benchmark(live_word) -> None:
    report = _new_benchmark_report()
    try:
        async with live_word as harness:
            other = (
                "short-edge" if harness.original_orientation == "long-edge" else "long-edge"
            )
            for run in range(1, BENCHMARK_RUNS + 1):
                orientation = other if run % 2 else harness.original_orientation
                before_orientation = (
                    harness.original_orientation if run % 2 else other
                )
                cid = f"t056-word-{run}-{uuid.uuid4().hex}"
                draft = await _word_draft(
                    harness.service, cid, harness.printer, orientation
                )
                assert draft.get("status") == "pending-confirmation", (
                    f"T056 run {run}: draft was not pending confirmation"
                )
                result = await _resolve(harness, "confirm", cid, 11, "yes")
                sample = _benchmark_sample(result)
                report["samples"].append(sample)
                _assert_benchmark_sample(sample, run)
                assert result.get("changed") is True, (
                    f"T056 run {run}: alternating orientation did not change duplex"
                )
                assert result["before"]["duplex"] == DUPLEX_MODES[before_orientation]
                assert result["after"]["duplex"] == DUPLEX_MODES[orientation]

            assert len(report["samples"]) == BENCHMARK_RUNS
            p95 = _nearest_rank_p95(
                [sample["execution_s"] for sample in report["samples"]]
            )
            assert p95 <= 90, f"T056 Word-duplex p95 execution_s={p95:.3f} exceeds 90s"
            report["state"] = "pass"
    except pytest.skip.Exception:
        report["state"] = "environment-blocked"
        raise
    except BaseException as exc:
        report["state"] = "failure"
        report["failure_type"] = type(exc).__name__
        raise
    finally:
        _finalize_benchmark_report(report)
        report["restoration"] = await _word_restoration_status(live_word)
        _write_benchmark_report(WORD_ACTION_ID, report)

