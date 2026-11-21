"""Contract tests: realistic failure modes reconciliation with contracts/mcp-tools.md."""

import asyncio

import pytest

from agentic_rag_mcp.config import Config
from agentic_rag_mcp.server import build_server


def call(server, name, args):
    import json
    raw = asyncio.run(server.call_tool(name, args))
    # FastMCP v1 returns a list mixing text blocks and structured results
    structured = [b["result"] for b in raw if isinstance(b, dict) and "result" in b]
    if structured:
        return structured[0]
    texts = [getattr(b, "text", "") for b in raw if getattr(b, "text", "")]
    joined = "".join(texts).strip()
    return json.loads(joined) if joined else None


@pytest.fixture()
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))  # isolate config/state dirs
    cfg = Config(state_db=tmp_path / "state.sqlite3", vector_dir=tmp_path / "vector",
                 decider_enabled=False)
    return build_server(cfg)


def test_ask_no_documents_returns_no_fabrication(server):
    out = call(server, "ask", {"question": "What is the airspeed of a swallow?"})
    assert "answer" in out
    assert out["answer"].startswith("No relevant information") or "could not" in out["answer"]
    assert out["citations"] == []


def test_unknown_source_remove_is_graceful(server):
    out = call(server, "sources_remove", {"source_id": "zz"})
    assert out == {"removed": "zz", "documents_deleted": 0}


def test_bad_source_type_raises_not_found(server):
    with pytest.raises(Exception) as ei:  # FastMCP wraps tool errors
        call(server, "sources_add", {"type": "gopher", "config": {}})
    assert "unsupported source type" in str(ei.value)


def test_graph_query_disabled_by_default(server):
    with pytest.raises(Exception) as ei:
        call(server, "graph_query", {"query": "x"})
    assert "FeatureDisabled" in str(ei.value) or "disabled" in str(ei.value)


def test_status_shape(server):
    out = call(server, "status", {})
    assert out["decision_layer"] in ("decision_node", "fallback")
    assert "index" in out and "sources" in out
    assert "documents" in out["index"] and "chunks" in out["index"]


def test_mcp_action_schema_is_additive_and_ask_schema_is_unchanged(server):
    tools = asyncio.run(server.list_tools())
    by_name = {tool.name: tool for tool in tools}

    assert "mcp_action" in by_name
    action_schema = by_name["mcp_action"].inputSchema
    properties = action_schema["properties"]
    assert set(properties) == {
        "phase", "conversation_id", "dialogue_count", "query", "action_id", "parameters",
    }
    assert set(action_schema["required"]) == {"phase", "conversation_id", "dialogue_count"}
    assert properties["phase"]["type"] == "string"
    assert set(properties["phase"]["enum"]) == {"draft", "confirm", "cancel"}
    assert properties["conversation_id"]["type"] == "string"
    assert properties["dialogue_count"]["type"] == "integer"
    assert properties["query"] == {"default": "", "title": "Query", "type": "string"}
    assert properties["action_id"] == {"default": "", "title": "Action Id", "type": "string"}
    assert properties["parameters"]["default"] is None

    # C05: adding the tool must not alter the established ask input contract.
    assert by_name["ask"].inputSchema == {
        "properties": {
            "collections": {
                "anyOf": [
                    {"items": {"type": "string"}, "type": "array"},
                    {"type": "null"},
                ],
                "default": None,
                "title": "Collections",
            },
            "max_iterations": {
                "anyOf": [{"type": "integer"}, {"type": "null"}],
                "default": None,
                "title": "Max Iterations",
            },
            "mode": {"default": "auto", "title": "Mode", "type": "string"},
            "question": {"title": "Question", "type": "string"},
        },
        "required": ["question"],
        "title": "askArguments",
        "type": "object",
    }
