"""Public MCP-Action service envelopes (spec 047, T005/T037).

The Windows-MCP and OfficeMCP trust boundaries are mocked. Default-printer and
Word-duplex tests share the consent, desktop serialization, evidence, privacy,
and honest-partial-result contracts without touching a live host.
"""

from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import agentic_rag_mcp.mcp_action.actions as actions_mod
import agentic_rag_mcp.mcp_action.service as service_mod
from agentic_rag_mcp.mcp_action.screenshots import ScreenshotStore
from agentic_rag_mcp.mcp_action.service import McpActionService
from agentic_rag_mcp.mcp_action.state import ProposalStore
from agentic_rag_mcp.office_lanes.proxy import OfficeProxy
from agentic_rag_mcp.windows_mcp import client as windows_client
from agentic_rag_mcp.windows_mcp.client import CapturedImage
from agentic_rag_mcp.windows_mcp.targets import TARGETS

PRINTER = "Microsoft Print to PDF"
OFFER = "Do you want me to do it automatically for you?"
EFFECT = (
    "Change your default printer to Microsoft Print to PDF, "
    "then open Windows printer settings to show the result."
)


@pytest.fixture
def host_effects(monkeypatch):
    windows = AsyncMock(side_effect=AssertionError("unexpected Windows host call"))
    office = Mock(side_effect=AssertionError("unexpected Office host call"))
    monkeypatch.setattr(windows_client, "call_tool", windows)
    # Also cover direct imports made by the feature modules.
    monkeypatch.setattr(actions_mod, "call_tool", windows, raising=False)
    monkeypatch.setattr(service_mod, "call_tool", windows, raising=False)
    monkeypatch.setattr(OfficeProxy, "call", office)
    return windows, office


@pytest.fixture
def service_and_store(host_effects):
    store = ProposalStore()
    return McpActionService(store=store), store


def _assert_no_host_effects(host_effects):
    windows, office = host_effects
    windows.assert_not_called()
    office.assert_not_called()


async def _draft(service, conversation_id="c1"):
    return await service.handle(
        phase="draft",
        conversation_id=conversation_id,
        dialogue_count=4,
        action_id="windows_default_printer",
        parameters={"printer": PRINTER},
    )


@pytest.mark.asyncio
async def test_default_printer_draft_stores_one_exact_proposal_without_host_effects(
    service_and_store, host_effects
):
    service, store = service_and_store

    out = await _draft(service)

    assert out["status"] == "pending-confirmation"
    assert out["action_id"] == "windows_default_printer"
    assert out["effect"] == EFFECT
    assert out["offer"] == OFFER
    assert out["expires_in_s"] == 900
    assert out["caveats"] == []

    # Public store behavior proves one executable proposal, not merely an offer string.
    reserved = store.resolve("c1", 5, "yes")
    assert reserved.status == "reserved"
    assert reserved.proposal.action_id == "windows_default_printer"
    assert reserved.proposal.parameters == {"printer": PRINTER}
    assert reserved.proposal.effect == EFFECT
    assert reserved.proposal.created_dialogue_count == 4
    assert store.resolve("c1", 5, "yes").status == "blocked"
    _assert_no_host_effects(host_effects)


@pytest.mark.asyncio
async def test_plain_yes_draft_with_pending_returns_confirm_hint_and_keeps_proposal(
    service_and_store, host_effects
):
    service, store = service_and_store
    await _draft(service)

    out = await service.handle(
        phase="draft",
        conversation_id="c1",
        dialogue_count=5,
        query="yes, help to do it",
        action_id="windows_default_printer",
        parameters={"printer": PRINTER},
    )

    assert out["status"] == "blocked"
    assert "phase='confirm'" in out["reason"]
    reserved = store.resolve("c1", 5, "yes, help to do it")
    assert reserved.status == "reserved"
    assert reserved.proposal.parameters == {"printer": PRINTER}
    _assert_no_host_effects(host_effects)


