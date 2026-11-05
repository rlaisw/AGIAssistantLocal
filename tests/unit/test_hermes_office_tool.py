"""Unit: the hermes_office_task MCP tool wrapper (spec 030, contract §1–§4).

Failing-first: written before the tool exists. The Hermes client is mocked —
blocked verdicts never reach it; the STEP/TASK marker protocol drives
per-step audit and the honest envelope; confirm-before-send resolves only
against the recorded pending draft; failures map to honest errors.
"""

from __future__ import annotations

import asyncio
import json

from agentic_rag_mcp.config import Config
from agentic_rag_mcp.server import build_server

ROOT = "C:\\OfficeMCP"


def call(server, name, args):
    raw = asyncio.run(server.call_tool(name, args))
    texts = [getattr(b, "text", "") for b in raw if getattr(b, "text", "")]
    joined = "".join(texts).strip()
    return json.loads(joined) if joined else None


def _server(tmp_path, monkeypatch, agent_reply=None, calls=None):
    import agentic_rag_mcp.server as server_mod
    import agentic_rag_mcp.hermes_client as hc

    monkeypatch.setattr(server_mod, "build_providers", lambda cfg: [])
    monkeypatch.setattr(server_mod, "Embedder", lambda model, device: object())

    def fake_run_task(cfg, task, instructions=""):
        if calls is not None:
            calls.append({"task": task, "instructions": instructions})
        if isinstance(agent_reply, Exception):
            raise agent_reply
        return {"ok": True, "output": agent_reply}

    monkeypatch.setattr(hc, "run_task", fake_run_task)
    from agentic_rag_mcp.office_state import OfficeState
    fresh = OfficeState()
    monkeypatch.setattr(server_mod, "get_office_state", lambda: fresh)

    cfg = Config(state_db=tmp_path / "s.sqlite3", vector_dir=tmp_path / "v",
                 decider_enabled=False,
                 hermes_api_url="http://hermes.test:8642",
                 hermes_api_key="test-key",
                 hermes_timeout_s=5.0,
                 hermes_audit_path=tmp_path / "audit.jsonl",
                 hermes_office_root=ROOT)
    return build_server(cfg), cfg


def _audit(tmp_path):
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    return [json.loads(x) for x in lines if x.strip()]


# ------------------------------------------------------------------ blocked

def test_blocked_never_calls_agent_and_audits(tmp_path, monkeypatch):
    calls = []
    srv, cfg = _server(tmp_path, monkeypatch, calls=calls)
    out = call(srv, "hermes_office_task",
               {"task": "create a macro that formats the sheet",
                "conversation_id": "c1"})
    assert out["status"] == "blocked"
    assert "literal" in out["reason"].lower()
    assert calls == []                                  # nothing reached the agent
    entries = _audit(tmp_path)
    assert entries[-1]["decision"] == "blocked"
    assert entries[-1]["operation"] == "office-task"
    assert entries[-1]["allowed_root"] == ROOT           # the lane's discriminator


def test_compose_without_address_asks_back(tmp_path, monkeypatch):
    calls = []
    srv, cfg = _server(tmp_path, monkeypatch, calls=calls)
    out = call(srv, "hermes_office_task",
               {"task": "write an email saying hello", "conversation_id": "c1"})
    assert out["status"] == "blocked"
    assert "address" in out["reason"].lower()
    assert calls == []


# ------------------------------------------------------------- happy path

def test_document_write_step_protocol_and_state(tmp_path, monkeypatch):
    calls = []
    reply = ("STEP 1: open OK — Excel is running with a new workbook\n"
             "STEP 2: write OK — wrote 12345 to A1\n"
             "ACTIVE FILE: C:\\OfficeMCP\\book1.xlsx\n"
             "TASK: COMPLETED")
    srv, cfg = _server(tmp_path, monkeypatch, agent_reply=reply, calls=calls)
    out = call(srv, "hermes_office_task",
               {"task": "open Excel and put 12345 in cell A1",
                "conversation_id": "c1"})
    assert out["status"] == "ok"
    assert out["decision"] == "executed"
    assert out["active_file"] == "C:\\OfficeMCP\\book1.xlsx"
    assert "STEP 2" in out["result"]
    # directive carries containment + literal rules
    assert "C:\\OfficeMCP" in calls[0]["task"]
    # per-step audit + the active document state updated
    entries = [e for e in _audit(tmp_path) if e["operation"] == "office-task"]
    assert [e["decision"] for e in entries] == ["executed", "executed"]
    import agentic_rag_mcp.server as server_mod
    st = server_mod.get_office_state()
    assert st.active_document("c1") == "C:\\OfficeMCP\\book1.xlsx"


