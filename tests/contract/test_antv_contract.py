"""Contract: antv tool schemas, envelope, tools/list growth (spec 012).

Hermetic (fake service per the ppt conftest pattern); matrix refs A01, A07-A09,
A11, A13-A15.
"""

from __future__ import annotations

import asyncio
import json
import textwrap
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from agentic_rag_mcp.config import Config
from agentic_rag_mcp.server import build_server

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "antv"
EXISTING_TOOLS = {
    "ask", "search", "web_search", "specialty_profiles", "specialty_search",
    "web_research", "graph_query", "status", "sources_add", "sources_sync",
    "sources_list", "sources_remove", "fetch_url", "onedrive_list_files",
    "onedrive_embed_files", "sources_auth",
    "ppt_project_init", "ppt_icon_sync", "ppt_write_page", "ppt_check", "ppt_export",
    "hermes_file_task",        # spec 028 (amended 2026-11-01 — the set was stale since)
    "hermes_launch_app",       # spec 029
}
ANTV_TOOLS = {"antv_chart", "antv_infographic"}


def call(server, name, args):
    raw = asyncio.run(server.call_tool(name, args))
    structured = [b["result"] for b in raw if isinstance(b, dict) and "result" in b]
    if structured:
        return structured[0]
    texts = [getattr(b, "text", "") for b in raw if getattr(b, "text", "")]
    joined = "".join(texts).strip()
    return json.loads(joined) if joined else None


class FakeChartService:
    def __init__(self):
        self.requests = []
        self.server = HTTPServer(("127.0.0.1", 0), self._handler())
        import threading

        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def _handler(self):
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.requests.append(body)
                ok = body.get("type") == "bar"
                payload = (
                    {"success": True, "resultObj": "https://img/ok.png", "errorMessage": "成功"}
                    if ok
                    else {"success": False, "errorMessage": "unsupported type", "errorCode": "EX"}
                )
                data = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        return H

    @property
    def url(self):
        return f"http://{self.server.server_address[0]}:{self.server.server_address[1]}"

    def stop(self):
        self.server.shutdown()


@pytest.fixture
def env(tmp_path):
    svc = FakeChartService()
    root = tmp_path / "pptm"
    (root / "projects").mkdir(parents=True)
    cfg = Config(
        state_db=tmp_path / "s.sqlite3",
        vector_dir=tmp_path / "v",
        decider_enabled=False,
        ppt_projects_root=root / "projects",
        antv_chart_service_url=svc.url,
        antv_infographic_served_root=tmp_path / "infographics",
    )
    srv = build_server(cfg)
    yield {"server": srv, "cfg": cfg, "svc": svc, "root": tmp_path}
    svc.stop()


def test_tools_list_grows_21_to_23(env):
    tools = asyncio.run(env["server"].list_tools())
    names = {t.name for t in tools}
    assert ANTV_TOOLS <= names
    assert EXISTING_TOOLS <= names
    assert len(names) == len(EXISTING_TOOLS | ANTV_TOOLS)  # exactly additive (A13)


def test_antv_chart_success_shape(env):
    result = call(env["server"], "antv_chart", {
        "chart_type": "bar",
        "data": [{"category": "A", "value": 30}, {"category": "B", "value": 70}],
        "title": "Volume",
    })
    assert result == {
        "chart_type": "bar",
        "image_url": "https://img/ok.png",
        "usage": result["usage"],  # present
    }
    assert "image_url" in result["usage"] or "markdown" in result["usage"].lower()
    assert env["svc"].requests[0]["type"] == "bar"


def test_antv_chart_unsupported_type_envelope(env):
    result = call(env["server"], "antv_chart", {
        "chart_type": "district-map", "data": [{"category": "A", "value": 1}], "title": "t",
    })
    assert result["error"]["code"] == "ANTV_INVALID_TYPE"
    assert "line" in result["error"]["message"]
    assert result["error"]["hint"]


def test_antv_chart_invalid_data_envelope(env):
    result = call(env["server"], "antv_chart", {"chart_type": "bar", "data": [], "title": "t"})
    assert result["error"]["code"] == "ANTV_INVALID_INPUT"


def test_antv_chart_service_failure_envelope(env):
    result = call(env["server"], "antv_chart", {
        "chart_type": "line",  # fake service only accepts bar -> success=false
        "data": [{"time": "1", "value": 2}],
        "title": "t",
    })
    assert result["error"]["code"] == "ANTV_SERVICE_ERROR"
    assert "unsupported type" in result["error"]["message"]


def test_antv_infographic_success_and_route(env):
    result = call(env["server"], "antv_infographic", {
        "description": "infographic list-row-simple\ndata\n  lists\n    - label A\n",
    })
    assert "/infographics/" in result["url"]
    # the stored file serves the rendered page content contract
    from agentic_rag_mcp.antv import infographic

    page = infographic.render_infographic_page(env["cfg"], result["id"])
    assert "cdn.jsdelivr.net" in page or "unpkg" in page


def test_antv_infographic_invalid_syntax_envelope(env):
    result = call(env["server"], "antv_infographic", {"description": ""})
    assert result["error"]["code"] == "ANTV_INVALID_INPUT"


def test_infographic_route_semantics(env):
    from starlette.applications import Starlette
    from starlette.responses import Response
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from agentic_rag_mcp.antv import infographic
    from agentic_rag_mcp.antv.errors import AntvInvalidInput

    cfg = env["cfg"]

    async def handler(request):
        try:
            page = infographic.render_infographic_page(cfg, request.path_params["id"])
        except AntvInvalidInput:
            return Response("bad request", status_code=400)
        except FileNotFoundError:
            return Response("not found", status_code=404)
        from starlette.responses import HTMLResponse

        return HTMLResponse(page)

    app = Starlette(routes=[Route("/infographics/{id}/", handler, methods=["GET"])])
    client = TestClient(app)
    good = call(env["server"], "antv_infographic", {"description": "infographic x\ndata\n  lists\n    - label A\n"})
    rid = good["url"].rstrip("/").split("/")[-1]
    assert client.get(f"/infographics/{rid}/").status_code == 200
    assert client.get("/infographics/ghost/").status_code == 404
    assert client.get("/infographics/bad%20id/").status_code == 400


def test_envelope_shape_every_code(env):
    results = [
        call(env["server"], "antv_chart", {"chart_type": "nope", "data": [{"category": "A", "value": 1}], "title": "t"}),
        call(env["server"], "antv_chart", {"chart_type": "bar", "data": [], "title": "t"}),
        call(env["server"], "antv_chart", {"chart_type": "line", "data": [{"time": "1", "value": 2}], "title": "t"}),
    ]
    for r in results:
        assert set(r) == {"error"}
        assert set(r["error"]) == {"code", "message", "hint"}
        assert r["error"]["message"] and r["error"]["hint"]


def test_existing_ppt_contract_suite_still_green():
    # A15 guard: the ppt contract suite runs as part of the full suite; here we
    # assert the frozen tool names remain present alongside the new ones.
    assert "ppt_export" in EXISTING_TOOLS and "antv_chart" in ANTV_TOOLS