@pytest.mark.parametrize(
    ("action_id", "parameters", "status"),
    [
        ("", {"printer": PRINTER}, "ask-back"),
        ("windows_default_printer", {}, "ask-back"),
        ("word_printer_duplex", {"printer": PRINTER}, "ask-back"),
        ("excel_change_setting", {"printer": PRINTER}, "unsupported"),
        ("run_powershell", {"command": "whoami"}, "unsupported"),
        ("windows_default_printer", {"printer": PRINTER, "command": "whoami"}, "error"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_drafts_have_no_offer_proposal_or_host_effects(
    service_and_store, host_effects, action_id, parameters, status
):
    service, store = service_and_store

    out = await service.handle(
        phase="draft",
        conversation_id="c1",
        dialogue_count=4,
        action_id=action_id,
        parameters=parameters,
    )

    assert out["status"] == status
    assert "offer" not in out
    assert store.resolve("c1", 5, "yes").status == "blocked"
    _assert_no_host_effects(host_effects)


@pytest.mark.asyncio
async def test_unknown_phase_is_a_bounded_error_without_host_effects(
    service_and_store, host_effects
):
    service, store = service_and_store

    out = await service.handle(
        phase="execute",
        conversation_id="c1",
        dialogue_count=4,
        action_id="windows_default_printer",
        parameters={"printer": PRINTER},
    )

    assert out["status"] == "error"
    assert "offer" not in out
    assert store.resolve("c1", 5, "yes").status == "blocked"
    _assert_no_host_effects(host_effects)


@pytest.mark.asyncio
async def test_next_turn_cancel_consumes_proposal_without_host_effects(
    service_and_store, host_effects
):
    service, store = service_and_store
    assert (await _draft(service))["status"] == "pending-confirmation"

    out = await service.handle(
        phase="cancel", conversation_id="c1", dialogue_count=5, query="no"
    )

    assert out == {"status": "cancelled", "reason": "No automatic action was performed."}
    assert store.resolve("c1", 5, "yes").status == "blocked"
    _assert_no_host_effects(host_effects)


@pytest.mark.parametrize("phase", ["confirm", "cancel"])
@pytest.mark.parametrize(
    ("field", "value"),
    [("action_id", "word_printer_duplex"), ("parameters", {"printer": "Other Printer"})],
)
@pytest.mark.asyncio
async def test_confirm_and_cancel_reject_replacement_action_fields(
    service_and_store, host_effects, phase, field, value
):
    service, _store = service_and_store
    assert (await _draft(service))["status"] == "pending-confirmation"

    out = await service.handle(
        phase=phase,
        conversation_id="c1",
        dialogue_count=5,
        query="yes" if phase == "confirm" else "no",
        **{field: value},
    )

    assert out["status"] == "error"
    assert field in out["reason"]
    _assert_no_host_effects(host_effects)


@pytest.mark.asyncio
async def test_unexpected_exception_is_sanitized_and_bounded(
    service_and_store, host_effects, monkeypatch
):
    service, store = service_and_store

    def explode(*args, **kwargs):
        raise RuntimeError(r"C:\Users\alice\secret.ps1 --token super-secret")

    monkeypatch.setattr(store, "create", explode)

    out = await _draft(service)

    assert out["status"] == "error"
    assert "offer" not in out
    serialized = json.dumps(out)
    assert "super-secret" not in serialized
    assert "secret.ps1" not in serialized
    assert "C:\\Users" not in serialized
    assert len(out.get("reason", "")) <= 500
    _assert_no_host_effects(host_effects)


@pytest.mark.asyncio
async def test_confirm_before_live_gate_is_blocked_without_execution(
    service_and_store, host_effects
):
    service, _store = service_and_store
    assert (await _draft(service))["status"] == "pending-confirmation"

    out = await service.handle(
        phase="confirm", conversation_id="c1", dialogue_count=5, query="yes"
    )

    assert out["status"] == "blocked"
    assert out.get("changed") is not True
    assert "screenshot" not in out
    _assert_no_host_effects(host_effects)


PNG_BYTES = b"\x89PNG\r\n\x1a\n"
CAPTURE_USAGE = (
    "Inline this temporary image once as ![Verification screenshot](<image_url>)."
)


def test_printers_is_a_reviewed_settings_page_target():
    assert TARGETS["printers"] == {
        "kind": "settings_page",
        "identifier": "printers",
    }


@pytest.mark.asyncio
async def test_windows_display_opens_waits_and_verifies_printer_page(monkeypatch):
    opened = AsyncMock(return_value={"status": "ok"})
    waitfor = AsyncMock(
        return_value={
            "status": "ok",
            "text": (
                "WaitFor condition 'text_exists' satisfied: "
                "text 'Printers & scanners' appeared."
            ),
        }
    )
    audit = Mock()
    monkeypatch.setattr(service_mod, "open_settings", opened, raising=False)
    monkeypatch.setattr(service_mod, "call_tool", waitfor, raising=False)

    out = await service_mod.WindowsDisplay(audit=audit).show_default_printer("c1")

    assert out == {"status": "displayed"}
    opened.assert_awaited_once_with("printers", "c1", audit)
    waitfor.assert_awaited_once_with(
        "WaitFor",
        {
            "condition": "text",
            "text": "Printers & scanners",
            "window_name": "Settings",
            "timeout": 30,
            "interval": 0.5,
            "use_dom": False,
        },
        "c1",
        audit,
    )


@pytest.mark.asyncio
async def test_windows_display_open_failure_is_sanitized_and_skips_snapshot(monkeypatch):
    opened = AsyncMock(
        return_value={
            "status": "error",
            "reason": r"C:\Users\alice\secret.txt raw desktop text",
        }
    )
    waitfor = AsyncMock()
    monkeypatch.setattr(service_mod, "open_settings", opened, raising=False)
    monkeypatch.setattr(service_mod, "call_tool", waitfor, raising=False)

    out = await service_mod.WindowsDisplay().show_default_printer("c1")

    assert out["status"] == "attempted-but-failed"
    assert "secret.txt" not in json.dumps(out)
    assert "raw desktop text" not in json.dumps(out)
    waitfor.assert_not_awaited()


@pytest.mark.asyncio
async def test_windows_display_missing_printer_markers_is_unverified(monkeypatch):
    opened = AsyncMock(return_value={"status": "ok"})
    waitfor = AsyncMock(
        return_value={"status": "error", "text": "Settings Home\nPrivate desktop text"}
    )
    monkeypatch.setattr(service_mod, "open_settings", opened, raising=False)
    monkeypatch.setattr(service_mod, "call_tool", waitfor, raising=False)

    out = await service_mod.WindowsDisplay().show_default_printer("c1")

    assert out == {
        "status": "unverified",
        "reason": "The Windows printer settings page could not be verified.",
    }
    assert "Private desktop text" not in json.dumps(out)


@pytest.mark.asyncio
async def test_screenshot_capture_uses_shared_store_and_returns_only_public_metadata(
    monkeypatch, tmp_path
):
    store = ScreenshotStore(
        root=tmp_path / "screenshots",
        public_base_url="https://example.test/mcp-action/screenshots",
    )
    shared_store = Mock(return_value=store)
    captured = CapturedImage(data=PNG_BYTES, mime_type="image/png")
    audit = Mock()
    host_call = AsyncMock(
        return_value={
            "status": "ok",
            "text": "Private desktop text",
            "images": [captured],
        }
    )
    monkeypatch.setattr(service_mod, "get_screenshot_store", shared_store, raising=False)
    monkeypatch.setattr(service_mod, "call_tool", host_call, raising=False)

    out = await service_mod.ScreenshotCapture(audit=audit).capture("c1")

    assert out == {
        "status": "captured",
        "capture_scope": "full-display",
        "image_url": out["image_url"],
        "expires_in_s": 900,
        "usage": CAPTURE_USAGE,
    }
    assert out["image_url"].startswith(
        "https://example.test/mcp-action/screenshots/"
    )
    token = out["image_url"].rsplit("/", 1)[1]
    resolved = store.resolve(token)
    assert resolved is not None and resolved.data == PNG_BYTES
    shared_store.assert_called_once_with()
    assert host_call.await_count == 2
    host_call.assert_awaited_with(
        "Screenshot",
        {},
        "c1",
        audit,
        include_images=True,
        consent_attempts=4,
    )
    serialized = json.dumps(out)
    assert "Private desktop text" not in serialized
    assert str(tmp_path) not in serialized
    assert base64.b64encode(PNG_BYTES).decode("ascii") not in serialized


@pytest.mark.asyncio
async def test_screenshot_capture_uses_foreground_region_when_bounds_are_available(
    monkeypatch,
):
    captured = CapturedImage(data=PNG_BYTES, mime_type="image/png")
    marker_payload = base64.b64encode(
        json.dumps({"region": [10, 20, 200, 300]}).encode("utf-8")
    ).decode("ascii")
    host_call = AsyncMock(
        side_effect=[
            {"status": "ok", "text": f"MCP_ACTION_JSON:{marker_payload}"},
            {"status": "ok", "images": [captured]},
        ]
    )
    store = Mock()
    store.save.return_value = SimpleNamespace(
        image_url="https://example.test/mcp-action/screenshots/token",
        mime="image/png",
        expires=900,
    )
    monkeypatch.setattr(service_mod, "call_tool", host_call, raising=False)

    out = await service_mod.ScreenshotCapture(store=store).capture("c1")

    assert out["status"] == "captured"
    assert out["capture_scope"] == "foreground-window"
    assert host_call.await_args_list[0].args[0] == "PowerShell"
    assert host_call.await_args_list[1].args[:2] == (
        "Screenshot",
        {"region": [10, 20, 200, 300]},
    )


@pytest.mark.asyncio
async def test_screenshot_region_failure_falls_back_to_full_display(monkeypatch):
    captured = CapturedImage(data=PNG_BYTES, mime_type="image/png")
    marker_payload = base64.b64encode(
        json.dumps({"region": [10, 20, 200, 300]}).encode("utf-8")
    ).decode("ascii")
    host_call = AsyncMock(
        side_effect=[
            {"status": "ok", "text": f"MCP_ACTION_JSON:{marker_payload}"},
            {"status": "error", "reason": "private regional failure"},
            {"status": "ok", "images": [captured]},
        ]
    )
    store = Mock()
    store.save.return_value = SimpleNamespace(
        image_url="https://example.test/mcp-action/screenshots/token",
        mime="image/png",
        expires=900,
    )
    monkeypatch.setattr(service_mod, "call_tool", host_call, raising=False)

    out = await service_mod.ScreenshotCapture(store=store).capture("c1")

    assert out["status"] == "captured"
    assert out["capture_scope"] == "full-display"
    assert out["region_fallback"] == "region-capture-failed"
    assert host_call.await_args_list[-1].args[:2] == ("Screenshot", {})
    assert "private regional failure" not in json.dumps(out)


@pytest.mark.asyncio
async def test_screenshot_invalid_bounds_fall_back_to_full_display(monkeypatch):
    captured = CapturedImage(data=PNG_BYTES, mime_type="image/png")
    marker_payload = base64.b64encode(
        json.dumps({"region": [0, 0, 0, 0]}).encode("utf-8")
    ).decode("ascii")
    host_call = AsyncMock(
        side_effect=[
            {"status": "ok", "text": f"MCP_ACTION_JSON:{marker_payload}"},
            {"status": "ok", "images": [captured]},
        ]
    )
    store = Mock()
    store.save.return_value = SimpleNamespace(
        image_url="https://example.test/mcp-action/screenshots/token",
        mime="image/png",
        expires=900,
    )
    monkeypatch.setattr(service_mod, "call_tool", host_call, raising=False)

    out = await service_mod.ScreenshotCapture(store=store).capture("c1")

    assert out["status"] == "captured"
    assert out["capture_scope"] == "full-display"
    assert host_call.await_args_list[-1].args[:2] == ("Screenshot", {})


@pytest.mark.parametrize("images", [[], [CapturedImage(PNG_BYTES, "image/png")] * 2])
@pytest.mark.asyncio
async def test_screenshot_capture_requires_exactly_one_captured_image(
    monkeypatch, images
):
    store = Mock()
    host_call = AsyncMock(return_value={"status": "ok", "images": images})
    monkeypatch.setattr(service_mod, "call_tool", host_call, raising=False)

    out = await service_mod.ScreenshotCapture(store=store).capture("c1")

    assert out["status"] == "attempted-but-failed"
    assert "image_url" not in out
    store.save.assert_not_called()


@pytest.mark.asyncio
async def test_screenshot_store_failure_is_sanitized(monkeypatch, tmp_path):
    secret_path = str(tmp_path / "private" / "screenshot.png")
    store = Mock()
    store.save.side_effect = RuntimeError(f"{secret_path} secret-store-error")
    host_call = AsyncMock(
        return_value={
            "status": "ok",
            "images": [CapturedImage(PNG_BYTES, "image/png")],
        }
    )
    monkeypatch.setattr(service_mod, "call_tool", host_call, raising=False)

    out = await service_mod.ScreenshotCapture(store=store).capture("c1")

    assert out["status"] == "attempted-but-failed"
    serialized = json.dumps(out)
    assert secret_path not in serialized
    assert "secret-store-error" not in serialized
    assert "image_url" not in out
    assert base64.b64encode(PNG_BYTES).decode("ascii") not in serialized


@pytest.mark.asyncio
async def test_screenshot_transport_failure_is_sanitized(monkeypatch):
    host_call = AsyncMock(
        return_value={
            "status": "error",
            "reason": "Raw desktop text, document name, and C:\\private\\shot.png",
        }
    )
    store = Mock()
    monkeypatch.setattr(service_mod, "call_tool", host_call, raising=False)

    out = await service_mod.ScreenshotCapture(store=store).capture("c1")

    assert out == {
        "status": "attempted-but-failed",
        "capture_scope": "full-display",
        "reason": "Screenshot capture or storage failed.",
    }
    store.save.assert_not_called()


WORD_ACTION = "word_printer_duplex"
DOCUMENT_NAME = "Confidential Quarterly Report.docx"
PRIVATE_PATH = r"C:\Users\alice\Confidential Quarterly Report.docx"


class _FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _duplex_result(printer, orientation):
    mode = {
        "long-edge": "TwoSidedLongEdge",
        "short-edge": "TwoSidedShortEdge",
    }[orientation]
    return {
        "status": "ok",
        "action_id": WORD_ACTION,
        "changed": True,
        "before": {"duplex": "OneSided"},
        "after": {"duplex": mode},
        "printer": printer,
        "orientation": orientation,
        "requested_duplex": mode,
        "verification": "verified",
        "caveats": [],
    }


class _FakeWordActions:
    def __init__(self, clock, trace):
        self.clock = clock
        self.trace = trace
        self.validate_calls = []
        self.execute_calls = []
        self.validation_error = None
        self.execution_error = None
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.gate_first = False
        self.active = 0
        self.max_active = 0

    async def validate_word_printer_duplex(self, printer, orientation):
        self.validate_calls.append((printer, orientation))
        if self.validation_error is not None:
            raise self.validation_error
        return {
            "status": "ok",
            "printer": printer,
            "match_count": 1,
            "caveats": [],
        }

    async def execute_word_printer_duplex(self, printer, orientation):
        self.execute_calls.append((printer, orientation))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.trace.append(f"execute-start:{printer}")
        try:
            if len(self.execute_calls) == 1:
                self.started.set()
                if self.gate_first:
                    await self.release.wait()
            if self.execution_error is not None:
                raise self.execution_error
            return _duplex_result(printer, orientation)
        finally:
            self.active -= 1
            self.trace.append(f"execute-settled:{printer}")


class _FakeWordDisplay:
    """Synchronous OfficeProxy.show_word_print-shaped test boundary."""

    def __init__(self, clock, trace):
        self.clock = clock
        self.trace = trace
        self.calls = []
        self.thread_ids = []
        self.error = None
        self.block = False
        self.started = threading.Event()
        self.release = threading.Event()
        self.outcome = {
            "status": "ok",
            "preview_ok": True,
            "view_type": 4,
            "visible": True,
            "foreground": True,
            "blank_created": False,
            "document_count": 1,
            "count_ok": True,
            "saved_ok": True,
            "documents_preserved": True,
        }

    def show_word_print(self):
        self.calls.append(())
        self.thread_ids.append(threading.get_ident())
        self.trace.append("display")
        if self.block:
            self.started.set()
            if not self.release.wait(timeout=2.0):
                raise TimeoutError("test display was not released")
        if self.error is not None:
            raise self.error
        return deepcopy(self.outcome)


class _FakeWordScreenshots:
    def __init__(self, clock, trace):
        self.clock = clock
        self.trace = trace
        self.calls = []
        self.outcome = {
            "status": "captured",
            "image_url": "https://example.test/mcp-action/screenshots/word-token",
            "expires_in_s": 900,
            "usage": CAPTURE_USAGE,
        }

    async def capture(self, conversation_id):
        self.calls.append(conversation_id)
        self.trace.append(f"capture:{conversation_id}")
        return deepcopy(self.outcome)


@pytest.fixture
def word_harness(host_effects):
    clock = _FakeClock()
    trace = []
    actions = _FakeWordActions(clock, trace)
    display = _FakeWordDisplay(clock, trace)
    screenshots = _FakeWordScreenshots(clock, trace)
    audit = Mock()
    service = McpActionService(
        store=ProposalStore(clock=clock),
        actions=actions,
        display=display,
        screenshots=screenshots,
        audit=audit,
        clock=clock,
    )
    return SimpleNamespace(
        service=service,
        actions=actions,
        display=display,
        screenshots=screenshots,
        audit=audit,
        clock=clock,
        trace=trace,
        host_effects=host_effects,
    )


async def _word_draft(harness, conversation_id="c1", printer=PRINTER):
    return await harness.service.handle(
        phase="draft",
        conversation_id=conversation_id,
        dialogue_count=4,
        action_id=WORD_ACTION,
        parameters={"printer": printer, "orientation": "long-edge"},
    )


async def _word_confirm(harness, conversation_id="c1"):
    return await harness.service.handle(
        phase="confirm",
        conversation_id=conversation_id,
        dialogue_count=5,
        query="yes",
    )


async def _wait_thread_event(event):
    while not event.is_set():
        await asyncio.sleep(0.005)


def _assert_word_privacy(harness, result):
    serialized = json.dumps(result)
    audit_serialized = json.dumps(
        [call.kwargs for call in harness.audit.write_attempt.call_args_list]
    )
    for secret in (DOCUMENT_NAME, PRIVATE_PATH, "super-secret", "raw desktop text"):
        assert secret not in serialized
        assert secret not in audit_serialized


@pytest.mark.asyncio
async def test_word_draft_discloses_scope_orientation_and_blank_document(
    word_harness,
):
    h = word_harness

    out = await _word_draft(h)

    assert out["status"] == "pending-confirmation"
    assert out["action_id"] == WORD_ACTION
    assert out["offer"] == OFFER
    effect = out["effect"]
    assert PRINTER in effect
    assert "long-edge" in effect
    assert "printer-wide" in effect
    assert "outside the current Word document" in effect
    assert "blank unsaved document" in effect
    assert "solely to show Print Preview" in effect
    assert h.actions.validate_calls == [(PRINTER, "long-edge")]
    assert h.actions.execute_calls == []
    assert h.display.calls == []
    assert h.screenshots.calls == []

    reserved = h.service.store.resolve("c1", 5, "yes")
    assert reserved.status == "reserved"
    assert reserved.proposal.parameters == {
        "printer": PRINTER,
        "orientation": "long-edge",
    }
    assert h.service.store.resolve("c1", 5, "yes").status == "blocked"
    _assert_no_host_effects(h.host_effects)


@pytest.mark.asyncio
async def test_word_validation_exception_is_sanitized_without_a_proposal(
    word_harness,
):
    h = word_harness
    h.actions.validation_error = RuntimeError(
        f"{PRIVATE_PATH} super-secret raw desktop text"
    )

    out = await _word_draft(h)

    assert out["status"] == "error"
    assert "offer" not in out
    assert len(out["reason"]) <= 500
    _assert_word_privacy(h, out)
    assert h.service.store.resolve("c1", 5, "yes").status == "blocked"
    assert h.actions.execute_calls == []
    assert h.display.calls == []
    assert h.screenshots.calls == []
    _assert_no_host_effects(h.host_effects)


@pytest.mark.asyncio
async def test_word_verified_preview_and_screenshot_return_ok(word_harness):
    h = word_harness
    h.display.outcome["blank_created"] = True
    h.display.outcome["document_count"] = 1
    assert (await _word_draft(h))["status"] == "pending-confirmation"

    out = await _word_confirm(h)

    assert out["status"] == "ok"
    assert out["action_id"] == WORD_ACTION
    assert out["changed"] is True
    assert out["before"] == {"duplex": "OneSided"}
    assert out["after"] == {"duplex": "TwoSidedLongEdge"}
    assert out["verification"] == "verified"
    assert out["orientation"] == "long-edge"
    assert out["requested_duplex"] == "TwoSidedLongEdge"
    assert out["display"]["status"] == "displayed"
    assert out["display"]["preview_ok"] is True
    assert out["display"]["foreground"] is True
    assert out["display"]["blank_created"] is True
    assert out["display"]["documents_preserved"] is True
    assert out["screenshot"] == h.screenshots.outcome
    assert h.actions.execute_calls == [(PRINTER, "long-edge")]
    assert len(h.display.calls) == 1
    assert h.screenshots.calls == ["c1"]
    _assert_no_host_effects(h.host_effects)


@pytest.mark.parametrize("obstacle", ["busy", "modal", "timeout"])
@pytest.mark.asyncio
async def test_word_busy_modal_and_timeout_are_partial_without_gui_fallback(
    word_harness, obstacle
):
    h = word_harness
    detail = f"{obstacle}: {PRIVATE_PATH}; super-secret; raw desktop text"
    if obstacle == "timeout":
        h.display.error = TimeoutError(detail)
    else:
        h.display.outcome = {"status": "error", "reason": detail}
    assert (await _word_draft(h))["status"] == "pending-confirmation"

    out = await _word_confirm(h)

    assert out["status"] == "partial"
    assert out["changed"] is True
    assert out["verification"] == "verified"
    assert out["display"]["status"] == "attempted-but-failed"
    assert out["screenshot"] == {"status": "skipped-display-unverified"}
    assert len(h.display.calls) == 1
    assert h.screenshots.calls == []
    _assert_word_privacy(h, out)
    _assert_no_host_effects(h.host_effects)


@pytest.mark.parametrize(
    ("display_delta", "display_status"),
    [
        (
            {"preview_ok": False, "view_type": None, "visible": False, "foreground": False},
            "unverified",
        ),
        ({"foreground": False}, "partial"),
    ],
)
@pytest.mark.asyncio
async def test_word_preview_or_foreground_failure_is_partial_and_skips_screenshot(
    word_harness, display_delta, display_status, monkeypatch
):
    h = word_harness
    h.display.outcome.update(display_delta)
    monkeypatch.setattr(
        service_mod,
        "call_tool",
        AsyncMock(return_value={"status": "error", "reason": "switch unavailable"}),
        raising=False,
    )
    assert (await _word_draft(h))["status"] == "pending-confirmation"

    out = await _word_confirm(h)

    assert out["status"] == "partial"
    assert out["changed"] is True
    assert out["verification"] == "verified"
    assert out["display"]["status"] == display_status
    assert out["display"]["preview_ok"] is display_delta.get("preview_ok", True)
    assert out["display"]["foreground"] is display_delta["foreground"]
    assert out["screenshot"] == {"status": "skipped-display-unverified"}
    assert h.screenshots.calls == []
    _assert_no_host_effects(h.host_effects)


@pytest.mark.asyncio
async def test_word_foreground_switch_revalidates_display_before_capture(
    word_harness, monkeypatch
):
    h = word_harness
    first = deepcopy(h.display.outcome)
    first["foreground"] = False
    second = deepcopy(h.display.outcome)
    h.display.show_word_print = Mock(side_effect=[first, second])
    app_switch = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(service_mod, "call_tool", app_switch, raising=False)
    await _word_draft(h)

    out = await _word_confirm(h)

    assert out["status"] == "ok"
    assert out["display"]["status"] == "displayed"
    assert out["display"]["foreground"] is True
    assert out["screenshot"]["status"] == "captured"
    app_switch.assert_awaited_once_with(
        "App", {"mode": "switch", "name": "WINWORD.EXE"}, "c1", h.audit
    )
    assert h.display.show_word_print.call_count == 2


@pytest.mark.parametrize(
    ("queued_seconds", "expected_status"),
    [(150.0, "ok"), (150.01, "queued-timeout")],
)
@pytest.mark.asyncio
async def test_word_lock_reserves_90_seconds_leaving_only_150_seconds_to_queue(
    word_harness, queued_seconds, expected_status
):
    h = word_harness
    h.actions.gate_first = True
    other_printer = "Second Test Printer"
    assert (await _word_draft(h, "c1"))["status"] == "pending-confirmation"
    assert (await _word_draft(h, "c2", other_printer))["status"] == (
        "pending-confirmation"
    )

    first = asyncio.create_task(_word_confirm(h, "c1"))
    second = None
    try:
        await asyncio.wait_for(h.actions.started.wait(), timeout=1)
        second = asyncio.create_task(_word_confirm(h, "c2"))
        await asyncio.sleep(0)
        h.clock.advance(queued_seconds)
    finally:
        h.actions.release.set()

    first_result, second_result = await asyncio.wait_for(
        asyncio.gather(first, second), timeout=1
    )

    assert first_result["status"] == "ok"
    assert second_result["status"] == expected_status
    assert second_result["timing"]["queue_wait_s"] == pytest.approx(queued_seconds)
    assert h.actions.max_active == 1
    if expected_status == "ok":
        assert h.actions.execute_calls == [
            (PRINTER, "long-edge"),
            (other_printer, "long-edge"),
        ]
        assert h.trace.index("capture:c1") < h.trace.index(
            f"execute-start:{other_printer}"
        )
    else:
        assert h.actions.execute_calls == [(PRINTER, "long-edge")]
        assert h.screenshots.calls == ["c1"]
        assert second_result["changed"] is False
        assert second_result["verification"] == "not-run"
        assert second_result["display"] == {"status": "skipped"}
        assert second_result["screenshot"] == {"status": "skipped"}
        assert second_result["timing"]["execution_s"] == 0.0


@pytest.mark.asyncio
async def test_word_sync_office_helper_runs_off_the_event_loop(
    word_harness, monkeypatch
):
    h = word_harness
    to_thread = AsyncMock(wraps=asyncio.to_thread)
    monkeypatch.setattr(service_mod.asyncio, "to_thread", to_thread)
    h.display.block = True
    assert (await _word_draft(h))["status"] == "pending-confirmation"

    confirmed = asyncio.create_task(_word_confirm(h))
    started_waiting = time.monotonic()
    try:
        await asyncio.wait_for(_wait_thread_event(h.display.started), timeout=1)
        startup_delay = time.monotonic() - started_waiting
        heartbeat_started = time.monotonic()
        await asyncio.wait_for(asyncio.sleep(0.01), timeout=0.2)
        heartbeat_delay = time.monotonic() - heartbeat_started
    finally:
        h.display.release.set()
    out = await asyncio.wait_for(confirmed, timeout=1)

    assert startup_delay < 1.0
    assert heartbeat_delay < 0.2
    assert out["status"] == "ok"
    to_thread.assert_awaited_once_with(h.display.show_word_print)
    assert h.display.thread_ids
    assert h.display.thread_ids[0] != threading.get_ident()
    assert h.screenshots.calls == ["c1"]


@pytest.mark.asyncio
async def test_word_transport_failure_is_sanitized_and_not_retried(word_harness):
    h = word_harness
    h.actions.execution_error = TimeoutError(
        f"mutation outcome unknown for {PRIVATE_PATH}; super-secret"
    )
    assert (await _word_draft(h))["status"] == "pending-confirmation"

    out = await _word_confirm(h)

    assert out["status"] == "error"
    assert out["changed"] is False
    assert out["verification"] == "unavailable"
    assert out["display"] == {"status": "skipped"}
    assert out["screenshot"] == {"status": "skipped"}
    assert h.actions.execute_calls == [(PRINTER, "long-edge")]
    assert h.display.calls == []
    assert h.screenshots.calls == []
    _assert_word_privacy(h, out)
    _assert_no_host_effects(h.host_effects)
    assert (await _word_confirm(h))["status"] == "blocked"
    assert h.actions.execute_calls == [(PRINTER, "long-edge")]


@pytest.mark.asyncio
async def test_word_screenshot_failure_is_partial_sanitized_and_audited(
    word_harness,
):
    h = word_harness
    h.screenshots.outcome = {
        "status": "attempted-but-failed",
        "reason": f"{PRIVATE_PATH}; super-secret; raw desktop text; " + "x" * 1000,
    }
    assert (await _word_draft(h))["status"] == "pending-confirmation"

    out = await _word_confirm(h)

    assert out["status"] == "partial"
    assert out["verification"] == "verified"
    assert out["display"]["status"] == "displayed"
    assert out["screenshot"]["status"] == "attempted-but-failed"
    assert len(out["screenshot"]["reason"]) <= 500
    assert "image_url" not in out["screenshot"]
    assert h.screenshots.calls == ["c1"]
    _assert_word_privacy(h, out)
    assert h.audit.write_attempt.call_count == 2


@pytest.mark.asyncio
async def test_audit_contains_stage_outcomes_and_timings_without_sensitive_values(
    word_harness,
):
    h = word_harness
    await _word_draft(h)
    out = await _word_confirm(h)

    assert out["status"] == "ok"
    assert isinstance(out["timing"]["display_s"], (int, float))
    assert isinstance(out["timing"]["screenshot_s"], (int, float))
    row = h.audit.write_attempt.call_args_list[-1].kwargs
    assert row["outcome"] == (
        "word_printer_duplex:ok:verification=verified:display=displayed:screenshot=captured"
    )
    assert isinstance(row["timing"]["display_s"], (int, float))
    assert isinstance(row["timing"]["screenshot_s"], (int, float))
    serialized = json.dumps([call.kwargs for call in h.audit.write_attempt.call_args_list])
    assert "word-token" not in serialized
    assert "https://example.test" not in serialized
    _assert_word_privacy(h, out)


@pytest.mark.asyncio
async def test_partial_display_audit_records_display_time_and_capture_skip(
    word_harness,
):
    h = word_harness
    h.display.outcome["foreground"] = False
    await _word_draft(h)
    out = await _word_confirm(h)

    assert out["status"] == "partial"
    assert isinstance(out["timing"]["display_s"], (int, float))
    assert out["timing"]["screenshot_s"] is None
    row = h.audit.write_attempt.call_args_list[-1].kwargs
    assert row["outcome"] == (
        "word_printer_duplex:partial:verification=verified:display=partial:screenshot=skipped-display-unverified"
    )
    assert isinstance(row["timing"]["display_s"], (int, float))
    assert row["timing"]["screenshot_s"] is None
    assert h.screenshots.calls == []


@pytest.mark.asyncio
async def test_validation_error_audit_marks_all_stages_not_attempted(word_harness):
    h = word_harness
    h.actions.validation_error = RuntimeError("private host text")
    out = await _word_draft(h)

    assert out["status"] == "error"
    row = h.audit.write_attempt.call_args_list[-1].kwargs
    assert row["outcome"] == (
        "error:verification=not-attempted:display=not-attempted:screenshot=not-attempted"
    )
    assert row["timing"] is None
    assert "private host text" not in json.dumps(row)


HEALTH_ACTION = "system_health_check"
HEALTH_EFFECT = (
    "Run a read-only desktop health check, publish a temporary report, and display "
    "Reliability Monitor. The check does not repair or change the system; HelpDesk "
    "can help with repairs."
)
HEALTH_REPORT_URL = (
    "http://sidecar:8080/mcp-action/reports/" + "R" * 43
)
HEALTH_FORGED_REPORT_URL = (
    "http://evil.example/mcp-action/reports/" + "F" * 43
)
HEALTH_SCREENSHOT_URL = (
    "https://example.test/mcp-action/screenshots/" + "S" * 43
)
HEALTH_COUNTS = {"pass": 8, "warn": 3, "fail": 1, "info": 2, "skip": 2}
HEALTH_REPORT_HTML = (
    "<!DOCTYPE html><html><head><title>System health</title></head><body>"
    "<p>User: TEST\\user</p><p>Email: user@example.test</p>"
    "<p>IP: 10.0.0.10</p><p>Serial: SN-SECRET</p>"
    "<p>Crash: app.exe</p></body></html>"
)
_HEALTH_OMITTED = object()


def _health_action_result(
    health_status: str = "warn", score: int = 72, confidence: str = "reduced"
) -> dict:
    return {
        "status": "ok",
        "health": {
            "status": health_status,
            "score": score,
            "counts": dict(HEALTH_COUNTS),
            "confidence": confidence,
        },
        "report_html": HEALTH_REPORT_HTML,
        "report_file": {
            "path": r"C:\Users\Test\AppData\Local\Temp\selfcheck.html",
            "status": "written",
        },
        "helpdesk": (
            "Disk and Reliability need review; HelpDesk can help with repairs."
        ),
        "remediation": ["Disk", "Reliability"],
    }


class _FakeHealthActions:
    def __init__(self, clock, trace):
        self.clock = clock
        self.trace = trace
        self.calls = 0
        self.outcome = _health_action_result()
        self.error = None
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.gate_first = False
        self.advance_s = 0.0
        self.active = 0
        self.max_active = 0

    async def execute_system_health_check(self):
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.trace.append("execute")
        try:
            if self.gate_first and self.calls == 1:
                self.started.set()
                await self.release.wait()
            if self.advance_s:
                self.clock.advance(self.advance_s)
            if self.error is not None:
                raise self.error
            return deepcopy(self.outcome)
        finally:
            self.active -= 1


class _FakeHealthReports:
    def __init__(self, trace):
        self.trace = trace
        self.calls = []
        self.outcome = {
            "status": "published",
            "report_url": HEALTH_REPORT_URL,
            "expires_in_s": 900,
        }
        self.error = None

    def publish(self, html: str) -> dict:
        self.calls.append(html)
        self.trace.append("report")
        if self.error is not None:
            raise self.error
        return deepcopy(self.outcome)


class _FakeHealthDisplay:
    def __init__(self, clock, trace):
        self.clock = clock
        self.trace = trace
        self.calls = []
        self.outcome = {"status": "displayed"}
        self.error = None
        self.advance_s = 0.0

    async def show_reliability_monitor(self, conversation_id: str) -> dict:
        self.calls.append(conversation_id)
        self.trace.append("display")
        if self.advance_s:
            self.clock.advance(self.advance_s)
        if self.error is not None:
            raise self.error
        return deepcopy(self.outcome)


class _FakeHealthScreenshots:
    def __init__(self, trace):
        self.trace = trace
        self.calls = []
        self.outcome = {
            "status": "captured",
            "capture_scope": "foreground-window",
            "image_url": HEALTH_SCREENSHOT_URL,
            "expires_in_s": 900,
        }
        self.error = None

    async def capture(self, conversation_id: str) -> dict:
        self.calls.append(conversation_id)
        self.trace.append("screenshot")
        if self.error is not None:
            raise self.error
        return deepcopy(self.outcome)


@pytest.fixture
def health_harness(host_effects):
    clock = _FakeClock()
    trace = []
    actions = _FakeHealthActions(clock, trace)
    display = _FakeHealthDisplay(clock, trace)
    screenshots = _FakeHealthScreenshots(trace)
    reports = _FakeHealthReports(trace)
    audit = Mock()
    service = McpActionService(
        store=ProposalStore(clock=clock),
        actions=actions,
        display=display,
        screenshots=screenshots,
        reports=reports,
        audit=audit,
        clock=clock,
    )
    return SimpleNamespace(
        service=service,
        actions=actions,
        display=display,
        screenshots=screenshots,
        reports=reports,
        audit=audit,
        clock=clock,
        trace=trace,
        host_effects=host_effects,
    )


async def _health_draft(
    harness, conversation_id: str = "c1", parameters=_HEALTH_OMITTED
) -> dict:
    kwargs = {}
    if parameters is not _HEALTH_OMITTED:
        kwargs["parameters"] = parameters
    return await harness.service.handle(
        phase="draft",
        conversation_id=conversation_id,
        dialogue_count=4,
        action_id=HEALTH_ACTION,
        **kwargs,
    )


async def _health_confirm(harness, conversation_id: str = "c1") -> dict:
    return await harness.service.handle(
        phase="confirm",
        conversation_id=conversation_id,
        dialogue_count=5,
        query="yes",
    )


def _assert_no_health_effects(harness) -> None:
    assert harness.actions.calls == 0
    assert harness.display.calls == []
    assert harness.screenshots.calls == []
    assert harness.reports.calls == []
    _assert_no_host_effects(harness.host_effects)


def test_health_service_accepts_a_report_publisher():
    reports = Mock()
    service = McpActionService(reports=reports)

    assert service.reports is reports


@pytest.mark.parametrize(
    "parameters", [_HEALTH_OMITTED, None, {}], ids=["omitted", "none", "empty"]
)
@pytest.mark.asyncio
async def test_health_draft_has_no_parameters_and_no_host_effects(
    health_harness, parameters
):
    h = health_harness

    out = await _health_draft(h, parameters=parameters)

    assert out["status"] == "pending-confirmation"
    assert out["action_id"] == HEALTH_ACTION
    assert out["effect"] == HEALTH_EFFECT
    assert out["offer"] == OFFER
    assert out["notice"] == (
        "Please wait about 2-5 minutes and do not use the keyboard or mouse "
        "during System-Self-Check is running\nuntil the report is finished"
    )
    assert out["expires_in_s"] == 900
    assert any("sensitive" in caveat.casefold() for caveat in out["caveats"])

    reserved = h.service.store.resolve("c1", 5, "yes")
    assert reserved.status == "reserved"
    assert reserved.proposal.action_id == HEALTH_ACTION
    assert reserved.proposal.parameters == {}
    assert reserved.proposal.created_dialogue_count == 4
    _assert_no_health_effects(h)


@pytest.mark.asyncio
async def test_health_confirm_returns_summary_published_report_display_and_screenshot(
    health_harness,
):
    h = health_harness
    assert (await _health_draft(h))["status"] == "pending-confirmation"

    out = await _health_confirm(h)

    assert out["status"] == "ok"
    assert out["action_id"] == HEALTH_ACTION
    assert out["changed"] is False
    assert out["verification"] == "reported"
    health = out["health"]
    assert health["status"] == "warn"
    assert health["score"] == 72
    assert health["counts"] == HEALTH_COUNTS
    assert health["confidence"] == "reduced"
    assert out["report"]["status"] == "published"
    assert out["report"]["report_url"] == HEALTH_REPORT_URL
    assert out["report"]["expires_in_s"] == 900
    assert out["display"] == {"status": "displayed"}
    assert out["screenshot"]["status"] == "captured"
    assert out["screenshot"]["image_url"] == HEALTH_SCREENSHOT_URL
    assert out["helpdesk"] == h.actions.outcome["helpdesk"]
    assert h.actions.calls == 1
    assert h.reports.calls == [HEALTH_REPORT_HTML]
    assert h.display.calls == ["c1"]
    assert h.screenshots.calls == ["c1"]
    assert "report_html" not in out
    assert out["report"]["html"] == HEALTH_REPORT_HTML
    assert out["report"]["host_path"] == r"C:\Users\Test\AppData\Local\Temp\selfcheck.html"
    _assert_no_host_effects(h.host_effects)


@pytest.mark.asyncio
async def test_health_machine_fail_is_still_an_ok_action(health_harness):
    h = health_harness
    h.actions.outcome = _health_action_result("fail", score=55)
    assert (await _health_draft(h))["status"] == "pending-confirmation"

    out = await _health_confirm(h)

    assert out["status"] == "ok"
    assert out["health"]["status"] == "fail"
    assert out["health"]["score"] == 55
    assert out["report"]["status"] == "published"
    assert out["display"]["status"] == "displayed"
    assert out["screenshot"]["status"] == "captured"
    assert h.actions.calls == 1
    _assert_no_host_effects(h.host_effects)


@pytest.mark.asyncio
async def test_health_report_publication_failure_is_partial_with_summary_retained(
    health_harness,
):
    h = health_harness
    h.reports.outcome = {
        "status": "failed",
        "reason": "The temporary report could not be published.",
    }
    assert (await _health_draft(h))["status"] == "pending-confirmation"

    out = await _health_confirm(h)

    assert out["status"] == "partial"
    assert out["health"]["status"] == "warn"
    assert out["report"]["status"] == "failed"
    assert "report_url" not in out["report"]
    assert out["display"]["status"] == "displayed"
    assert out["screenshot"]["status"] == "captured"
    assert len(h.reports.calls) == 1
    _assert_no_host_effects(h.host_effects)


@pytest.mark.asyncio
async def test_health_display_failure_is_partial_and_skips_screenshot(health_harness):
    h = health_harness
    h.display.outcome = {
        "status": "attempted-but-failed",
        "reason": "Reliability Monitor could not be opened.",
    }
    assert (await _health_draft(h))["status"] == "pending-confirmation"

    out = await _health_confirm(h)

    assert out["status"] == "partial"
    assert out["report"]["status"] == "published"
    assert out["report"]["report_url"] == HEALTH_REPORT_URL
    assert out["display"]["status"] == "attempted-but-failed"
    assert out["screenshot"]["status"] == "skipped-display-unverified"
    assert h.display.calls == ["c1"]
    assert h.screenshots.calls == []
    _assert_no_host_effects(h.host_effects)


@pytest.mark.asyncio
async def test_health_screenshot_failure_is_partial_with_report_and_display_retained(
    health_harness,
):
    h = health_harness
    h.screenshots.outcome = {
        "status": "attempted-but-failed",
        "reason": "The Reliability Monitor evidence could not be captured.",
    }
    assert (await _health_draft(h))["status"] == "pending-confirmation"

    out = await _health_confirm(h)

    assert out["status"] == "partial"
    assert out["report"]["status"] == "published"
    assert out["display"]["status"] == "displayed"
    assert out["screenshot"]["status"] == "attempted-but-failed"
    assert "image_url" not in out["screenshot"]
    assert h.display.calls == ["c1"]
    assert h.screenshots.calls == ["c1"]
    _assert_no_host_effects(h.host_effects)


@pytest.mark.asyncio
async def test_health_display_launches_reliability_monitor_exactly_once(health_harness):
    h = health_harness
    h.display.outcome = {
        "status": "unverified",
        "reason": "The Reliability Monitor window could not be verified.",
    }
    assert (await _health_draft(h))["status"] == "pending-confirmation"

    out = await _health_confirm(h)

    assert out["status"] == "partial"
    assert out["display"]["status"] == "unverified"
    assert out["screenshot"]["status"] == "skipped-display-unverified"
    assert h.display.calls == ["c1"]
    assert h.screenshots.calls == []
    _assert_no_host_effects(h.host_effects)


@pytest.mark.parametrize(
    ("queued_seconds", "expected_status"),
    [(60.0, "ok"), (60.01, "queued-timeout")],
)
@pytest.mark.asyncio
async def test_health_budget_reserves_180_seconds_leaving_only_60_seconds_to_queue(
    health_harness, queued_seconds, expected_status
):
    h = health_harness
    h.actions.gate_first = True
    assert (await _health_draft(h, "c1"))["status"] == "pending-confirmation"
    assert (await _health_draft(h, "c2"))["status"] == "pending-confirmation"

    first = asyncio.create_task(_health_confirm(h, "c1"))
    second = None
    try:
        await asyncio.wait_for(h.actions.started.wait(), timeout=1)
        second = asyncio.create_task(_health_confirm(h, "c2"))
        await asyncio.sleep(0)
        h.clock.advance(queued_seconds)
    finally:
        h.actions.release.set()

    first_result, second_result = await asyncio.wait_for(
        asyncio.gather(first, second), timeout=1
    )

    assert first_result["status"] == "ok"
    assert second_result["status"] == expected_status
    assert second_result["timing"]["queue_wait_s"] == pytest.approx(queued_seconds)
    assert h.actions.max_active == 1
    if expected_status == "ok":
        assert h.actions.calls == 2
        assert len(h.reports.calls) == 2
        assert h.display.calls == ["c1", "c2"]
        assert h.screenshots.calls == ["c1", "c2"]
    else:
        assert h.actions.calls == 1
        assert len(h.reports.calls) == 1
        assert h.display.calls == ["c1"]
        assert h.screenshots.calls == ["c1"]
        assert second_result["changed"] is False
        assert second_result["verification"] == "not-run"
        assert second_result["display"] == {"status": "skipped"}
        assert second_result["screenshot"] == {"status": "skipped"}
        assert second_result["timing"]["execution_s"] == 0.0


@pytest.mark.asyncio
async def test_health_stage_deadline_stops_before_screenshot_and_reports_partial(
    health_harness,
):
    h = health_harness
    h.actions.advance_s = 150.0
    h.display.advance_s = 40.0
    assert (await _health_draft(h))["status"] == "pending-confirmation"

    out = await _health_confirm(h)

    assert out["status"] == "partial"
    assert out.get("budget_exhausted") is True
    assert out["health"]["status"] == "warn"
    assert out["report"]["status"] == "published"
    assert out["report"]["report_url"] == HEALTH_REPORT_URL
    assert out["screenshot"]["status"] == "skipped"
    assert len(h.display.calls) == 1
    assert h.screenshots.calls == []
    _assert_no_host_effects(h.host_effects)


@pytest.mark.asyncio
async def test_health_helpdesk_is_guidance_only_and_calls_no_task_tool(health_harness):
    h = health_harness
    h.actions.outcome = _health_action_result("fail", score=55)
    assert (await _health_draft(h))["status"] == "pending-confirmation"

    out = await _health_confirm(h)

    assert out["status"] == "ok"
    assert out["changed"] is False
    assert "HelpDesk" in out["helpdesk"]
    assert "Disk" in out["helpdesk"]
    serialized = json.dumps(out)
    assert "task_helpdesk" not in serialized
    assert "ticket" not in serialized.casefold()
    _assert_no_host_effects(h.host_effects)


@pytest.mark.asyncio
async def test_health_audit_is_summary_only_without_report_url_or_pii(health_harness):
    h = health_harness
    assert (await _health_draft(h))["status"] == "pending-confirmation"
    out = await _health_confirm(h)
    assert out["status"] == "ok"

    row = h.audit.write_attempt.call_args_list[-1].kwargs
    outcome = row["outcome"]
    for fragment in (
        "health=warn",
        "score=72",
        "pass=8",
        "warn=3",
        "fail=1",
        "skip=2",
        "confidence=reduced",
        "report=published",
        "display=displayed",
        "screenshot=captured",
    ):
        assert fragment in outcome
    assert isinstance(row["timing"]["display_s"], (int, float))
    assert isinstance(row["timing"]["screenshot_s"], (int, float))
    audit_text = json.dumps(
        [call.kwargs for call in h.audit.write_attempt.call_args_list]
    )
    for secret in (
        HEALTH_REPORT_URL,
        "R" * 43,
        "/mcp-action/reports/",
        "TEST\\user",
        "user@example.test",
        "10.0.0.10",
        "SN-SECRET",
        "app.exe",
        "<html",
    ):
        assert secret not in audit_text
    _assert_no_host_effects(h.host_effects)


@pytest.mark.asyncio
async def test_health_returns_only_the_published_report_link_and_ignores_forged_url(
    health_harness,
):
    h = health_harness
    h.actions.outcome["report_url"] = HEALTH_FORGED_REPORT_URL
    h.actions.outcome["report"] = {
        "status": "published",
        "report_url": HEALTH_FORGED_REPORT_URL,
    }
    assert (await _health_draft(h))["status"] == "pending-confirmation"

    out = await _health_confirm(h)

    assert out["status"] == "ok"
    assert out["report"]["report_url"] == HEALTH_REPORT_URL
    assert HEALTH_FORGED_REPORT_URL not in json.dumps(out)
    assert h.reports.calls == [HEALTH_REPORT_HTML]
    _assert_no_host_effects(h.host_effects)