def test_followup_uses_active_document(tmp_path, monkeypatch):
    calls = []
    reply = ("STEP 1: write OK — wrote hello to B2\n"
             "ACTIVE FILE: C:\\OfficeMCP\\book1.xlsx\n"
             "TASK: COMPLETED")
    srv, cfg = _server(tmp_path, monkeypatch, agent_reply=reply, calls=calls)
    import agentic_rag_mcp.server as server_mod
    server_mod.get_office_state().set_active_document(
        "c1", "C:\\OfficeMCP\\book1.xlsx")         # a prior turn wrote this file
    out = call(srv, "hermes_office_task",
               {"task": "also write 'hello' in B2", "conversation_id": "c1"})
    assert out["status"] == "ok"
    assert "book1.xlsx" in calls[0]["task"]       # directive names the active doc


def test_partial_failure_is_honest_error(tmp_path, monkeypatch):
    reply = ("STEP 1: open OK — Excel running\n"
             "STEP 2: write FAILED — cannot reach the sheet\n"
             "TASK: PARTIAL")
    srv, cfg = _server(tmp_path, monkeypatch, agent_reply=reply)
    out = call(srv, "hermes_office_task",
               {"task": "open Excel and put 12345 in cell A1",
                "conversation_id": "c1"})
    assert out["status"] == "error"
    assert "PARTIAL" in out["reason"]
    assert "write FAILED" in out["reason"]
    entries = [e for e in _audit(tmp_path) if e["operation"] == "office-task"]
    assert [e["decision"] for e in entries] == ["executed", "error"]


def test_missing_task_marker_is_error_never_ok(tmp_path, monkeypatch):
    srv, cfg = _server(tmp_path, monkeypatch, agent_reply="done, probably")
    out = call(srv, "hermes_office_task",
               {"task": "open Excel and put 12345 in cell A1",
                "conversation_id": "c1"})
    assert out["status"] == "error"
    assert "TASK" in out["reason"]                  # honest: no completion marker


# ------------------------------------------------------- email + confirm flow

def test_compose_records_pending_and_never_sends(tmp_path, monkeypatch):
    calls = []
    reply = ("STEP 1: compose OK — draft created in Outlook Drafts\n"
             "DRAFT ID: EID-77\n"
             "TASK: COMPLETED")
    srv, cfg = _server(tmp_path, monkeypatch, agent_reply=reply, calls=calls)
    out = call(srv, "hermes_office_task",
               {"task": "send an email to a@b.com saying 'test Hello World'",
                "conversation_id": "c1"})
    assert out["status"] == "ok"
    assert out["draft_pending"] is True
    assert "EID-77" in out["result"] or "draft" in out["result"].lower()
    assert "never send" in calls[0]["instructions"].lower() + calls[0]["task"].lower()
    import agentic_rag_mcp.server as server_mod
    assert server_mod.get_office_state().pending_draft("c1")["entry_id"] == "EID-77"


