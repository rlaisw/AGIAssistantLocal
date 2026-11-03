"""Contract: ppt_* tool schemas, error envelopes, tools/list growth, /exports route.

Spec 009 (FR-001/010/011, Constitution I + IV). Hermetic: fake ppt-master
scripts + temp workspaces; the real toolchain is exercised in
tests/integration/test_ppt_pipeline.py. Matrix refs: T02, T05, T06, T08, T09,
T12, T15, T18, T19, T21, T22, T23, T25.
"""

from __future__ import annotations

import asyncio
import json
import textwrap

import pytest

from agentic_rag_mcp.config import Config
from agentic_rag_mcp.server import build_server

PASSING_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
    '<g id="t" data-pptx-bounds="64 64 400 100"><text x="64" y="100" '
    'font-size="24" fill="#212121">Hello Dify</text></g></svg>'
)

EXISTING_TOOLS = {
    "ask", "search", "web_search", "specialty_profiles", "specialty_search",
    "web_research", "graph_query", "status", "sources_add", "sources_sync",
    "sources_list", "sources_remove", "fetch_url", "onedrive_list_files",
    "onedrive_embed_files", "sources_auth",
    "hermes_file_task",        # spec 028 (amended 2026-11-01 — the set was stale since)
    "hermes_launch_app",       # spec 029
    "hermes_office_task",      # spec 030
}
ANTV_TOOLS = {"antv_chart", "antv_infographic"}  # spec 012 (additive)
PPT_TOOLS = {
    "ppt_project_init", "ppt_icon_sync", "ppt_write_page", "ppt_check", "ppt_export",
}


def call(server, name, args):
    raw = asyncio.run(server.call_tool(name, args))
    structured = [b["result"] for b in raw if isinstance(b, dict) and "result" in b]
    if structured:
        return structured[0]
    texts = [getattr(b, "text", "") for b in raw if getattr(b, "text", "")]
    joined = "".join(texts).strip()
    return json.loads(joined) if joined else None


def fake_scripts(scripts_root) -> None:
    """Minimal ppt-master script stand-ins emitting the parsed output lines."""
    scripts = scripts_root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "project_manager.py").write_text(textwrap.dedent("""
        import os, sys
        name = sys.argv[2]
        pid = f"{name}_20260101"
        root = os.environ["PPT_PROJECTS_ROOT"]
        os.makedirs(os.path.join(root, pid, "svg_output"), exist_ok=True)
        print(f"[OK] Project initialized: projects/{pid}")
    """))
    (scripts / "icon_sync.py").write_text(textwrap.dedent("""
        import sys
        ws, icons = sys.argv[1], sys.argv[2:]
        print(f"[OK] {len(icons)} icon(s) in {ws}:")
        for icon in icons:
            if icon == "tabler-outline/nonexistent":
                print("     [MISSING] not in the library")
                print(f"     ✗ {icon}")
            else:
                print(f"     + {icon}")
    """))
    (scripts / "svg_quality_checker.py").write_text(
        "import sys; print('[REPORT] json: %s/validation/svg_quality_report.json' % sys.argv[2])\n"
    )
    (scripts / "svg_to_pptx.py").write_text(textwrap.dedent("""
        import os, sys
        ws = sys.argv[1]
        out = f"{ws}/exports"
        os.makedirs(out, exist_ok=True)
        with open(f"{out}/deck_120000.pptx", "wb") as f:
            f.write(b"PK\\x03\\x04fake-pptx")
        print(f"[PPTX] {out}/deck_120000.pptx")
    """))


def write_report(projects_root, project_id, *, errors=None, warnings=None):
    import pathlib

    errors = errors or []
    warnings = warnings or []
    vdir = pathlib.Path(projects_root) / project_id / "validation"
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / "svg_quality_report.json").write_text(json.dumps({
        "summary": {"total": 1, "passed": int(not errors), "warnings": len(warnings),
                    "errors": len(errors)},
        "files": [{"file": "01_overview.svg", "errors": errors, "warnings": warnings}],
    }))


