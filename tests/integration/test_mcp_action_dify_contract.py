"""Spec 047 T012: opt-in live Dify draft/next-turn-cancel contract probe.

Run from the repository root, never in ordinary CI::

    RUN_MCP_ACTION_DIFY_CONTRACT=1 .venv/bin/python -m pytest \
        tests/integration/test_mcp_action_dify_contract.py -q -s

Prerequisites (this file performs NONE of the setup/publish steps):

* The T009 sidecar and T010 chatflow are deployed and published, Dify's MCP tool
  cache contains ``mcp_action``, and the configured ``[dify].api_key`` belongs to
  the app under test. ``[dify].console_url``, ``console_email``, and
  ``console_password`` (or their documented ``DIFY_*`` overrides) are required
  for the read-only console fallback. Config is loaded only through
  ``load_config`` + ``deploy.config.resolve``; secrets are never printed.
* The exact installed printer ``Microsoft Print to PDF`` must be available for
  the draft's read-only target validation. Owner-approved scope is General-cloud
  plus Hermes only; General-local retains its original non-MCP-Action behavior.
  Each test creates a fresh Dify conversation. The lane/draft tests stop after a
  draft or cancel. The newline/yes regression confirms the already-active default
  printer only, so it cannot change the machine's default.
* Console fallback uses only GETs on the two explicit app IDs below:
  ``/apps/<id>/chat-messages`` and ``/apps/<id>/workflow-app-logs?detail=true``.
  No app-name lookup is used. To prove both deployed apps separately, run this
  file once with each app's API key in the existing secret config/environment.

Evidence and deterministic-routing limits:

* Tool evidence comes from streamed ``agent_thought``/``node_finished`` events,
  with the matching console workflow run's node executions as fallback. The
  response must equal the active agent's text and the shared ``honesty_check``
  result; otherwise the test fails rather than inferring guard coverage. If
  neither API exposes those shapes, the assertion includes raw, recursively
  credential-sanitized events/console payloads needed to adapt the parser.
* ``inputs.ai_model = cloud|local`` is the only supported lane selector. Dify
  has no supported input that deterministically selects General versus Hermes;
  the lane-specific prompt is therefore only a routing request. The test checks
  the actual agent node ID on BOTH turns. A mismatch is an explicit T012 STOP
  failure requesting an approved deterministic resolver, never a skip or a
  claimed lane pass. A console node-run is not substituted for the missing
  end-to-end route because it would not prove dialogue-count propagation.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from agentic_rag_mcp.config import load_config
from agentic_rag_mcp.deploy.config import DeployConfig, redact, resolve
from agentic_rag_mcp.deploy.dify_console import ConsoleError, DifyConsole
from agentic_rag_mcp.mcp_action.actions import ReviewedActions

APP_IDS = (
    "194e1edf-2eba-442c-b10b-231bebb79c37",
    "7863fbe2-47f8-48c9-b096-6f7da8536b08",
)
OFFER = "Do you want me to do it automatically for you?"
CANCEL_REASON = "No automatic action was performed."
PRINTER = "Microsoft Print to PDF"
CANCEL_QUERY = "no"
AGENT_NODES = {
    "general_cloud": "agentic_strategy",
    "hermes": "hermes_agent",
}
HONESTY_FAILURE = re.compile(r"\b(?:honesty|dispatch) check\s*:", re.IGNORECASE)
SENSITIVE_KEY = re.compile(
    r"(?:authorization|password|api[_-]?key|access[_-]?token|csrf|cookie|secret|credential|token)",
    re.IGNORECASE,
)
BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;\"']+")
DIFY_KEY = re.compile(r"\bapp-[A-Za-z0-9_-]{8,}")
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
TOOL_RESPONSE_WRAPPER = re.compile(
    r"\Atool response:\s*(\{.*\})\.\s*\Z", re.IGNORECASE | re.DOTALL
)
MAX_TOOL_RESPONSE_CHARS = 262_144
MISSING = object()

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MCP_ACTION_DIFY_CONTRACT") != "1",
    reason="opt-in live Dify probe: set RUN_MCP_ACTION_DIFY_CONTRACT=1",
)


@dataclass
class ToolCall:
    inputs: Any
    output: Any
    source: str
    tool_call_id: str = ""


@dataclass
class Turn:
    query: str
    answer: str = ""
    conversation_id: str = ""
    message_id: str = ""
    task_id: str = ""
    workflow_run_id: str = ""
    events: list[Any] = field(default_factory=list)
    calls: list[ToolCall] = field(default_factory=list)
    agent_texts: dict[str, str] = field(default_factory=dict)
    guard_results: list[str] = field(default_factory=list)
    console_payloads: list[Any] = field(default_factory=list)
    console_notes: list[str] = field(default_factory=list)
    evidence_app_id: str = ""


@pytest.fixture(scope="session")
def dcfg() -> DeployConfig:
    cfg = resolve(load_config())
    if not cfg.api_key:
        pytest.fail("T012 needs [dify].api_key or DIFY_API_KEY; no credential was printed")
    return cfg


@pytest.fixture(scope="session")
def console(dcfg: DeployConfig):
    dcfg.require_console()
    client = DifyConsole(dcfg)
    try:
        client.login()
    except ConsoleError as exc:
        pytest.fail(_safe_text(f"T012 console login failed: {exc}", dcfg))
    yield client
    client.client.close()


def _decoded(value: Any) -> Any:
    """Decode bounded Dify JSON/tool-response wrappers, preserving other text."""
    for _ in range(6):
        if isinstance(value, list):
            return [_decoded(child) for child in value]
        if isinstance(value, dict) and "tool_response" in value:
            value = value["tool_response"]
            continue
        if isinstance(value, dict) and "tool_responses" in value:
            responses = _decoded(value["tool_responses"])
            if isinstance(responses, list) and len(responses) == 1:
                value = responses[0]
                continue
            return responses
        if isinstance(value, str) and len(value) <= MAX_TOOL_RESPONSE_CHARS:
            text = value.strip()
            match = TOOL_RESPONSE_WRAPPER.fullmatch(text)
            candidate = match.group(1) if match else text
            try:
                value = json.loads(candidate)
                continue
            except json.JSONDecodeError:
                pass
        break
    return value


def _output_value(value: Any) -> Any:
    value = _decoded(value)
    for _ in range(4):
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
            continue
        if isinstance(value, dict) and "output" in value and (
            str(value.get("type") or "").upper() == "CALL"
            or "tool_call_name" in value
            or "tool_call_input" in value
        ):
            value = _decoded(value["output"])
            continue
        break
    return value


def _tool_name(value: Any) -> str:
    if isinstance(value, dict):
        value = next(
            (value[key] for key in ("tool_call_name", "tool", "tool_name", "tool_label")
             if value.get(key)),
            "",
        )
    return str(value or "").rsplit(":", 1)[-1]


def _extract_calls(payload: Any, source: str) -> list[ToolCall]:
    fragments: list[ToolCall] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if _tool_name(value) == "mcp_action":
                raw_input = next(
                    (value[key] for key in (
                        "tool_call_input", "tool_input", "input", "arguments", "args"
                    ) if key in value),
                    MISSING,
                )
                raw_output = next(
                    (value[key] for key in (
                        "tool_responses", "output", "observation", "tool_response"
                    ) if key in value),
                    MISSING,
                )
                inputs = _decoded(None if raw_input is MISSING else raw_input)
                if isinstance(inputs, list) and len(inputs) == 1:
                    inputs = _decoded(inputs[0])
                output = _output_value(None if raw_output is MISSING else raw_output)
                # Agent thoughts describe intended calls; only a parsed tool
                # response with a status is evidence of an actual invocation.
                if isinstance(output, dict) and isinstance(output.get("status"), str):
                    fragments.append(ToolCall(
                        inputs=inputs,
                        output=output,
                        source=source,
                        tool_call_id=str(value.get("tool_call_id") or ""),
                    ))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    calls: list[ToolCall] = []
    for fragment in fragments:
        match = None
        if fragment.tool_call_id:
            compatible = [
                call for call in calls
                if call.tool_call_id == fragment.tool_call_id
                and (call.inputs is None or fragment.inputs is None or call.inputs == fragment.inputs)
                and (call.output is None or fragment.output is None or call.output == fragment.output)
            ]
            if compatible:
                match = compatible[-1]
        elif fragment.inputs is None:
            # An ID-less output fragment is attachable only when exactly one
            # earlier call awaits output; guessing would merge distinct retries.
            compatible = [
                call for call in calls
                if not call.tool_call_id and call.inputs is not None and call.output is None
            ]
            if len(compatible) == 1:
                match = compatible[0]
        else:
            # Complete ID-less calls are never folded together: identical retry
            # arguments can still be separate real calls. Complementary fragments merge.
            compatible = [
                call for call in calls
                if not call.tool_call_id
                and call.inputs == fragment.inputs
                and (call.output is None or fragment.output is None)
            ]
            if len(compatible) == 1:
                match = compatible[0]
        if match is None:
            calls.append(fragment)
            continue
        if match.inputs is None:
            match.inputs = fragment.inputs
        if match.output is None:
            match.output = fragment.output
        if not match.tool_call_id:
            match.tool_call_id = fragment.tool_call_id
        match.source = "+".join(dict.fromkeys((match.source, fragment.source)))
    return calls


def _dedup_calls(calls: list[ToolCall]) -> list[ToolCall]:
    unique: list[ToolCall] = []
    for call in calls:
        duplicate = next(
            (
                existing
                for existing in unique
                if call.tool_call_id
                and existing.tool_call_id == call.tool_call_id
                and existing.inputs == call.inputs
                and existing.output == call.output
            ),
            None,
        )
        if duplicate is not None:
            duplicate.source = "+".join(dict.fromkeys((duplicate.source, call.source)))
        else:
            unique.append(call)
    return unique


def _capture_node(turn: Turn, data: dict[str, Any]) -> None:
    node_id = str(data.get("node_id") or data.get("id") or "")
    outputs = _decoded(data.get("outputs") or {})
    if not isinstance(outputs, dict):
        return
    if (
        node_id in AGENT_NODES.values()
        and isinstance(outputs.get("text"), str)
        and outputs["text"].strip()
    ):
        turn.agent_texts[node_id] = outputs["text"]
    if node_id == "honesty_check" and isinstance(outputs.get("result"), str):
        turn.guard_results.append(outputs["result"])


def _walk_dicts(payload: Any):
    if isinstance(payload, dict):
        yield payload
        for value in payload.values():
            yield from _walk_dicts(value)
    elif isinstance(payload, list):
        for value in payload:
            yield from _walk_dicts(value)


def _stream_turn(
    dcfg: DeployConfig,
    *,
    user: str,
    query: str,
    ai_model: str,
    conversation_id: str = "",
) -> Turn:
    turn = Turn(query=query, conversation_id=conversation_id)
    url = dcfg.console_url.rstrip("/") + "/v1/chat-messages"
    payload = {
        "inputs": {"ai_model": ai_model},
        "query": query,
        "response_mode": "streaming",
        "conversation_id": conversation_id,
        "user": user,
    }
    try:
        with httpx.stream(
            "POST",
            url,
            headers={"Authorization": f"Bearer {dcfg.api_key}"},
            json=payload,
            timeout=httpx.Timeout(600, connect=30),
        ) as response:
            if response.status_code != 200:
                body = _safe_text(response.read().decode("utf-8", "replace"), dcfg)
                raise AssertionError(
                    f"chat-messages returned HTTP {response.status_code}: {body[:2000]}"
                )
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].lstrip()
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    turn.events.append({"event": "_invalid_sse_json", "raw": raw})
                    continue
                turn.events.append(event)
                if not isinstance(event, dict):
                    continue
                turn.conversation_id = str(
                    event.get("conversation_id") or turn.conversation_id
                )
                turn.message_id = str(event.get("message_id") or turn.message_id)
                turn.task_id = str(event.get("task_id") or turn.task_id)
                for item in _walk_dicts(event):
                    if item.get("workflow_run_id"):
                        turn.workflow_run_id = str(item["workflow_run_id"])
                        break
                if event.get("event") in ("message", "agent_message"):
                    chunk = event.get("answer")
                    if isinstance(chunk, str):
                        turn.answer += chunk
                if event.get("event") == "node_finished":
                    data = event.get("data") or {}
                    if isinstance(data, dict):
                        _capture_node(turn, data)
                turn.calls.extend(_extract_calls(event, "stream"))
    except httpx.HTTPError as exc:
        raise AssertionError(
            _safe_text(f"chat-messages transport failed: {exc.__class__.__name__}: {exc}", dcfg)
        ) from None
    turn.calls = _dedup_calls(turn.calls)
    return turn


def _message_for_turn(messages: list[dict[str, Any]], turn: Turn) -> dict[str, Any] | None:
    if turn.message_id:
        match = next((item for item in messages if item.get("id") == turn.message_id), None)
        if match is not None:
            return match
    return next((item for item in messages if item.get("query") == turn.query), None)


def _read_console_turn(
    console: DifyConsole, app_id: str, turn: Turn, *, replace_tools: bool = True
) -> tuple[bool, str]:
    """Merge only the exact message/workflow run; return (conversation found, note)."""
    messages_body = console._get(  # existing read-only console client
        f"/apps/{app_id}/chat-messages",
        params={"conversation_id": turn.conversation_id, "limit": 20},
    )
    messages = messages_body.get("data") if isinstance(messages_body, dict) else messages_body
    if not isinstance(messages, list):
        return False, f"{app_id}: chat-messages shape had no data list"
    message = _message_for_turn(messages, turn)
    if message is None:
        return False, f"{app_id}: exact conversation/message not present"
    turn.evidence_app_id = app_id
    turn.console_payloads.append({"app_id": app_id, "message": message})
    if not turn.answer and isinstance(message.get("answer"), str):
        turn.answer = message["answer"]
    run_id = str(
        turn.workflow_run_id
        or message.get("workflow_run_id")
        or (message.get("workflow_run") or {}).get("id")
        or ""
    )
    turn.workflow_run_id = run_id
    if not run_id:
        return True, f"{app_id}: message has no workflow_run_id; cannot select a node run"
    logs_body = console._get(
        f"/apps/{app_id}/workflow-app-logs",
        params={"page": 1, "limit": 100, "detail": "true"},
    )
    logs = logs_body.get("data") if isinstance(logs_body, dict) else None
    if not isinstance(logs, list):
        return True, f"{app_id}: workflow-app-logs shape had no data list"
    detail = next(
        (
            item for item in logs
            if str((item.get("workflow_run") or {}).get("id") or "") == run_id
            or str(item.get("workflow_run_id") or "") == run_id
        ),
        None,
    )
    if detail is None:
        return True, f"{app_id}: no workflow-app-log exactly matched run {run_id}"
    turn.console_payloads.append({"app_id": app_id, "workflow_log": detail})
    console_calls = _dedup_calls(_extract_calls(detail, f"console:{app_id}"))
    if replace_tools and console_calls:
        # Keep one evidence source: mixing a complete streamed call with a
        # console invocation/process-data stub would look like a missing output.
        turn.calls = console_calls
    for item in _walk_dicts(detail):
        if "outputs" in item:
            _capture_node(turn, item)
    return True, f"{app_id}: exact workflow run detail merged"


def _enrich_from_console(console: DifyConsole, dcfg: DeployConfig, turn: Turn) -> None:
    replace_tools = not turn.calls or any(
        not isinstance(call.inputs, dict) or not isinstance(call.output, dict)
        for call in turn.calls
    )
    if not replace_tools and turn.agent_texts and turn.guard_results and turn.answer:
        return  # complete streamed evidence needs no duplicate console tool records
    if not turn.conversation_id:
        turn.console_notes.append("console fallback impossible: no conversation_id in stream")
        return
    for attempt in range(3):
        found = False
        for app_id in APP_IDS:  # explicit IDs only — deliberately no name lookup
            try:
                found, note = _read_console_turn(
                    console, app_id, turn, replace_tools=replace_tools
                )
                turn.console_notes.append(note)
                if found:
                    return
            except Exception as exc:  # noqa: BLE001 — diagnostics must sanitize every shape error
                turn.console_notes.append(_safe_text(f"{app_id}: {exc}", dcfg))
        if attempt < 2:
            time.sleep(1)  # console log writes can trail the completed SSE stream


def _sanitized(value: Any, dcfg: DeployConfig) -> Any:
    if isinstance(value, dict):
        return {
            str(key): ("***" if SENSITIVE_KEY.search(str(key)) else _sanitized(child, dcfg))
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_sanitized(child, dcfg) for child in value]
    if isinstance(value, tuple):
        return [_sanitized(child, dcfg) for child in value]
    if isinstance(value, bytes):
        return f"<{len(value)} bytes omitted>"
    if isinstance(value, str):
        return _safe_text(value, dcfg)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _safe_text(str(value), dcfg)


def _safe_text(text: str, dcfg: DeployConfig) -> str:
    text = redact(text, dcfg.secrets)
    text = BEARER.sub("Bearer ***", text)
    text = DIFY_KEY.sub("app-***", text)
    return JWT.sub("***", text)


def _diagnostics(turn: Turn, dcfg: DeployConfig) -> str:
    evidence = {
        "query": turn.query,
        "answer": turn.answer,
        "conversation_id": turn.conversation_id,
        "message_id": turn.message_id,
        "task_id": turn.task_id,
        "workflow_run_id": turn.workflow_run_id,
        "evidence_app_id": turn.evidence_app_id,
        "agent_texts": turn.agent_texts,
        "guard_results": turn.guard_results,
        "tool_calls": [call.__dict__ for call in turn.calls],
        "console_notes": turn.console_notes,
    }
    if os.environ.get("MCP_ACTION_DIFY_DEBUG") == "1":
        evidence["console_payloads"] = turn.console_payloads
        evidence["raw_events"] = turn.events
    rendered = json.dumps(_sanitized(evidence, dcfg), indent=2, ensure_ascii=False, default=str)
    return "\nSANITIZED T012 EVIDENCE (credentials/tokens replaced):\n" + rendered


def _require(condition: bool, message: str, turn: Turn, dcfg: DeployConfig) -> None:
    if not condition:
        detail = _diagnostics(turn, dcfg) if os.environ.get("MCP_ACTION_DIFY_DEBUG") == "1" else ""
        raise AssertionError(message + detail)


def _assert_guard(turn: Turn, lane: str | None, dcfg: DeployConfig) -> None:
    if lane is None:
        _require(
            len(turn.agent_texts) == 1,
            f"Cancel must have exactly one active answering agent; observed {sorted(turn.agent_texts)}.",
            turn,
            dcfg,
        )
        expected = next(iter(turn.agent_texts), "")
    else:
        expected = AGENT_NODES[lane]
        _require(
            expected in turn.agent_texts,
            f"T012 STOP: requested {lane}, but {expected} produced no observed answer. "
            "General versus Hermes is not deterministically selectable through supported inputs; "
            "request owner approval for a deterministic resolver instead of claiming coverage.",
            turn,
            dcfg,
        )
    unrelated = sorted(set(turn.agent_texts) - {expected})
    _require(
        not unrelated,
        f"Unrelated answering agent node(s) also produced text: {unrelated}; "
        "multi-upstream guard selection is not isolated.",
        turn,
        dcfg,
    )
    _require(bool(turn.guard_results), "No honesty_check node result was exposed.", turn, dcfg)
    active = turn.agent_texts[expected]
    guard = turn.guard_results[-1]
    _require(
        not HONESTY_FAILURE.search(turn.answer),
        "Final answer is an honesty/dispatch failure replacement.",
        turn,
        dcfg,
    )
    _require(
        guard == active,
        "honesty_check did not return the active agent answer verbatim (possible substitution).",
        turn,
        dcfg,
    )
    _require(
        turn.answer == guard,
        "Final streamed/stored answer differs from honesty_check.result.",
        turn,
        dcfg,
    )


def _phase(call: ToolCall) -> Any:
    return call.inputs.get("phase") if isinstance(call.inputs, dict) else None


def _assert_no_confirm(turn: Turn, dcfg: DeployConfig) -> None:
    _require(
        all(_phase(call) != "confirm" for call in turn.calls),
        "SAFETY: a confirm call was observed; this harness permits draft/cancel only.",
        turn,
        dcfg,
    )


def _assert_draft(turn: Turn, lane: str, dcfg: DeployConfig) -> int:
    _assert_no_confirm(turn, dcfg)
    calls = [call for call in turn.calls if _phase(call) == "draft"]
    _require(bool(calls), "No mcp_action draft input was captured.", turn, dcfg)
    exact_parameters = {"printer": PRINTER}
    for call in calls:
        _require(isinstance(call.inputs, dict), "Draft tool input is not an object.", turn, dcfg)
        _require(
            call.inputs.get("conversation_id") == turn.conversation_id,
            "Draft conversation_id differs from the actual Dify conversation.",
            turn,
            dcfg,
        )
        _require(call.inputs.get("query") == turn.query, "Draft query was not raw sys.query.", turn, dcfg)
        _require(
            call.inputs.get("action_id") == "windows_default_printer",
            "Draft action_id was substituted.",
            turn,
            dcfg,
        )
        parameters = call.inputs.get("parameters", MISSING)
        count = call.inputs.get("dialogue_count")
        _require(type(count) is int and count >= 0, "Draft dialogue_count is not numeric.", turn, dcfg)
        _require(isinstance(call.output, dict), "A draft tool output was absent or not parsed JSON.", turn, dcfg)
        status = call.output.get("status")
        _require(
            status in ("ask-back", "error", "pending-confirmation"),
            f"Draft retry had forbidden status {status!r}.",
            turn,
            dcfg,
        )
        if status == "pending-confirmation":
            _require(
                parameters == exact_parameters,
                "A pending draft omitted or changed the exact parameters.",
                turn,
                dcfg,
            )
            _require(call.output.get("offer") == OFFER, "Draft returned a different offer.", turn, dcfg)
            _require(call.output.get("expires_in_s") == 900, "Draft TTL was not 900 seconds.", turn, dcfg)
    counts = {call.inputs["dialogue_count"] for call in calls}
    _require(len(counts) == 1, f"Conflicting draft dialogue counts: {sorted(counts)}", turn, dcfg)
    _require(
        calls[-1].output.get("status") == "pending-confirmation",
        "The final draft retry did not produce the exact pending offer.",
        turn,
        dcfg,
    )
    _require(OFFER in turn.answer, "Final draft answer omitted the exact pending offer.", turn, dcfg)
    _assert_guard(turn, lane, dcfg)
    return counts.pop()


def _assert_cancel(turn: Turn, lane: str, draft_count: int, dcfg: DeployConfig) -> None:
    _assert_no_confirm(turn, dcfg)
    calls = [call for call in turn.calls if _phase(call) == "cancel"]
    _require(bool(calls), "No mcp_action cancel input was captured on the immediate next turn.", turn, dcfg)
    for call in calls:
        _require(isinstance(call.inputs, dict), "Cancel tool input is not an object.", turn, dcfg)
        _require(
            call.inputs.get("conversation_id") == turn.conversation_id,
            "Cancel conversation_id differs from the draft conversation.",
            turn,
            dcfg,
        )
        _require(call.inputs.get("query") == CANCEL_QUERY, "Cancel query was not raw 'no'.", turn, dcfg)
        _require(
            type(call.inputs.get("dialogue_count")) is int
            and call.inputs["dialogue_count"] == draft_count + 1,
            f"Cancel dialogue_count must be numeric N+1 ({draft_count + 1}).",
            turn,
            dcfg,
        )
        _require(isinstance(call.output, dict), "A cancel tool output was absent or not parsed JSON.", turn, dcfg)
        status = call.output.get("status")
        _require(
            status in ("error", "cancelled"),
            f"Cancel retry had forbidden status {status!r}.",
            turn,
            dcfg,
        )
        if status == "cancelled":
            _require(
                call.inputs.get("action_id") in (None, ""),
                "Successful cancel supplied a replacement action_id.",
                turn,
                dcfg,
            )
            _require(
                call.inputs.get("parameters") is None,
                "Successful cancel supplied replacement parameters.",
                turn,
                dcfg,
            )
            _require(call.output.get("reason") == CANCEL_REASON, "Cancel reason differed from the contract.", turn, dcfg)
    _require(
        calls[-1].output.get("status") == "cancelled",
        "The final cancel retry did not cancel the pending proposal.",
        turn,
        dcfg,
    )
    _assert_guard(turn, None, dcfg)


def _draft_query(lane: str) -> str:
    prefix = (
        "For the Hermes Local Agent on my Windows computer: "
        if lane == "hermes"
        else "For a written Windows how-to answer, not a PowerShell, file, launch, or Office task: "
    )
    return (
        prefix
        + f"the exact target printer is {PRINTER}. Give tailored manual steps for making it "
        "the default printer, then create the reviewed mcp_action draft for "
        "windows_default_printer. The request is complete; do not ask for more context, "
        "and do not confirm or execute anything."
    )


def test_raw_query_with_newline_reaches_agent_without_tool_json_crash():
    """Regression: Dify serializes tool definitions before variable resolution.

    Template constants containing raw sys.query produced invalid JSON when the
    follow-up had a newline, collapsing the tool list to a string and crashing
    build_parameters. Native auto variable selectors resolve after parsing.
    """
    dcfg = resolve(load_config())
    actions = ReviewedActions()
    validation = asyncio.run(actions.validate_default_printer(PRINTER))
    target = validation.get("current_default")
    assert target, "could not read the current default printer"
    user = f"mcp-newline-yes-regression-{uuid.uuid4().hex}"
    first = _stream_turn(
        dcfg,
        user=user,
        ai_model="cloud",
        query=f"how to change my default printer to {target} on Windows 11",
    )
    reply = f"Q1. default: {target}\nQ2. already installed"
    second = _stream_turn(
        dcfg,
        user=user,
        ai_model="cloud",
        conversation_id=first.conversation_id,
        query=reply,
    )
    assert second.answer.strip(), "Dify returned an empty answer after the newline reply"
    drafts = [call for call in second.calls if call.inputs.get("phase") == "draft"]
    pending = [call for call in drafts if call.output.get("status") == "pending-confirmation"]
    assert pending, "no pending proposal; newline query did not reach mcp_action"
    assert any(
        call.inputs.get("query") == reply
        and call.inputs.get("conversation_id") == first.conversation_id
        and type(call.inputs.get("dialogue_count")) is int
        for call in pending
    ), "runtime variable selectors did not deliver the exact raw query/conversation/turn"

    yes_query = "yes, help to do it"
    confirmed = _stream_turn(
        dcfg,
        user=user,
        ai_model="cloud",
        conversation_id=first.conversation_id,
        query=yes_query,
    )
    assert "Honesty check:" not in confirmed.answer, confirmed.answer
    yes_drafts = [
        call
        for call in confirmed.calls
        if call.inputs.get("phase") == "draft"
        and call.output.get("status") == "pending-confirmation"
    ]
    assert not yes_drafts, "a yes turn replaced the pending proposal instead of confirming it"
    confirms = [call for call in confirmed.calls if call.inputs.get("phase") == "confirm"]
    assert any(
        call.inputs.get("query") == yes_query
        and call.inputs.get("conversation_id") == first.conversation_id
        and call.output.get("verification") == "verified"
        and call.output.get("display", {}).get("status") == "displayed"
        for call in confirms
    ), "the affirmative turn did not confirm the stored proposal"
    after = asyncio.run(actions.validate_default_printer(target))
    assert after.get("current_default") == target, "the already-active default changed unexpectedly"


@pytest.mark.parametrize("lane", tuple(AGENT_NODES))
def test_mcp_action_draft_then_immediate_cancel(
    lane: str, dcfg: DeployConfig, console: DifyConsole
) -> None:
    user = f"t012-{lane}-{uuid.uuid4().hex}"
    draft_query = _draft_query(lane)
    draft = _stream_turn(
        dcfg, user=user, query=draft_query, ai_model="local" if lane == "general_local" else "cloud"
    )
    _require(bool(draft.conversation_id), "Draft stream exposed no conversation_id.", draft, dcfg)

    # No intervening user turn and no assertion-only early exit: every dispatched
    # draft gets its non-mutating cancel opportunity on the immediately next turn.
    cancel = _stream_turn(
        dcfg,
        user=user,
        query=CANCEL_QUERY,
        ai_model="local" if lane == "general_local" else "cloud",
        conversation_id=draft.conversation_id,
    )
    _require(
        cancel.conversation_id == draft.conversation_id,
        "Dify changed conversation_id between draft and cancel.",
        cancel,
        dcfg,
    )

    # Public streaming is sufficient on some Dify versions; console node detail
    # fills agent-thought/guard gaps on others. These are read-only requests.
    _enrich_from_console(console, dcfg, draft)
    _enrich_from_console(console, dcfg, cancel)
    try:
        count = _assert_draft(draft, lane, dcfg)
        _assert_cancel(cancel, lane, count, dcfg)
    except AssertionError as exc:
        if "SANITIZED T012 EVIDENCE" in str(exc):
            raise
        raise AssertionError(_safe_text(str(exc), dcfg) + _diagnostics(cancel, dcfg)) from None

    print(
        f"T012 {lane}: app_candidates={','.join(APP_IDS)} "
        f"evidence_app={draft.evidence_app_id or 'stream-only'} "
        f"conversation={draft.conversation_id} dialogue_count={count}->{count + 1} "
        "draft=pending cancel=cancelled guard=active-agent-only"
    )
