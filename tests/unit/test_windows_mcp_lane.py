"""Spec 040 — the Windows-MCP lane (040-windowsmcp-powershell).

Unit battery: transport contract (the canonical Host header fix verified
live 2026-11-14 — the service 400s 'Invalid host header' otherwise), tool
schema validation, honest envelopes, output bounding, audit rows, and the
behavioral probe matrix (the browser-lane bridge-mask lesson)."""

import asyncio
import json
import socket
import threading

import httpx

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
        assert set(TOOL_SCHEMAS) == {"Process", "Clipboard", "Notification",
                                     "Registry"}
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
        ok, reason = validate_args("PowerShell", {"mode": "list"})
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
        assert classify_refusal("USER_CONTROL: not approved")
        assert not classify_refusal("some random service failure")


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
