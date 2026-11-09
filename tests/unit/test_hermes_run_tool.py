"""Unit: the hermes_run_command MCP tool wrapper (spec 033).

Failing-first: written with the tool. The allowlist gate is mocked at the
Hermes boundary (respx); blocked requests never reach the gateway; ok is
stamped ONLY on the echo-and-attest protocol (COMMAND match + TASK:
COMPLETED); the identity parameter is required at the schema level, so
every turn is timed and cancellable.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from agentic_rag_mcp.config import Config
from agentic_rag_mcp.server import build_server

HERMES_BASE = "http://hermes.test:8642"


def call(server, name, args):
    raw = asyncio.run(server.call_tool(name, args))
    texts = [getattr(b, "text", "") for b in raw if getattr(b, "text", "")]
    joined = "".join(texts).strip()
    return json.loads(joined) if joined else None


def _hermes_mock():
    # assert_all_called=False: blocked turns legitimately make zero calls
    return respx.mock(base_url=HERMES_BASE, assert_all_called=False)


def _server(tmp_path, monkeypatch):
    import agentic_rag_mcp.server as server_mod
    monkeypatch.setattr(server_mod, "build_providers", lambda cfg: [])
    monkeypatch.setattr(server_mod, "Embedder", lambda model, device: object())
    cfg = Config(state_db=tmp_path / "s.sqlite3", vector_dir=tmp_path / "v",
                 decider_enabled=False,
                 hermes_api_url=HERMES_BASE, hermes_api_key="test-key",
                 hermes_timeout_s=30.0,
                 hermes_audit_path=tmp_path / "audit.jsonl")
    return build_server(cfg), cfg


def _last_audit_entry(tmp_path):
    lines = [l for l in (tmp_path / "audit.jsonl").read_text().splitlines()
             if l.strip()]
    return json.loads(lines[-1]) if lines else None


def _ok_sse(output: str) -> str:
    payload = json.dumps({"type": "response.completed",
                          "response": {"output_text": output}})
    return f"data: {payload}\ndata: [DONE]"


# ------------------------------------------------------------------ gate side

def test_blocked_never_calls_hermes_and_audits(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        route = router.post("/v1/responses")
        srv, cfg = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_run_command",
                   {"task": "run Get-NetIPAddress", "conversation_id": "c1"})
    assert out["status"] == "blocked"
    assert "not on the run-command allowlist" in out["reason"]
    assert route.call_count == 0                    # nothing reached the agent
    entry = _last_audit_entry(tmp_path)
    assert entry["decision"] == "blocked"
    assert entry["operation"] == "run-command"


def test_ask_back_envelope_is_blocked_with_the_question(tmp_path, monkeypatch):
    srv, cfg = _server(tmp_path, monkeypatch)
    out = call(srv, "hermes_run_command",
               {"task": "ipconfig and tasklist", "conversation_id": "c1"})
    assert out["status"] == "blocked"
    assert "one command per request" in out["reason"]
    assert _last_audit_entry(tmp_path)["decision"] == "blocked"


# ------------------------------------------------------------------ ok path

def test_ok_relays_real_output_and_audits_executed(tmp_path, monkeypatch):
    real = ("COMMAND: ipconfig\nOUTPUT:\nWindows IP Configuration\n\n"
            "Wireless LAN adapter Wi-Fi:\n"
            "   IPv4 Address. . . : 192.168.1.23\nTASK: COMPLETED")
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(200, content=_ok_sse(real).encode())
        srv, cfg = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_run_command",
                   {"task": "show my windows current ip address",
                    "conversation_id": "c1"})
    assert out["status"] == "ok"
    assert out["command"] == "ipconfig"
    assert "192.168.1.23" in out["result"]           # the real output, relayed
    assert "TIMING: total" in out["result"]          # timing parity (FR-004)
    entry = _last_audit_entry(tmp_path)
    assert entry["decision"] == "executed"
    assert entry["operation"] == "run-command"
    assert entry["duration_s"] is not None
    assert entry["timing"]["event_count"] >= 1


def test_targeted_command_directive_and_echo(tmp_path, monkeypatch):
    real = ("COMMAND: ping 8.8.8.8\nOUTPUT:\n\nPackets: Sent = 4, "
            "Received = 4, Lost = 0\nTASK: COMPLETED")
    calls = []
    with _hermes_mock() as router:
        def _capture(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, content=_ok_sse(real).encode())
        router.post("/v1/responses").mock(side_effect=_capture)
        srv, cfg = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_run_command",
                   {"task": "ping 8.8.8.8", "conversation_id": "c1"})
    assert out["status"] == "ok" and out["command"] == "ping 8.8.8.8"
    # the directive carries the gated command line and the protocol prompt
    assert "Run this exact command and nothing else: ping 8.8.8.8" \
        in calls[0]["input"]


# ------------------------------------------------- anti-fabrication envelope

def test_mismatched_echo_is_error_never_ok(tmp_path, monkeypatch):
    fake = ("COMMAND: ipconfig /all\nOUTPUT:\nwhatever\nTASK: COMPLETED")
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(200, content=_ok_sse(fake).encode())
        srv, cfg = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_run_command",
                   {"task": "show my ip address", "conversation_id": "c1"})
    assert out["status"] == "error"
    assert "did not run the requested command" in out["reason"]
    assert _last_audit_entry(tmp_path)["decision"] == "error"


def test_missing_attestation_is_error_never_ok(tmp_path, monkeypatch):
    fake = "COMMAND: ipconfig\nOUTPUT:\nWindows IP Configuration\n"
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(200, content=_ok_sse(fake).encode())
        srv, cfg = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_run_command",
                   {"task": "show my ip address", "conversation_id": "c1"})
    assert out["status"] == "error"
    assert "did not run the requested command" in out["reason"]


def test_failed_attestation_is_error_never_ok(tmp_path, monkeypatch):
    fake = "COMMAND: ipconfig\nOUTPUT:\nTASK: FAILED\naccess denied"
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(200, content=_ok_sse(fake).encode())
        srv, cfg = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_run_command",
                   {"task": "show my ip address", "conversation_id": "c1"})
    assert out["status"] == "error"


# ------------------------------------------------------------------ contract

def test_conversation_id_is_required_schema_rejects_without_it(tmp_path, monkeypatch):
    # FR-006: the identity is schema-required — a call without it is rejected
    # BEFORE the gate, so no attempt (and no audit row) ever exists
    srv, cfg = _server(tmp_path, monkeypatch)
    with pytest.raises(Exception):
        call(srv, "hermes_run_command", {"task": "show my ip"})
    lines = [l for l in (tmp_path / "audit.jsonl").read_text().splitlines()
             if l.strip()] if (tmp_path / "audit.jsonl").exists() else []
    assert not [l for l in lines if "run-command" in l]


def test_truncation_is_named_honestly(tmp_path, monkeypatch):
    real = ("COMMAND: systeminfo\nOUTPUT:\n" + "X" * 6000 + "\nTASK: COMPLETED")
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(200, content=_ok_sse(real).encode())
        srv, cfg = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_run_command",
                   {"task": "show system info", "conversation_id": "c1"})
    assert out["status"] == "ok"
    assert len(out["result"]) < 4600
    assert "truncated" in out["result"]


def test_error_turn_audits_with_timing(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        router.post("/v1/responses").mock(side_effect=httpx.ConnectError("refused"))
        srv, cfg = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_run_command",
                   {"task": "show my ip address", "conversation_id": "c1"})
    assert out["status"] == "error"
    assert "unreachable" in out["reason"]
    entry = _last_audit_entry(tmp_path)
    assert entry["decision"] == "error"
    assert "duration_s" in entry and "timing" in entry
