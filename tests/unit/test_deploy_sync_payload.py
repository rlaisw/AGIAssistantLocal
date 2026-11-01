"""Unit: sync payload building + version gate (spec 011, P04-P05)."""

from __future__ import annotations

import json
from pathlib import Path

from agentic_rag_mcp.deploy.tool_sync import build_payload, resync_path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "deploy"


def _live():
    return json.loads((FIXTURES / "tools_list.json").read_text())["tools"]


def test_payload_shape_and_count():
    payload = build_payload(_live())
    assert len(payload) == 3
    for entry in payload:
        assert set(entry) == {"name", "title", "description", "inputSchema"}
        assert entry["title"] is None
    names = [e["name"] for e in payload]
    assert names == ["ask", "ppt_project_init", "ppt_export"]
    by_name = {e["name"]: e for e in payload}
    assert by_name["ppt_project_init"]["inputSchema"]["properties"]["name"]["type"] == "string"


def test_payload_defaults_missing_fields():
    payload = build_payload([{"name": "x"}])
    assert payload[0]["description"] == ""
    assert payload[0]["inputSchema"] == {"type": "object", "properties": {}}


def test_version_gate_supported():
    assert resync_path("1.17.1") == "db-resync"
    assert resync_path("1.17.0") == "db-resync"
    # 1.18 validated live during spec 029 (same tools column; read path verified)
    assert resync_path("1.18.0") == "db-resync"


def test_version_gate_unknown_or_missing():
    assert resync_path("2.0.0") == "skipped"
    assert resync_path(None) == "skipped"