@pytest.fixture
def server(tmp_path):
    # layout mirrors the real toolchain: scripts at <root>/skills/ppt-master,
    # projects (and fakes honoring PPT_PROJECTS_ROOT) at <root>/projects
    root = tmp_path / "pptm"
    scripts = root / "skills" / "ppt-master"
    fake_scripts(scripts)
    (root / "projects").mkdir(parents=True)
    cfg = Config(
        state_db=tmp_path / "s.sqlite3",
        vector_dir=tmp_path / "v",
        decider_enabled=False,
        ppt_scripts_root=scripts,
        ppt_projects_root=root / "projects",
        ppt_exports_url_base="http://test/exports",
    )
    srv = build_server(cfg)
    srv._ppt_cfg = cfg
    return srv


# ---------------------------------------------------------------- tools/list (T22)

def test_tools_list_grows_16_to_21(server):
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert PPT_TOOLS <= names
    assert EXISTING_TOOLS <= names, "existing tools must survive unchanged (Constitution I)"
    assert len(names) == len(EXISTING_TOOLS | PPT_TOOLS | ANTV_TOOLS)  # no accidental extras (antv added in spec 012)


# ---------------------------------------------------------------- happy path

def test_init_returns_workspace(server):
    result = call(server, "ppt_project_init", {"name": "dify"})
    assert result["project_id"] == "dify_20260101"
    assert result["workspace"].endswith("dify_20260101")
    assert result["max_pages"] == 5


def test_full_round_trip(server, tmp_path):
    pid = call(server, "ppt_project_init", {"name": "dify"})["project_id"]
    assert call(server, "ppt_icon_sync", {"project_id": pid,
                                          "icons": ["tabler-outline/star"]}) == {
        "synced": ["tabler-outline/star"], "missing": []}
    written = call(server, "ppt_write_page", {
        "project_id": pid, "page_number": 1, "name": "overview", "svg": PASSING_SVG})
    assert written["file"] == "svg_output/01_overview.svg"
    write_report(server._ppt_cfg.ppt_projects_root, pid)
    result = call(server, "ppt_check", {"project_id": pid})
    assert result["passing"] is True
    exported = call(server, "ppt_export", {"project_id": pid})
    assert exported["url"] == f"http://test/exports/{pid}/deck_120000.pptx"


# ---------------------------------------------------------------- error paths (T23)

def test_init_rejects_bad_name(server):
    result = call(server, "ppt_project_init", {"name": "../escape"})
    assert result["error"]["code"] == "PPT_INVALID_INPUT"
    assert result["error"]["hint"]


def test_unknown_project_every_tool(server):
    for tool, args in [
        ("ppt_icon_sync", {"project_id": "ghost", "icons": ["tabler-outline/star"]}),
        ("ppt_write_page", {"project_id": "ghost", "page_number": 1, "name": "x",
                            "svg": PASSING_SVG}),
        ("ppt_check", {"project_id": "ghost"}),
        ("ppt_export", {"project_id": "ghost"}),
    ]:
        result = call(server, tool, args)
        assert result["error"]["code"] == "PPT_INVALID_PROJECT", tool


def test_missing_icon_envelope(server):
    pid = call(server, "ppt_project_init", {"name": "dify"})["project_id"]
    result = call(server, "ppt_icon_sync", {
        "project_id": pid,
        "icons": ["tabler-outline/star", "tabler-outline/nonexistent"]})
    assert result["error"]["code"] == "PPT_MISSING_ICON"
    assert "tabler-outline/nonexistent" in result["error"]["message"]
    assert "tabler-outline/star" in result["error"]["message"]  # partial success is visible