def test_compose_without_draft_id_line_still_registers_pending(tmp_path, monkeypatch):
    """Robustness (2026-11-03): a completed compose whose report lacks a
    DRAFT ID line still registers the pending draft (entry_id None); the
    confirm directive then locates the draft by content, never 'None'."""
    import agentic_rag_mcp.hermes_client as hc
    import agentic_rag_mcp.server as server_mod

    calls = []
    compose = ("STEP 1: compose OK — draft created and saved in Drafts\n"
               "TASK: COMPLETED")          # no DRAFT ID line
    send = ("STEP 1: send OK — sent exactly as composed\nTASK: COMPLETED")
    replies = iter([compose, send])

    def fake_run_task(cfg, task, instructions=""):
        calls.append(task)
        return {"ok": True, "output": next(replies)}

    monkeypatch.setattr(server_mod, "build_providers", lambda cfg: [])
    monkeypatch.setattr(server_mod, "Embedder", lambda m, d: object())
    monkeypatch.setattr(hc, "run_task", fake_run_task)
    from agentic_rag_mcp.office_state import OfficeState
    fresh = OfficeState()
    monkeypatch.setattr(server_mod, "get_office_state", lambda: fresh)
    cfg = Config(state_db=tmp_path / "s.sqlite3", vector_dir=tmp_path / "v",
                 decider_enabled=False, hermes_audit_path=tmp_path / "audit.jsonl",
                 hermes_office_root=ROOT)
    srv = build_server(cfg)
    out1 = call(srv, "hermes_office_task",
                {"task": "send an email to rlaisw@gmail.com saying 'Hello'",
                 "conversation_id": "c1"})
    assert out1["status"] == "ok"
    assert out1["draft_pending"] is True                    # registered anyway
    st = server_mod.get_office_state()
    assert st.pending_draft("c1")["entry_id"] is None
    out2 = call(srv, "hermes_office_task", {"task": "send it", "conversation_id": "c1"})
    assert out2["status"] == "ok"
    assert "None" not in calls[1]                            # never 'SEND PENDING DRAFT None'
    assert "Drafts folder" in calls[1]                       # locate-by-content directive
    assert "rlaisw@gmail.com" in calls[1]                    # the composed context carries the address


def test_confirmation_sends_recorded_entry_id(tmp_path, monkeypatch):
    import agentic_rag_mcp.hermes_client as hc
    import agentic_rag_mcp.server as server_mod

    calls = []
    compose = ("STEP 1: compose OK\nDRAFT ID: EID-77\nTASK: COMPLETED")
    send = ("STEP 1: send OK — sent exactly as composed\nTASK: COMPLETED")
    replies = iter([compose, send])

    def fake_run_task(cfg, task, instructions=""):
        calls.append(task)
        return {"ok": True, "output": next(replies)}

    monkeypatch.setattr(server_mod, "build_providers", lambda cfg: [])
    monkeypatch.setattr(server_mod, "Embedder", lambda m, d: object())
    monkeypatch.setattr(hc, "run_task", fake_run_task)
    from agentic_rag_mcp.office_state import OfficeState
    fresh = OfficeState()
    monkeypatch.setattr(server_mod, "get_office_state", lambda: fresh)
    cfg = Config(state_db=tmp_path / "s.sqlite3", vector_dir=tmp_path / "v",
                 decider_enabled=False, hermes_audit_path=tmp_path / "audit.jsonl",
                 hermes_office_root=ROOT)
    srv = build_server(cfg)
    call(srv, "hermes_office_task",
         {"task": "send an email to a@b.com saying 'hi'", "conversation_id": "c1"})
    out = call(srv, "hermes_office_task", {"task": "send it", "conversation_id": "c1"})
    assert out["status"] == "ok"
    assert fresh.pending_draft("c1") is None          # resolved
    assert len(calls) == 2
    # the send directive carried the recorded EntryID — the draft shown is the draft sent
    assert "EID-77" in calls[1]
    assert "do not modify" in calls[1].lower()


def test_confirmation_without_pending_asks_back(tmp_path, monkeypatch):
    calls = []
    srv, cfg = _server(tmp_path, monkeypatch, calls=calls)
    out = call(srv, "hermes_office_task", {"task": "send it", "conversation_id": "c9"})
    assert out["status"] == "blocked"
    assert "no email is waiting" in (out["reason"] or "").lower()
    assert calls == []


def test_cancel_drops_pending_without_agent(tmp_path, monkeypatch):
    calls = []
    srv, cfg = _server(tmp_path, monkeypatch, calls=calls)
    import agentic_rag_mcp.server as server_mod
    st = server_mod.get_office_state()
    st.set_pending_draft("c1", {"entry_id": "EID-1", "recipients": "a@b.com",
                                "subject": "s", "body": "b"})
    out = call(srv, "hermes_office_task", {"task": "cancel that email",
                                           "conversation_id": "c1"})
    assert out["status"] == "ok"
    assert st.pending_draft("c1") is None
    assert calls == []                                  # pure state op — no agent
    entries = [e for e in _audit(tmp_path) if e["operation"] == "office-task"]
    assert entries[-1]["decision"] == "executed"


# --------------------------------------------------- resume path (FR-005)

