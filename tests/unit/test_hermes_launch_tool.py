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


def test_launch_lane_budget_is_under_daemon_kill_timer():
    """desktop-followup-timeout-600s (2026-11-08): the launch lane's Hermes
    budget (540 s) must sit 90% of the Dify plugin-daemon's ~600 s tool-kill
    timer so the sidecar's honest verdict always precedes the silent kill.
    (2026-11-09: the lane is stream-mode with a conversation key; the 540 s
    budget now flows to _run_hermes and the keepalive wrapper.)"""
    import inspect as _inspect
    import agentic_rag_mcp.server as _srv
    src = _inspect.getsource(_srv)
    assert "budget=540.0" in src


def test_run_task_accepts_timeout_override():
    """The override reaches the httpx call and the honest error message."""
    import agentic_rag_mcp.hermes_client as hc
    import httpx as _hx
    class _Boom:
        def __init__(self, *a, **k): raise hc.httpx.TimeoutException("t/o")
    orig = hc.httpx.post
    hc.httpx.post = _Boom
    try:
        class _Cfg: hermes_api_url = "http://x"; hermes_api_key = "k"; hermes_timeout_s = 600.0
        out = hc.run_task(_Cfg(), "task", timeout_s=540.0)
        assert out["ok"] is False and "540" in out["error"], out
    finally:
        hc.httpx.post = orig


def test_launch_instructions_pin_fastest_path_guidance():
    """The FASTEST-PATH NAVIGATION rule must survive refactors — it is the
    behavioral half of the 540 s budget fix."""
    from agentic_rag_mcp.hermes_client import LAUNCH_INSTRUCTIONS
    assert "FASTEST-PATH NAVIGATION" in LAUNCH_INSTRUCTIONS
    assert "~540 s" in LAUNCH_INSTRUCTIONS
    assert "end the turn honestly instead of grinding toward the timeout" in LAUNCH_INSTRUCTIONS


def test_cancel_inflight_registry_semantics():
    """repeated-show-AI-is-controlling-… (2026-11-09): the per-conversation
    registry is the Stop lever — cancel closes the registered client once;
    unknown keys are a completion race (False), not an error; unregister only
    removes its OWN registration (a stale re-registration never evicts the
    live one)."""
    from agentic_rag_mcp import hermes_client as hc

    class FakeClient:
        def __init__(self):
            self.closed = False
        def close(self):
            self.closed = True

    a, b = FakeClient(), FakeClient()
    hc._register_inflight("cancel-test-1", a)
    assert hc.cancel_inflight("cancel-test-1") is True
    assert a.closed is True
    # a second cancel inside the unregister window is idempotent (re-close)
    assert hc.cancel_inflight("cancel-test-1") is True
    assert hc.cancel_inflight("never-registered") is False
    hc._register_inflight("cancel-test-2", b)
    stale = FakeClient()
    hc._register_inflight("cancel-test-2", stale)        # stale overwrite
    hc._unregister_inflight("cancel-test-2", b)           # must NOT evict the stale one
    assert "cancel-test-2" in hc._INFLIGHT
    hc._unregister_inflight("cancel-test-2", stale)       # correct owner evicts
    assert "cancel-test-2" not in hc._INFLIGHT


def test_run_task_stream_parses_response_completed():
    """The stream-mode client must return the SAME {"ok": True, output} shape
    from the response.completed SSE envelope the blocking client gets."""
    from agentic_rag_mcp import hermes_client as hc

    envelope = {"type": "response.completed", "response": {
        "id": "resp_x", "status": "completed",
        "output": [{"id": "rs_1", "type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": "LAUNCH: SUCCESS"}]}],
    }}
    # parse helper under test: the SSE data-line walker
    body = envelope["response"]
    text = hc._extract_text(body)
    assert text == "LAUNCH: SUCCESS"


# ----------------------------------------------- turn timing (2026-11-09 bug)

class _FakeTime:
    """Deterministic clock for the stream loop — pops ticks in order, holds
    the last one when exhausted (later paths never re-read it)."""
    def __init__(self, ticks):
        self._ticks = list(ticks)
        self._last = 0.0

    def perf_counter(self):
        if self._ticks:
            self._last = self._ticks.pop(0)
        return self._last


class _StreamCfg:
    hermes_api_url = HERMES_BASE
    hermes_api_key = "test-key"
    hermes_timeout_s = 600.0


