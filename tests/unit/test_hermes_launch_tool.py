"""Unit: the hermes_launch_app MCP tool wrapper (spec 029, contracts §1–§4).

Failing-first: written before the tool exists. The Hermes client is mocked
at the trust boundary (respx on httpx, scoped to the Hermes base URL so
nothing else is intercepted) — blocked verdicts never reach it; failures
map to honest error envelopes with recovery hints; every attempt writes
exactly one audit entry (operation per verdict, allowed_root="").
"""

from __future__ import annotations

import asyncio
import json

import httpx
import respx

from agentic_rag_mcp.config import Config
from agentic_rag_mcp.server import build_server

HERMES_BASE = "http://hermes.test:8642"


def call(server, name, args):
    raw = asyncio.run(server.call_tool(name, args))
    structured = [b["result"] for b in raw if isinstance(b, dict) and "result" in b]
    if structured:
        return structured[0]
    texts = [getattr(b, "text", "") for b in raw if getattr(b, "text", "")]
    joined = "".join(texts).strip()
    return json.loads(joined) if joined else None


def _hermes_mock():
    # scoped router: only Hermes traffic is intercepted, everything else passes through
    return respx.mock(base_url=HERMES_BASE, assert_all_mocked=False,
                      assert_all_called=False)   # blocked verdicts may never call the route


def _server(tmp_path, monkeypatch):
    import agentic_rag_mcp.server as server_mod

    monkeypatch.setattr(server_mod, "build_providers", lambda cfg: [])
    # no network, no model load — the launch lane never touches the embedder
    monkeypatch.setattr(server_mod, "Embedder", lambda model, device: object())
    cfg = Config(state_db=tmp_path / "s.sqlite3", vector_dir=tmp_path / "v",
                 decider_enabled=False,
                 hermes_api_url=HERMES_BASE,
                 hermes_api_key="test-key",
                 hermes_timeout_s=5.0,
                 hermes_audit_path=tmp_path / "audit.jsonl")
    return build_server(cfg)


def _last_audit_entry(tmp_path):
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    return json.loads(lines[-1])


# ---------------------------------------------------------------- blocked

def test_blocked_never_calls_hermes_and_audits(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        route = router.post("/v1/responses")
        srv = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_launch_app", {"task": "launch outlook --dangerous-flag"})
        assert out["status"] == "blocked"
        assert out["decision"] == "blocked"
        assert "argument" in out["reason"].lower()
        assert route.call_count == 0                      # nothing reached Hermes
        entry = _last_audit_entry(tmp_path)
        assert entry["decision"] == "blocked"
        assert entry["operation"] == "unsupported"         # rule refusal, like the file lane
        assert entry["allowed_root"] == ""                 # no containment root for launches


def test_ask_back_blocked_and_audited(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        route = router.post("/v1/responses")
        srv = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_launch_app", {"task": "open it"})
        assert out["status"] == "blocked"
        assert "which" in out["reason"].lower()
        assert route.call_count == 0
        assert _last_audit_entry(tmp_path)["operation"] == "ask-back"


# ---------------------------------------------------------------- ok

def test_ok_launch_relays_result_and_audits_executed(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(
            200, json={"output_text": "Started notepad.exe — new process observed.\nLAUNCH: SUCCESS"})
        srv = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_launch_app", {"task": "open notepad"})
        assert out["status"] == "ok"
        assert out["decision"] == "executed"
        assert "Started notepad.exe" in out["result"]
        assert out["target"].lower() == "notepad"
        entry = _last_audit_entry(tmp_path)
        assert entry["decision"] == "executed"
        assert entry["operation"] == "launch-app"
        assert entry["allowed_root"] == ""
        assert "Started notepad.exe" in entry["outcome"]


def test_agent_failed_marker_is_error_never_ok(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(200, json={"output_text":
            "I couldn't launch it — Notepad never started.\n\n"
            "LAUNCH: FAILED: Windows interop is disabled on this host"})
        srv = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_launch_app", {"task": "open notepad"})
        assert out["status"] == "error"
        assert "could not launch" in out["reason"].lower()
        assert "interop" in out["reason"].lower()
        assert _last_audit_entry(tmp_path)["decision"] == "error"


def test_agent_output_without_marker_is_error_never_ok(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(
            200, json={"output_text": "Started notepad.exe, probably."})
        srv = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_launch_app", {"task": "open notepad"})
        assert out["status"] == "error"
        assert _last_audit_entry(tmp_path)["decision"] == "error"


# ---------------------------------------------------------------- error handling

def test_gateway_down_honest_error_and_audited(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        router.post("/v1/responses").mock(side_effect=httpx.ConnectError("refused"))
        srv = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_launch_app", {"task": "open notepad"})
        assert out["status"] == "error"
        assert "unreachable" in out["reason"].lower()
        assert "hermes gateway restart" in out["reason"].lower()   # recovery hint
        assert _last_audit_entry(tmp_path)["decision"] == "error"


def test_key_rejected_honest_error(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(401, json={"detail": "unauthorized"})
        srv = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_launch_app", {"task": "open notepad"})
        assert out["status"] == "error"
        assert "key" in out["reason"].lower()
        assert _last_audit_entry(tmp_path)["decision"] == "error"


def test_timeout_honest_error(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        router.post("/v1/responses").mock(side_effect=httpx.ReadTimeout("too slow"))
        srv = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_launch_app", {"task": "open notepad"})
        assert out["status"] == "error"
        assert "within" in out["reason"].lower()          # "did not finish within 5s"
        assert _last_audit_entry(tmp_path)["decision"] == "error"


def test_empty_agent_output_is_error_never_ok(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(200, json={"output_text": ""})
        srv = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_launch_app", {"task": "open notepad"})
        assert out["status"] == "error"
        assert "empty" in out["reason"].lower()