def test_partial_stores_interrupted_and_continue_resumes(tmp_path, monkeypatch):
    import agentic_rag_mcp.hermes_client as hc
    import agentic_rag_mcp.server as server_mod

    calls = []
    replies = iter([
        "STEP 1: open OK — Excel running\nSTEP 2: write FAILED — no sheet\nTASK: PARTIAL",
        "STEP 1: write OK — wrote 12345 to A1\nTASK: COMPLETED",
    ])

    def fake_run_task(cfg, task, instructions=""):
        calls.append(task)
        return {"ok": True, "output": next(replies)}

    monkeypatch.setattr(server_mod, "build_providers", lambda cfg: [])
    monkeypatch.setattr(server_mod, "Embedder", lambda m, d: object())
    monkeypatch.setattr(hc, "run_task", fake_run_task)
    from agentic_rag_mcp.office_state import OfficeState
    fresh = OfficeState()
    monkeypatch.setattr(server_mod, "get_office_state", lambda: fresh)
    cfg = Config(state_db=tmp_path / "s.sqlite3", vector_dir=tmp_path / "v",
                 decider_enabled=False, hermes_audit_path=tmp_path / "audit.jsonl",
                 hermes_office_root=ROOT)
    srv = build_server(cfg)
    out1 = call(srv, "hermes_office_task",
                {"task": "open Excel and put 12345 in cell A1",
                 "conversation_id": "c1"})
    assert out1["status"] == "error"                    # honest partial
    assert fresh.interrupted("c1") is not None           # resumable state stored
    out2 = call(srv, "hermes_office_task",
                {"task": "continue", "conversation_id": "c1"})
    assert out2["status"] == "ok"
    assert "12345" in calls[1]                           # resume carries the task
    assert "PARTIAL" in calls[1]                         # plus the partial context
    assert fresh.interrupted("c1") is None               # cleared on completion


def test_continue_with_nothing_pending_asks_back(tmp_path, monkeypatch):
    calls = []
    srv, cfg = _server(tmp_path, monkeypatch, calls=calls)
    out = call(srv, "hermes_office_task", {"task": "continue", "conversation_id": "c9"})
    assert out["status"] == "blocked"
    assert "resume" in (out["reason"] or "").lower()
    assert calls == []                                   # no agent call, honest ask-back


# --------------------------------------------------------------- error paths

def test_service_down_honest_error_with_start_hint(tmp_path, monkeypatch):
    import agentic_rag_mcp.hermes_client as hc
    import agentic_rag_mcp.server as server_mod
    monkeypatch.setattr(server_mod, "build_providers", lambda cfg: [])
    monkeypatch.setattr(server_mod, "Embedder", lambda m, d: object())
    monkeypatch.setattr(hc, "run_task",
                        lambda cfg, task, instructions="": {"ok": False, "error": "error:OfficeMCP unreachable"})
    from agentic_rag_mcp.office_state import OfficeState
    monkeypatch.setattr(server_mod, "get_office_state", lambda: OfficeState())
    cfg = Config(state_db=tmp_path / "s.sqlite3", vector_dir=tmp_path / "v",
                 decider_enabled=False, hermes_audit_path=tmp_path / "audit.jsonl",
                 hermes_office_root=ROOT)
    srv = build_server(cfg)
    out = call(srv, "hermes_office_task",
               {"task": "open Excel and put 12345 in cell A1", "conversation_id": "c1"})
    assert out["status"] == "error"
    assert "officemcp sse" in out["reason"].lower()   # the exact start command hint
    entries = [e for e in _audit(tmp_path) if e["operation"] == "office-task"]
    assert entries[-1]["decision"] == "error"


# ------------------------------------------------- save-anywhere (spec 031)

def test_named_location_rides_the_directive(tmp_path, monkeypatch):
    import agentic_rag_mcp.hermes_client as hc
    import agentic_rag_mcp.server as server_mod

    calls = []

    def fake_run_task(cfg, task, instructions=""):
        calls.append(task)
        return {"ok": True, "output":
                "STEP 1: save OK — saved at the named location\n"
                "ACTIVE FILE: /mnt/d/projects/report.docx\n"
                "TASK: COMPLETED"}

    monkeypatch.setattr(server_mod, "build_providers", lambda cfg: [])
    monkeypatch.setattr(server_mod, "Embedder", lambda m, d: object())
    monkeypatch.setattr(hc, "run_task", fake_run_task)
    from agentic_rag_mcp.office_state import OfficeState
    fresh = OfficeState()
    monkeypatch.setattr(server_mod, "get_office_state", lambda: fresh)
    cfg = Config(state_db=tmp_path / "s.sqlite3", vector_dir=tmp_path / "v",
                 decider_enabled=False, hermes_audit_path=tmp_path / "audit.jsonl",
                 hermes_office_root=ROOT)
    srv = build_server(cfg)
    out = call(srv, "hermes_office_task",
               {"task": "create a Word document with the text 'notes' and "
                        "save it to D:\\projects\\report.docx",
                "conversation_id": "c1"})
    assert out["status"] == "ok", out
    assert "D:\\projects\\report.docx" in calls[0]
    assert fresh.active_document("c1") == "/mnt/d/projects/report.docx"
    # the audit records the ACTUAL target (031 FR-006)
    assert _audit(tmp_path)[-1]["normalized_path"] == "/mnt/d/projects/report.docx"