def test_timing_profile_orders_and_truncates_gaps():
    """every-steps-hold-long-time: the profile keeps only the top-3 gaps,
    descending by length — the benchmark must surface the minutes, not every
    sub-second pause."""
    from agentic_rag_mcp import hermes_client as hc
    gaps = [(2.0, 5.0, "b"), (30.0, 40.0, "big"),
            (3.0, 10.0, "c"), (20.0, 25.0, "mid")]
    t = hc._timing_profile(0.0, 1.5, 9, gaps)
    assert [g["gap_s"] for g in t["gaps"]] == [30.0, 20.0, 3.0]
    assert t["first_event_s"] == 1.5
    assert t["event_count"] == 9


def test_run_task_stream_records_timing_profile(monkeypatch):
    """every-steps-hold-long-time: the stream loop must stop discarding
    event arrivals — total, first-event latency, event count and the top
    gaps come back on the ok envelope. Fake clock makes the profile
    assertable EXACTLY, not loosely."""
    from agentic_rag_mcp import hermes_client as hc

    sse = "\n".join([
        'data: {"type": "response.created"}',
        'data: {"type": "response.output_text.delta", "delta": "STEP 1: focus OK"}',
        'data: {"type": "response.output_text.delta", "delta": "STEP 2: type OK"}',
        'data: {"type": "response.completed", "response": {"output_text": "LAUNCH: SUCCESS"}}',
        "data: [DONE]",
    ])
    # t0, one arrival per event (4), then the profile's total read
    ticks = [0.0, 0.5, 10.5, 10.6, 30.6, 31.0]
    monkeypatch.setattr(hc, "time", _FakeTime(ticks))
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(200, content=sse.encode())
        out = hc.run_task_stream(_StreamCfg(), "open chrome", "instr",
                                 540.0, "bench-1")
    assert out["ok"] is True and out["output"] == "LAUNCH: SUCCESS"
    t = out["timing"]
    assert t["total_s"] == 31.0
    assert t["first_event_s"] == 0.5
    assert t["event_count"] == 4
    assert t["gaps"] == [
        {"gap_s": 20.0, "at_s": 30.6, "event": "response.completed"},
        {"gap_s": 10.0, "at_s": 10.5,
         "event": "response.output_text.delta 'STEP 1: focus OK'"},
    ]


def test_cancelled_turn_still_carries_timing(monkeypatch):
    """A stopped turn is benchmarked too — the disconnect error envelope must
    carry the (empty) profile so Stop-path forensics have the same shape."""
    from agentic_rag_mcp import hermes_client as hc

    monkeypatch.setattr(hc, "time", _FakeTime([0.0, 0.4]))
    with _hermes_mock() as router:
        router.post("/v1/responses").mock(side_effect=httpx.ReadError("peer closed"))
        out = hc.run_task_stream(_StreamCfg(), "open chrome", "instr",
                                 540.0, "bench-2")
    assert out["ok"] is False
    assert "cancelled" in out["error"]
    assert out["timing"] == {"total_s": 0.4, "first_event_s": None,
                             "event_count": 0, "gaps": []}


def test_ok_launch_appends_timing_line_and_audits_duration(tmp_path, monkeypatch):
    """The tool surface: the result gains a TIMING line (the relay's only
    post-hoc view — Dify streams nothing mid-tool) and the audit entry gains
    duration_s + the timing profile."""
    sse = "\n".join([
        'data: {"type": "response.output_text.delta", "delta": "starting"}',
        'data: {"type": "response.completed", "response": {"output_text": '
        '"Started notepad.exe — new process observed.\\nLAUNCH: SUCCESS"}}',
        "data: [DONE]",
    ])
    with _hermes_mock() as router:
        router.post("/v1/responses").respond(200, content=sse.encode())
        srv = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_launch_app",
                   {"task": "open notepad", "conversation_id": "c-timing"})
    assert out["status"] == "ok"
    assert "TIMING: total" in out["result"]
    assert "events" in out["result"]
    entry = _last_audit_entry(tmp_path)
    assert entry["decision"] == "executed"
    assert entry["duration_s"] >= 0
    assert entry["timing"]["event_count"] == 2


def test_error_turn_audits_duration_too(tmp_path, monkeypatch):
    """Failed turns are benchmarked as well — an errored audit entry carries
    duration_s + timing (a zero-event transport failure still has a shape)."""
    with _hermes_mock() as router:
        router.post("/v1/responses").mock(side_effect=httpx.ReadTimeout("too slow"))
        srv = _server(tmp_path, monkeypatch)
        out = call(srv, "hermes_launch_app",
                   {"task": "open notepad", "conversation_id": "c-timing"})
    assert out["status"] == "error"
    assert "within" in out["reason"].lower()
    entry = _last_audit_entry(tmp_path)
    assert entry["decision"] == "error"
    assert "duration_s" in entry and "timing" in entry
