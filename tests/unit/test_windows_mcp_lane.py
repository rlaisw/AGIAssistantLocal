"""Spec 040 — the Windows-MCP lane (040-windowsmcp-powershell).

Unit battery: transport contract (the canonical Host header fix verified
live 2026-11-14 — the service 400s 'Invalid host header' otherwise), tool
schema validation, honest envelopes, output bounding, audit rows, and the
behavioral probe matrix (the browser-lane bridge-mask lesson)."""

import asyncio
import base64
import json
import socket
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import httpx
import pytest

from agentic_rag_mcp.hermes_audit import HermesAudit
from agentic_rag_mcp.windows_mcp import (
    BRIDGE_SSE_URL,
    CANONICAL_HOST,
    RECOVERY_TEXT,
    TEXT_BOUND,
    TOOL_SCHEMAS,
    bound_text,
    call_tool,
    classify_refusal,
    health,
    machine_processors,
    render_cpu_scale,
    validate_args,
)
from agentic_rag_mcp.windows_mcp.client import _headers


class TestTransportContract:
    """The 400-fix is part of the lane's contract (research.md R1)."""

    def test_every_request_carries_the_canonical_host(self):
        assert _headers() == {"Host": CANONICAL_HOST}

    def test_the_url_is_the_bridged_sse_endpoint(self):
        assert BRIDGE_SSE_URL == "http://172.17.0.1:18800/sse"

    def test_recovery_text_names_a_task_that_exists(self):
        # the browser-lane lesson: the hint must name a real recovery
        assert "schtasks /run /tn windows-mcp-server" in RECOVERY_TEXT

    def test_tool_surface_matches_the_captured_schemas(self):
        # spec 041 (2026-11-15): the applet tiers added the live-captured
        # GUI/shell tool schemas to the lane's validation surface
        assert set(TOOL_SCHEMAS) == {"Process", "Clipboard", "Notification",
                                     "Registry", "PowerShell", "App",
                                     "Snapshot", "Screenshot", "Click",
                                     "Type", "Wait", "WaitFor"}
        assert TOOL_SCHEMAS["Process"]["required"] == {"mode"}
        assert TOOL_SCHEMAS["Notification"]["required"] == {
            "title", "message", "app_id"}
        assert TOOL_SCHEMAS["Registry"]["required"] == {"mode", "path"}


