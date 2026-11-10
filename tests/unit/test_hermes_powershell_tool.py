"""Unit: the hermes_run_powershell MCP tool (spec 034 + test-plan §1b).

Failing-first: written with the tool. Two phases under one schema: draft
registers (never-list-scanned, stored, echoed, audited with exact text —
nothing executes); confirm executes the STORED draft (the confirm call
carries no command text, so what the user confirmed is structurally what
runs). ok stamps only on the stored-draft echo-match + attestation.
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
    # a fresh state per test — the pending draft is conversation-scoped;
    # patch the source module (build_server imports it at call time) with
    # ONE shared instance (a per-call getter would split draft/confirm state)
    import agentic_rag_mcp.hermes_powershell_state as ps_state_mod
    shared = ps_state_mod.PowerShellState()
    monkeypatch.setattr(ps_state_mod, "get_powershell_state", lambda: shared)
    return build_server(cfg)


def _audit(tmp_path, op="run-powershell"):
    return [json.loads(l) for l in (tmp_path / "audit.jsonl").read_text().splitlines()
            if l.strip() and op in l]


def _sse(output: str) -> str:
    payload = json.dumps({"type": "response.completed",
                          "response": {"output_text": output}})
    return f"data: {payload}\ndata: [DONE]"


CMD = "Get-Service | Where-Object {$_.StartType -eq 'Automatic'}"
OK_SSE = _sse(f"COMMAND: {CMD}\nOUTPUT:\nStatus   Name\nRunning  Spooler\nTASK: COMPLETED")


# ------------------------------------------------------------- draft phase

def test_draft_registers_pending_confirmation_no_execution(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        route = router.post("/v1/responses")
        srv = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_run_powershell",
                   {"task": "list automatic services", "conversation_id": "c1",
                    "draft": CMD})
    assert out["status"] == "pending-confirmation"
    assert out["command"] == CMD                    # echoed verbatim
    assert route.call_count == 0                    # nothing executed
    rows = _audit(tmp_path)
    assert len(rows) == 1 and rows[0]["decision"] == "executed"
    assert rows[0]["operation"] == "run-powershell"
    assert rows[0]["outcome"] == CMD                # the exact text, audited
    assert rows[0]["normalized_path"] == CMD


def test_never_list_draft_blocked_and_not_stored(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        srv = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_run_powershell",
                   {"task": "wipe it", "conversation_id": "c1",
                    "draft": "format D:"})
    assert out["status"] == "blocked"
    assert "never executable from chat" in out["reason"]
    # and the follow-up confirm answers no-pending: zero executions anywhere
    with _hermes_mock() as router:
        route = router.post("/v1/responses")
        out2 = call(srv, "hermes_run_powershell",
                    {"task": "wipe it", "conversation_id": "c1", "confirm": True})
    assert out2["status"] == "blocked"
    assert "no pending command" in out2["reason"].lower()
    assert route.call_count == 0


def test_empty_draft_usage_is_blocked(tmp_path, monkeypatch):
    srv = _server(tmp_path, monkeypatch)
    out = call(srv, "hermes_run_powershell",
               {"task": "do shell stuff", "conversation_id": "c1"})
    assert out["status"] == "blocked"
    assert "no command drafted" in out["reason"].lower()


# ---------------------------------------------------------- confirm phase

def test_confirm_executes_stored_draft_and_clears_state(tmp_path, monkeypatch):
    calls = []
    with _hermes_mock() as router:
        def _capture(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, content=OK_SSE.encode())
        router.post("/v1/responses").mock(side_effect=_capture)
        srv = _server(tmp_path, monkeypatch)
        call(srv, "hermes_run_powershell",
             {"task": "list automatic services", "conversation_id": "c1",
              "draft": CMD})
        out = call(srv, "hermes_run_powershell",
                   {"task": "confirmed", "conversation_id": "c1",
                    "confirm": True})            # no command text — stored runs
    assert out["status"] == "ok"
    assert out["command"] == CMD
    assert "Spooler" in out["result"] and "TIMING: total" in out["result"]
    # the directive carries the STORED draft and the protocol prompt
    assert f"Run this exact command and nothing else: {CMD}" in calls[0]["input"]
    # state cleared: a second confirm answers no-pending
    out2 = call(srv, "hermes_run_powershell",
                {"task": "again", "conversation_id": "c1", "confirm": True})
    assert out2["status"] == "blocked"
    rows = _audit(tmp_path)
    assert [r["decision"] for r in rows] == ["executed", "executed", "blocked"]
    assert rows[1]["normalized_path"] == CMD       # the execution row
    assert rows[1]["duration_s"] is not None        # timing parity


def test_confirm_ignores_draft_param_executes_stored(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(200, content=OK_SSE.encode())
        srv = _server(tmp_path, monkeypatch)
        call(srv, "hermes_run_powershell",
             {"task": "t", "conversation_id": "c1", "draft": CMD})
        out = call(srv, "hermes_run_powershell",
                   {"task": "t", "conversation_id": "c1",
                    "draft": "Remove-Item C:\\other.txt",  # must be IGNORED
                    "confirm": True})
    assert out["status"] == "ok" and out["command"] == CMD


def test_supersession_second_draft_replaces_first(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        route = router.post("/v1/responses")
        srv = _server(tmp_path, monkeypatch)
        call(srv, "hermes_run_powershell",
             {"task": "t", "conversation_id": "c1", "draft": "Get-Date"})
        out = call(srv, "hermes_run_powershell",
                   {"task": "t", "conversation_id": "c1",
                    "draft": "Get-Host"})
        assert out["status"] == "pending-confirmation"
        assert out["command"] == "Get-Host"
        assert route.call_count == 0               # neither executed


def test_never_list_cannot_reach_execution_via_state(tmp_path, monkeypatch):
    # defense-in-depth: even a corrupted stored never-list text refuses
    import agentic_rag_mcp.hermes_powershell_state as ps_state_mod
    srv = _server(tmp_path, monkeypatch)
    ps_state_mod.get_powershell_state().set_pending("c1", "format C:")
    with _hermes_mock() as router:
        route = router.post("/v1/responses")
        out = call(srv, "hermes_run_powershell",
                   {"task": "t", "conversation_id": "c1", "confirm": True})
    assert out["status"] == "blocked"
    assert "never executable from chat" in out["reason"]
    assert route.call_count == 0


# ------------------------------------------------- anti-fabrication envelope

def test_echo_mismatch_is_error_never_ok(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(200, content=_sse(
            "COMMAND: Get-Date\nOUTPUT:\ndoomsday\nTASK: COMPLETED").encode())
        srv = _server(tmp_path, monkeypatch)
        call(srv, "hermes_run_powershell",
             {"task": "t", "conversation_id": "c1", "draft": CMD})
        out = call(srv, "hermes_run_powershell",
                   {"task": "t", "conversation_id": "c1", "confirm": True})
    assert out["status"] == "error"
    assert "did not run the confirmed command as gated" in out["reason"]
    # the wrong command's output is never relayed as a result (the reason's
    # diagnostic tail naming it is the established honest-error pattern)
    assert "doomsday" not in out.get("result", "")
    assert out.get("command") is None


def test_missing_attestation_is_error_never_ok(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(200, content=_sse(
            f"COMMAND: {CMD}\nOUTPUT:\nsomething").encode())
        srv = _server(tmp_path, monkeypatch)
        call(srv, "hermes_run_powershell",
             {"task": "t", "conversation_id": "c1", "draft": CMD})
        out = call(srv, "hermes_run_powershell",
                   {"task": "t", "conversation_id": "c1", "confirm": True})
    assert out["status"] == "error"


def test_failed_attestation_is_error_never_ok(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(200, content=_sse(
            f"COMMAND: {CMD}\nOUTPUT:\nTASK: FAILED\naccess denied").encode())
        srv = _server(tmp_path, monkeypatch)
        call(srv, "hermes_run_powershell",
             {"task": "t", "conversation_id": "c1", "draft": CMD})
        out = call(srv, "hermes_run_powershell",
                   {"task": "t", "conversation_id": "c1", "confirm": True})
    assert out["status"] == "error"


# ------------------------------------------------------------------ contract

def test_conversation_id_is_required_schema_rejects_without_it(tmp_path, monkeypatch):
    srv = _server(tmp_path, monkeypatch)
    with pytest.raises(Exception):
        call(srv, "hermes_run_powershell", {"task": "t", "draft": CMD})
    assert not (tmp_path / "audit.jsonl").exists() or not _audit(tmp_path)


def test_truncation_is_named_honestly(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(200, content=_sse(
            f"COMMAND: {CMD}\nOUTPUT:\n" + "X" * 6000 + "\nTASK: COMPLETED").encode())
        srv = _server(tmp_path, monkeypatch)
        call(srv, "hermes_run_powershell",
             {"task": "t", "conversation_id": "c1", "draft": CMD})
        out = call(srv, "hermes_run_powershell",
                   {"task": "t", "conversation_id": "c1", "confirm": True})
    assert out["status"] == "ok"
    assert len(out["result"]) < 4600 and "truncated" in out["result"]


def test_transport_error_is_honest_error_with_timing(tmp_path, monkeypatch):
    with _hermes_mock() as router:
        router.post("/v1/responses").mock(side_effect=httpx.ConnectError("refused"))
        srv = _server(tmp_path, monkeypatch)
        call(srv, "hermes_run_powershell",
             {"task": "t", "conversation_id": "c1", "draft": CMD})
        out = call(srv, "hermes_run_powershell",
                   {"task": "t", "conversation_id": "c1", "confirm": True})
    assert out["status"] == "error"
    assert "unreachable" in out["reason"]
    rows = _audit(tmp_path)
    assert rows[-1]["decision"] == "error"
    assert "duration_s" in rows[-1] and "timing" in rows[-1]


def test_pending_is_conversation_scoped(tmp_path, monkeypatch):
    srv = _server(tmp_path, monkeypatch)
    call(srv, "hermes_run_powershell",
         {"task": "t", "conversation_id": "c1", "draft": CMD})
    out = call(srv, "hermes_run_powershell",
               {"task": "t", "conversation_id": "c2", "confirm": True})
    assert out["status"] == "blocked"
    assert "no pending command" in out["reason"].lower()