def test_write_page_rejects_forbidden_svg(server):
    pid = call(server, "ppt_project_init", {"name": "dify"})["project_id"]
    bad = PASSING_SVG.replace(">", "><script>alert(1)</script>", 1)
    result = call(server, "ppt_write_page", {
        "project_id": pid, "page_number": 1, "name": "x", "svg": bad})
    assert result["error"]["code"] == "PPT_INVALID_INPUT"
    assert "script" in result["error"]["message"]


def test_write_page_rejects_out_of_range_page(server):
    pid = call(server, "ppt_project_init", {"name": "dify"})["project_id"]
    for page in (0, 6):
        result = call(server, "ppt_write_page", {
            "project_id": pid, "page_number": page, "name": "x", "svg": PASSING_SVG})
        assert result["error"]["code"] == "PPT_INVALID_INPUT"


def test_export_blocked_on_failing_pages(server, tmp_path):
    pid = call(server, "ppt_project_init", {"name": "dify"})["project_id"]
    call(server, "ppt_write_page", {"project_id": pid, "page_number": 1,
                                    "name": "overview", "svg": PASSING_SVG})
    write_report(server._ppt_cfg.ppt_projects_root, pid, errors=["text overflow 14.8%"])
    result = call(server, "ppt_export", {"project_id": pid})
    assert result["error"]["code"] == "PPT_EXPORT_BLOCKED"
    assert "text overflow" in result["error"]["message"]  # fixable summary included


def test_check_reports_details(server, tmp_path):
    pid = call(server, "ppt_project_init", {"name": "dify"})["project_id"]
    write_report(server._ppt_cfg.ppt_projects_root, pid, errors=["overflow A"], warnings=["advisory B"])
    result = call(server, "ppt_check", {"project_id": pid})
    assert result["passing"] is False
    assert result["blocking_errors"] == 1
    assert any("overflow A" in d for d in result["details"])


# ---------------------------------------------------------------- concurrency (T21)

def test_concurrent_projects_isolated(server, tmp_path):
    a = call(server, "ppt_project_init", {"name": "deck_a"})["project_id"]
    b = call(server, "ppt_project_init", {"name": "deck_b"})["project_id"]
    assert a != b
    call(server, "ppt_write_page", {"project_id": a, "page_number": 1,
                                    "name": "pa", "svg": PASSING_SVG})
    call(server, "ppt_write_page", {"project_id": b, "page_number": 1,
                                    "name": "pb", "svg": PASSING_SVG})
    root = server._ppt_cfg.ppt_projects_root
    assert (root / a / "svg_output" / "01_pa.svg").is_file()
    assert (root / b / "svg_output" / "01_pb.svg").is_file()


# ---------------------------------------------------------------- /exports route (T25)

def test_exports_route(tmp_path):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from agentic_rag_mcp.ppt.http_exports import PPTX_CONTENT_TYPE, resolve_export

    projects = tmp_path / "pptm" / "projects"
    proj = projects / "deck_20260101"
    (proj / "exports").mkdir(parents=True)
    (proj / "exports" / "deck_1.pptx").write_bytes(b"PK-fake")

    async def handler(request):
        from agentic_rag_mcp.ppt.errors import InvalidInput
        from agentic_rag_mcp.ppt.http_exports import ExportNotFound
        from starlette.responses import FileResponse, Response

        try:
            path = resolve_export(projects, request.path_params["project_id"],
                                  request.path_params["filename"])
        except InvalidInput:
            return Response("bad request", status_code=400)
        except ExportNotFound:
            return Response("not found", status_code=404)
        return FileResponse(path, media_type=PPTX_CONTENT_TYPE)

    app = Starlette(routes=[Route("/exports/{project_id}/{filename}", handler)])
    client = TestClient(app)

    ok = client.get("/exports/deck_20260101/deck_1.pptx")
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith(PPTX_CONTENT_TYPE)
    assert ok.content == b"PK-fake"

    assert client.get("/exports/deck_20260101/missing.pptx").status_code == 404
    assert client.get("/exports/deck_20260101/..%2F..%2Fetc.pptx").status_code in (400, 404)