def _serve(handler):
    """Host-validating fake: 400 unless the canonical Host header,
    else the handler's response — the miniature of the real 400."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    threading.Thread(target=_accept_loop, args=(srv, handler),
                     daemon=True).start()
    return srv.getsockname()[1]


def _accept_loop(srv, handler):
    while True:
        try:
            conn, _ = srv.accept()
        except OSError:
            return
        threading.Thread(target=handler, args=(conn,), daemon=True).start()


def _respond_200_if_canonical_host(conn):
    try:
        req = conn.recv(4096).decode("utf-8", "replace")
        if f"Host: {CANONICAL_HOST}" not in req:
            body = b"Invalid host header"
            conn.sendall(b"HTTP/1.1 400 Bad Request\r\n"
                         b"Content-Length: " + str(len(body)).encode()
                         + b"\r\n\r\n" + body)
        else:
            conn.sendall(b"HTTP/1.1 200 OK\r\n"
                         b"Content-Type: text/event-stream\r\n\r\n"
                         b"event: endpoint\r\n"
                         b"data: /messages/?session_id=unit\r\n\r\n")
        conn.close()
    except OSError:
        pass


class TestHostValidation400:
    """The exact failure class the bridge exposed, in miniature."""

    def test_without_the_header_the_service_400s(self):
        port = _serve(_respond_200_if_canonical_host)
        r = httpx.get(f"http://127.0.0.1:{port}/sse", timeout=5)
        assert r.status_code == 400
        assert "Invalid host header" in r.text

    def test_with_the_canonical_header_the_service_answers(self):
        port = _serve(_respond_200_if_canonical_host)
        r = httpx.get(f"http://127.0.0.1:{port}/sse",
                      headers=_headers(), timeout=5)
        assert r.status_code == 200
        assert "event: endpoint" in r.text


class TestArgsValidation:
    """Invalid shape -> blocked, NO service call (contracts)."""

    def test_unknown_tool_rejected(self):
        ok, reason = validate_args("FluxCapacitor", {"mode": "list"})
        assert not ok and "unknown tool" in reason

    def test_missing_required_rejected(self):
        ok, reason = validate_args("Process", {"sort_by": "memory"})
        assert not ok and "requires" in reason
        ok, reason = validate_args("Registry", {"mode": "read"})
        assert not ok and "path" in reason

    def test_unknown_arg_rejected(self):
        ok, reason = validate_args("Process",
                                   {"mode": "list", "hack": 1})
        assert not ok and "unknown args" in reason

    def test_valid_args_pass(self):
        ok, reason = validate_args("Process",
                                   {"mode": "list", "limit": 5})
        assert ok and reason is None


class TestEnvelopesAndBounding:
    def test_long_output_bounded_and_named(self):
        bounded, truncated = bound_text("x" * (TEXT_BOUND + 500))
        assert truncated and len(bounded) == TEXT_BOUND

    def test_short_output_not_truncated(self):
        bounded, truncated = bound_text("short")
        assert not truncated and bounded == "short"

    def test_refusal_classification(self):
        assert classify_refusal("The request was declined by the user")
        assert classify_refusal("not approved")
        assert not classify_refusal("some random service failure")

    def test_user_control_is_a_wait_not_a_refusal(self):
        # bugtest-040 live finding: the service's consent-WAIT signal
        # (USER_CONTROL + wait_seconds) must not classify as a refusal —
        # the call loop retries while the desktop user approves
        from agentic_rag_mcp.windows_mcp.client import _user_control_wait
        assert not classify_refusal('{"code": "USER_CONTROL", "status": '
                                     '{"state": "user", "wait_seconds": 7.3}}')
        wait = _user_control_wait('{"code": "USER_CONTROL", "status": '
                                  '{"state": "user", "wait_seconds": 7.3}}')
        assert wait == 7.3
        assert _user_control_wait('{"code": "OTHER"}') is None
        assert _user_control_wait('{"code": "USER_CONTROL"}') == 10.0  # default


class TestBlockedAuditsLocally:
    """Validation-blocked calls never reach the network and still audit."""

    def test_invalid_args_blocked_and_audited(self, tmp_path):
        audit = HermesAudit(tmp_path / "audit.jsonl")
        out = asyncio.run(call_tool("Process", {}, "conv-unit-blocked",
                                    audit=audit))
        assert out["status"] == "blocked"
        row = json.loads((tmp_path / "audit.jsonl").read_text().splitlines()[0])
        assert row["decision"] == "blocked"
        assert row["operation"] == "windows-mcp-process"
        assert row["conversation_id"] == "conv-unit-blocked"

    def test_missing_conversation_id_blocked(self, tmp_path):
        audit = HermesAudit(tmp_path / "audit.jsonl")
        out = asyncio.run(call_tool("Process", {"mode": "list"}, "",
                                    audit=audit))
        assert out["status"] == "blocked"
        assert "conversation_id is required" in out["reason"]


class TestProbeBehavior:
    """The bridge-mask lesson (2026-11-14): measure the far side, honestly."""

    def test_accept_then_close_reports_unavailable(self):
        port = _serve(lambda c: c.close())
        out = health.probe_windows_mcp(
            url=f"http://127.0.0.1:{port}/sse", timeout_s=5)
        assert out["status"] == "error"
        assert out["windows_mcp"]["reachable"] is False
        assert "windows-mcp-lane-unavailable" in out["reason"]
        assert RECOVERY_TEXT in out["reason"]

    def test_accept_never_speak_falls_to_timeout(self):
        port = _serve(lambda c: None)
        out = health.probe_windows_mcp(
            url=f"http://127.0.0.1:{port}/sse", timeout_s=0.3)
        assert out["status"] == "error"

    def test_responder_reports_ok_and_header_was_canonical(self):
        # the fake only answers 200 when the Host header is canonical —
        # so a pass here also proves the probe carries the fix
        port = _serve(_respond_200_if_canonical_host)
        out = health.probe_windows_mcp(
            url=f"http://127.0.0.1:{port}/sse", timeout_s=5)
        assert out["status"] == "ok"
        assert out["windows_mcp"]["reachable"] is True


class TestProcessListShape:
    def test_process_list_builds_the_canonical_call(self):
        # the acceptance case's args, pinned
        ok, reason = validate_args("Process",
                                   {"mode": "list", "sort_by": "memory",
                                    "limit": 5})
        assert ok, reason


class TestCpuScaleRendering:
    """the-value-of-cpu-is-impossibel round 2 (2026-11-14): CPU values
    must be human-understandable — the raw per-core aggregate stays, and
    each row gains '(x% of machine)' normalized to the whole host."""

    TABLE = (
        "Processes (5 shown):\n"
        "  PID  Name                 CPU%     Memory\n"
        "-----  -------------------  -------  ----------\n"
        "    0  System Idle Process  1847.4%  0.0 MB\n"
        " 8928  vmmemWSL             121.8%   19190.5 MB\n")

    def test_machine_scale_is_the_value(self):
        out = render_cpu_scale(self.TABLE, 20)
        # the human scale leads every row; no >100% number in any cell
        assert "92.4%" in out                          # 1847.4 / 20
        assert "6.1%" in out                           # 121.8 / 20
        assert "CPU% (of machine)" in out               # the column header
        assert "(92.4% of machine)" not in out         # no parenthetical cells
        # the raw aggregates survive only in the footnote
        assert "System Idle Process raw 1847.4%" in out
        assert "vmmemWSL raw 121.8%" in out

    def test_unknown_count_falls_back_to_raw(self):
        assert render_cpu_scale(self.TABLE, 0) == self.TABLE

    def test_inconsistent_count_self_check_falls_back(self):
        # raw 1847 on 8 processors = 231% of machine -> impossible, the
        # count cannot be trusted -> never present wrong numbers
        assert render_cpu_scale(self.TABLE, 8) == self.TABLE

    def test_non_listing_text_untouched(self):
        out = render_cpu_scale("some other output", 20)
        assert out == "some other output"

    def test_env_parsing(self, monkeypatch):
        monkeypatch.setenv("WINDOWS_LOGICAL_PROCESSORS", "20")
        assert machine_processors() == 20
        monkeypatch.setenv("WINDOWS_LOGICAL_PROCESSORS", "bogus")
        assert machine_processors() == 0
        monkeypatch.delenv("WINDOWS_LOGICAL_PROCESSORS", raising=False)
        assert machine_processors() == 0

    def test_deploy_bakes_the_host_count(self):
        # the deploy reads the Windows host's count via interop (the
        # container's own cpu_count is the capped WSL VM view and must
        # never be used) and passes it to the container
        import agentic_rag_mcp.deploy.docker_ops as ops
        with open(ops.__file__, encoding="utf-8") as f:
            src = f.read()
        assert "WINDOWS_LOGICAL_PROCESSORS" in src
        assert "_windows_logical_processors" in src


class TestUserControlDeferral:
    """error-windows-mcp-tool-error (2026-11-14): a USER_CONTROL signal
    still pending after the bounded consent retries is a desktop-activity
    DEFERRAL — a named blocked envelope, never raw JSON, never the
    schtasks hint (the service is up). Explicit declines keep their own
    wording."""

    UC = ('{"code": "USER_CONTROL", "status": {"state": "user", '
          '"generation": 92, "wait_seconds": 0.02}}')

    @staticmethod
    def _install(monkeypatch, responses):
        """Fake the SSE+session layer; responses: list or factory of
        (text-or-content-list, is_error) tuples. Returns the call counter."""
        import agentic_rag_mcp.windows_mcp.client as cl

        class _Item:
            def __init__(self, text):
                self.text = text

        class _Res:
            def __init__(self, text, is_error):
                self.isError = is_error
                self.content = text if isinstance(text, list) else [_Item(text)]

        class _Session:
            calls = 0
            last_args = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def initialize(self):
                pass

            async def call_tool(self, tool, args):
                type(self).calls += 1
                type(self).last_args = args
                text, is_error = responses() if callable(responses) \
                    else responses
                return _Res(text, is_error)

        import contextlib

        @contextlib.asynccontextmanager
        async def _sse(url, headers=None):
            yield ("read", "write")

        monkeypatch.setattr(cl, "sse_client", _sse)
        monkeypatch.setattr(cl, "ClientSession", lambda r, w: _Session())
        return _Session

    def test_exhausted_user_control_is_a_named_deferral(self, monkeypatch):
        sess = self._install(monkeypatch, lambda: (self.UC, True))
        audit = HermesAudit(tmp_path := __import__("pathlib").Path(
            "/tmp/kilo/deferral-audit.jsonl"))
        out = asyncio.run(call_tool("Process", {"mode": "list"},
                                    "conv-deferral", audit))
        assert out["status"] == "blocked"
        assert "deferred the call while the desktop user is active" in out["reason"]
        assert "schtasks" not in out["reason"]       # service is up
        assert '{"code"' not in out["reason"]        # no raw JSON payload
        assert "wait_seconds" not in out["reason"]
        assert sess.calls == 8                        # the bounded retries (8 attempts, ~64 s of patience — 2026-11-16)
        row = json.loads(tmp_path.read_text().splitlines()[-1])
        assert row["decision"] == "blocked"
        assert row["operation"] == "windows-mcp-process"

    def test_explicit_decline_keeps_the_refusal_wording(self, monkeypatch):
        self._install(monkeypatch, lambda: (
            "The request was declined by the user", True))
        out = asyncio.run(call_tool("Process", {"mode": "list"},
                                    "conv-decline", None))
        assert out["status"] == "blocked"
        assert "host did not approve execution" in out["reason"]
        assert "deferred" not in out["reason"]

    def test_success_after_two_deferrals(self, monkeypatch):
        # the wait-retry loop recovers when the desktop goes quiet
        seq = iter([(self.UC, True), (self.UC, True), ("PID 1 idle", False)])
        sess = self._install(monkeypatch, lambda: next(seq))
        out = asyncio.run(call_tool("Process", {"mode": "list"},
                                    "conv-recover", None))
        assert out["status"] == "ok"
        assert sess.calls == 3

    @pytest.mark.parametrize("attempts", [1, 8])
    def test_consent_attempts_accepts_the_boundaries(self, monkeypatch,
                                                     attempts):
        sess = self._install(monkeypatch, lambda: (self.UC, True))
        out = asyncio.run(call_tool("Process", {"mode": "list"},
                                    "conv-consent-bound", None,
                                    consent_attempts=attempts))
        assert out["status"] == "blocked"
        assert sess.calls == attempts
        assert sess.last_args == {"mode": "list"}

    @pytest.mark.parametrize("attempts", [0, 9])
    def test_consent_attempts_outside_the_bounds_never_dispatch(
            self, monkeypatch, attempts):
        sess = self._install(monkeypatch, lambda: (self.UC, True))
        out = asyncio.run(call_tool("Process", {"mode": "list"},
                                    "conv-consent-invalid", None,
                                    consent_attempts=attempts))
        assert out["status"] == "blocked"
        assert "consent_attempts" in out["reason"]
        assert sess.calls == 0


class TestImageExtraction:
    """Spec 047 T015: screenshots are additive, singular, and bounded."""

    FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "mcp_action"
    BASELINE: ClassVar[dict] = {
        "status": "ok", "tool": "Screenshot",
        "text": "Screenshot captured.", "truncated": False}

    @classmethod
    def _content(cls, case):
        document = json.loads((cls.FIXTURES / "windows_mcp_results.json")
                              .read_text(encoding="utf-8"))
        content = []
        for item in document[case]["content"]:
            values = dict(item)
            data_file = values.pop("data_file", None)
            if data_file:
                values["data"] = base64.b64encode(
                    (cls.FIXTURES / data_file).read_bytes()).decode("ascii")
            content.append(SimpleNamespace(**values))
        return content

    @classmethod
    def _image_bytes(cls, filename):
        return (cls.FIXTURES / filename).read_bytes()

    def _run(self, monkeypatch, tmp_path, caplog, content, **options):
        caplog.set_level("DEBUG")
        sess = TestUserControlDeferral._install(monkeypatch, (content, False))
        audit_path = tmp_path / "audit.jsonl"
        out = asyncio.run(call_tool("Screenshot", {}, "conv-image",
                                    HermesAudit(audit_path), **options))
        return out, sess, audit_path

    @staticmethod
    def _assert_no_binary_leak(audit_path, caplog, *payloads):
        audit_bytes = audit_path.read_bytes()
        audit_text = audit_bytes.decode("utf-8")
        for payload in payloads:
            encoded = base64.b64encode(payload).decode("ascii")
            assert payload not in audit_bytes, "image bytes leaked into audit"
            for rendered in (encoded, repr(payload)):
                assert rendered not in audit_text, "image data leaked into audit"
                assert rendered not in caplog.text, "image data leaked into logs"

    @staticmethod
    def _assert_bounded_image_error(out, audit_path, caplog, content):
        assert out["status"] == "error"
        reason = out.get("reason", "")
        assert reason.startswith("error:")
        assert "image" in reason.lower()
        assert len(reason) <= TEXT_BOUND
        assert not out.get("images")
        audit_text = audit_path.read_text(encoding="utf-8")
        for item in content:
            encoded = getattr(item, "data", "")
            if encoded:
                assert encoded not in reason, "Base64 leaked into the error"
                assert encoded not in audit_text, "Base64 leaked into audit"
                assert encoded not in caplog.text, "Base64 leaked into logs"

    @pytest.mark.parametrize("options", [{}, {"include_images": False}],
                             ids=["default", "explicit-false"])
    def test_mixed_result_is_compatible_without_opt_in(
            self, monkeypatch, tmp_path, caplog, options):
        content = self._content("mixed_image_result")
        out, sess, audit_path = self._run(monkeypatch, tmp_path, caplog,
                                          content, **options)
        assert out == self.BASELINE
        assert "images" not in out
        assert sess.last_args == {}
        self._assert_no_binary_leak(audit_path, caplog,
                                    self._image_bytes("tiny.png"))

    @pytest.mark.parametrize(("filename", "mime_type"), [
        ("tiny.png", "image/png"),
        ("tiny.jpg", "image/jpeg"),
    ])
    def test_opt_in_extracts_one_image_and_preserves_the_envelope(
            self, monkeypatch, tmp_path, caplog, filename, mime_type):
        content = self._content("mixed_image_result")
        payload = self._image_bytes(filename)
        image = next(item for item in content if item.type == "image")
        image.data = base64.b64encode(payload).decode("ascii")
        image.mimeType = mime_type
        out, sess, audit_path = self._run(monkeypatch, tmp_path, caplog,
                                          content, include_images=True)
        assert {key: value for key, value in out.items() if key != "images"} \
            == self.BASELINE
        assert len(out["images"]) == 1
        captured = out["images"][0]
        assert captured.data == payload
        assert captured.mime_type == mime_type
        assert sess.last_args == {}
        self._assert_no_binary_leak(audit_path, caplog, payload)

    @pytest.mark.parametrize(("case", "reason_part"), [
        ("missing_image", "image"),
        ("multiple_images", "image"),
        ("malformed_image", "base64"),
    ])
    def test_invalid_image_results_are_honest_bounded_errors(
            self, monkeypatch, tmp_path, caplog, case, reason_part):
        content = self._content(case)
        out, _, audit_path = self._run(monkeypatch, tmp_path, caplog,
                                       content, include_images=True)
        self._assert_bounded_image_error(out, audit_path, caplog, content)
        assert reason_part in out["reason"].lower()

    def test_wrong_image_mime_is_rejected(self, monkeypatch, tmp_path, caplog):
        content = self._content("mixed_image_result")
        image = next(item for item in content if item.type == "image")
        image.mimeType = "image/gif"
        out, _, audit_path = self._run(monkeypatch, tmp_path, caplog,
                                       content, include_images=True)
        self._assert_bounded_image_error(out, audit_path, caplog, content)
        assert "mime" in out["reason"].lower()

    def test_image_bytes_must_match_the_declared_mime(
            self, monkeypatch, tmp_path, caplog):
        content = self._content("mixed_image_result")
        image = next(item for item in content if item.type == "image")
        image.data = base64.b64encode(self._image_bytes("tiny.jpg")).decode(
            "ascii")
        image.mimeType = "image/png"
        out, _, audit_path = self._run(monkeypatch, tmp_path, caplog,
                                       content, include_images=True)
        self._assert_bounded_image_error(out, audit_path, caplog, content)

    def test_image_over_ten_mib_is_rejected(self, monkeypatch, tmp_path,
                                            caplog):
        content = self._content("mixed_image_result")
        image = next(item for item in content if item.type == "image")
        payload = self._image_bytes("tiny.png") + b"\0" * (10 * 1024 * 1024)
        image.data = base64.b64encode(payload).decode("ascii")
        out, _, audit_path = self._run(monkeypatch, tmp_path, caplog,
                                       content, include_images=True)
        self._assert_bounded_image_error(out, audit_path, caplog, content)
        assert "10" in out["reason"]


class TestChatSurface:
    """does-not-have-a-powershell-windows-mcp-tool (2026-11-14): the
    verified lane is exposed to the chat as read-only tools, and both ops
    are loop-exempt (the v2 fast-path precedent — no protocol rounds
    around sub-second deterministic tools)."""

    def test_both_chat_tools_are_registered(self):
        import agentic_rag_mcp.server as srv
        with open(srv.__file__, encoding="utf-8") as f:
            src = f.read()
        assert "windows_mcp_process_list" in src
        assert "windows_mcp_status" in src

    def test_privileged_windows_mcp_tools_are_not_registered(self):
        # the first slice is read-only by design (the T019 unprompted
        # registry-write finding): no clipboard/registry/notification chat
        # tools, no kill mode
        import agentic_rag_mcp.server as srv
        with open(srv.__file__, encoding="utf-8") as f:
            src = f.read()
        assert "windows_mcp_clipboard" not in src
        assert "windows_mcp_registry" not in src
        assert "windows_mcp_notification" not in src

    def test_both_ops_are_loop_exempt(self):
        from agentic_rag_mcp.loop_gate import EXEMPT_OPS
        assert {"windows-mcp-process", "windows-mcp-status"} <= set(EXEMPT_OPS)