def test_os_permission_error_relayed(tmp_path, monkeypatch):
    import agentic_rag_mcp.hermes_client as hc
    import agentic_rag_mcp.server as server_mod
    monkeypatch.setattr(server_mod, "build_providers", lambda cfg: [])
    monkeypatch.setattr(server_mod, "Embedder", lambda m, d: object())
    monkeypatch.setattr(hc, "run_task",
                        lambda cfg, task, instructions="":
                        {"ok": True, "output":
                         "STEP 1: save FAILED — [Errno 13] Permission denied: "
                         "'C:\\Windows\\system32\\config.sys'\nTASK: FAILED"})
    from agentic_rag_mcp.office_state import OfficeState
    monkeypatch.setattr(server_mod, "get_office_state", lambda: OfficeState())
    cfg = Config(state_db=tmp_path / "s.sqlite3", vector_dir=tmp_path / "v",
                 decider_enabled=False, hermes_audit_path=tmp_path / "audit.jsonl",
                 hermes_office_root=ROOT)
    srv = build_server(cfg)
    out = call(srv, "hermes_office_task",
               {"task": "save a file at C:\\Windows\\System32\\probe.txt",
                "conversation_id": "c1"})
    assert out["status"] == "error"
    assert "Permission denied" in out["reason"]      # the OS error relayed verbatim
    assert _audit(tmp_path)[-1]["decision"] == "error"


def test_office_instructions_contain_attach_failure_protocol():
    """only-one-version-of-outlook recurrence (2026-11-05): when Outlook's
    process runs but its COM server is unreachable, the agent must NEVER
    Launch again (dialog risk) and must offer exactly two consent paths.
    Guards the instruction text against silent removal."""
    from agentic_rag_mcp.hermes_client import OFFICE_INSTRUCTIONS

    assert "OUTLOOK ATTACH-FAILURE PROTOCOL" in OFFICE_INSTRUCTIONS
    assert "0x800401E3" in OFFICE_INSTRUCTIONS and "0x80080005" in OFFICE_INSTRUCTIONS
    assert "NEVER call Launch again" in OFFICE_INSTRUCTIONS
    assert "'restart Outlook'" in OFFICE_INSTRUCTIONS
    assert "taskkill /IM outlook.exe /F" in OFFICE_INSTRUCTIONS
    assert "never be killed silently" in OFFICE_INSTRUCTIONS
    # the pre-existing legs stay (Nov-4 fix + session-degradation rule)
    assert "try Dispatch/GetComObject" in OFFICE_INSTRUCTIONS
    assert "SESSION-DEGRADATION RULE" in OFFICE_INSTRUCTIONS
    # the-tool-call-failed (2026-11-05): the strip window is TIME-based — the
    # rule must teach WAITING (never a reset, which re-arms the window), cap
    # canaries at 3, and probe outlook.exe before any Launch
    assert "TIME-based" in OFFICE_INSTRUCTIONS or "time-window aware" in OFFICE_INSTRUCTIONS
    assert "up to 3 tiny canaries" in OFFICE_INSTRUCTIONS
    assert "WAIT about 15 minutes" in OFFICE_INSTRUCTIONS
    assert "re-arms" in OFFICE_INSTRUCTIONS
    assert "hermes mcp remove" not in OFFICE_INSTRUCTIONS  # reset hint removed
    assert "OUTLOOK LAUNCH GUARD" in OFFICE_INSTRUCTIONS
    assert "process-probe outlook.exe" in OFFICE_INSTRUCTIONS
