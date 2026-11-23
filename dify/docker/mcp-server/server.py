"""AgenticRAG MCP sidecar for Dify: real tools over HTTP.

Bridges the actual agentic-rag-mcp server (LanceDB + embedder + pipeline)
onto a Dify-compatible surface, per the Dify MCP Sidecar procedure:

  - stateless_http=True  -> Dify sends requests without session management
  - POST /mcp            -> Streamable HTTP (recommended for Dify)
  - GET /sse + POST /messages/  -> legacy SSE fallback
  - GET /healthz         -> container health check
  - binds 0.0.0.0:28080  -> reachable via Docker DNS (http://agentic-rag:28080/mcp)

Run locally:  .venv/bin/python dify/docker/mcp-server/server.py
Run in Docker: see Dockerfile next to this file.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path

# Make `agentic_rag_mcp` importable when run straight from the repo checkout.
# (In Docker the file is copied to /app and the package is pip-installed,
# so there is no repo root to find — skip path injection there.)
_p = Path(__file__).resolve()
if len(_p.parents) > 3 and (_p.parents[3] / "src" / "agentic_rag_mcp").is_dir():
    sys.path.insert(0, str(_p.parents[3] / "src"))

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from agentic_rag_mcp.config import load_config
from agentic_rag_mcp.mcp_action.reports import get_report_store
from agentic_rag_mcp.mcp_action.screenshots import get_screenshot_store
from agentic_rag_mcp.server import build_server

HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "28080"))

# stateless_http=True is required so Dify can send stateless requests
# without session-management errors.
cfg = load_config()
screenshot_store = get_screenshot_store()
report_store = get_report_store()
exports_url_base = (
    os.environ.get("PPT_EXPORTS_URL_BASE") or cfg.ppt_exports_url_base
).rstrip("/")
public_origin = exports_url_base.removesuffix("/exports")
# The shared stores predate sidecar configuration; only their public URLs are configured here.
screenshot_store._public_base_url = f"{public_origin}/mcp-action/screenshots"
report_store._public_base_url = f"{public_origin}/mcp-action/reports"
mcp = build_server(cfg, stateless_http=True, host=HOST, port=PORT)

streamable = mcp.streamable_http_app()  # registers POST /mcp, creates session manager
sse = mcp.sse_app()                     # registers GET /sse, POST /messages/


async def healthz(request) -> JSONResponse:
    """Container health check (docker exec ... curl http://agentic-rag:28080/healthz)."""
    return JSONResponse({"status": "ok"})


async def export_file(request) -> Response:
    """Serve a generated deck: GET /exports/<project_id>/<file>.pptx (spec 009, R2)."""
    from agentic_rag_mcp.ppt.bridge import projects_root
    from agentic_rag_mcp.ppt.errors import InvalidInput
    from agentic_rag_mcp.ppt.http_exports import (
        PPTX_CONTENT_TYPE,
        ExportNotFound,
        resolve_export,
    )

    try:
        path = resolve_export(
            projects_root(cfg),  # where the toolchain actually writes
            request.path_params["project_id"],
            request.path_params["filename"],
        )
    except InvalidInput:
        return Response("bad request", status_code=400)
    except ExportNotFound:
        return Response("not found", status_code=404)
    # ACAO: the Chat UI embeds sidecar-hosted media in exported PDFs (spec 013)
    return FileResponse(path, media_type=PPTX_CONTENT_TYPE,
                        headers={"Access-Control-Allow-Origin": "*"})


async def completion_page(request) -> Response:
    """Serve an export's completion page: GET /decks/<project_id>/<stem>/ (spec 010)."""
    from agentic_rag_mcp.ppt.completion import artifact_exists, render_completion_page
    from agentic_rag_mcp.ppt.errors import InvalidInput

    try:
        if not artifact_exists(cfg, request.path_params["project_id"],
                               request.path_params["stem"]):
            return Response("not found", status_code=404)
        page = render_completion_page(
            cfg, request.path_params["project_id"], request.path_params["stem"]
        )
    except InvalidInput:
        return Response("bad request", status_code=400)
    return HTMLResponse(page)


async def completion_slide(request) -> Response:
    """Serve one preview slide: GET /decks/<project_id>/<stem>/slides/<file> (spec 010)."""
    from agentic_rag_mcp.ppt.completion import resolve_slide
    from agentic_rag_mcp.ppt.errors import InvalidInput

    try:
        path = resolve_slide(
            cfg,
            request.path_params["project_id"],
            request.path_params["stem"],
            request.path_params["filename"],
        )
    except InvalidInput:
        return Response("bad request", status_code=400)
    except FileNotFoundError:
        return Response("not found", status_code=404)
    # ACAO: the Chat UI embeds sidecar-hosted media in exported PDFs (spec 013)
    return FileResponse(path, media_type="image/svg+xml",
                        headers={"Access-Control-Allow-Origin": "*"})


async def infographic_page(request) -> Response:
    """Serve a rendered infographic: GET /infographics/<id>/ (spec 012)."""
    from agentic_rag_mcp.antv.errors import AntvInvalidInput
    from agentic_rag_mcp.antv.infographic import render_infographic_page

    try:
        page = render_infographic_page(cfg, request.path_params["id"])
    except AntvInvalidInput:
        return Response("bad request", status_code=400,
                        headers={"Cache-Control": "no-store"})
    except FileNotFoundError:
        return Response("not found", status_code=404,
                        headers={"Cache-Control": "no-store"})
    return HTMLResponse(page, headers={
        "Cache-Control": "no-store",
        "Access-Control-Allow-Origin": "*",  # spec 013: UI embeds sidecar media in PDFs
    })


_SCREENSHOT_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "Access-Control-Allow-Origin": "*",
    "Cross-Origin-Resource-Policy": "cross-origin",
    "X-Content-Type-Options": "nosniff",
    "Content-Disposition": "inline",
}


async def screenshot_file(request) -> Response:
    """Serve one temporary screenshot without exposing its storage metadata."""
    if request.method != "GET":
        return Response(
            "method not allowed",
            status_code=405,
            headers={"Allow": "GET", "Cache-Control": "no-store"},
        )
    image = screenshot_store.resolve(request.path_params["token"])
    if image is None:
        return Response("not found", status_code=404,
                        headers={"Cache-Control": "no-store"})
    return Response(image.data, media_type=image.mime_type, headers=_SCREENSHOT_HEADERS)


_REPORT_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "Content-Disposition": 'inline; filename="system-health-report.html"',
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
        "script-src 'none'; object-src 'none'; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'; sandbox"
    ),
}


async def report_file(request) -> Response:
    """Serve one temporary self-contained HTML report as exact stored bytes."""
    if request.method != "GET":
        return Response(
            "method not allowed",
            status_code=405,
            headers={"Allow": "GET", "Cache-Control": "no-store"},
        )
    report = report_store.resolve(request.path_params["token"])
    if report is None:
        return Response("not found", status_code=404,
                        headers={"Cache-Control": "no-store"})
    return Response(
        report.data,
        media_type="text/html; charset=utf-8",
        headers=_REPORT_HEADERS,
    )


async def mcp_get(request) -> Response:
    """Browsers/probes that GET /mcp get a clean 405 instead of a confusing
    JSON-RPC 406. Per MCP streamable-HTTP spec, servers without the optional
    server-initiated stream answer 405; clients (incl. Dify) proceed POST-only."""
    return Response(
        "MCP streamable HTTP endpoint. Send JSON-RPC via POST. Health: GET /healthz",
        status_code=405,
        headers={"Allow": "POST"},
    )


async def _cleanup_loop():
    while True:
        await asyncio.sleep(30)
        screenshot_store.cleanup()
        report_store.cleanup()


@asynccontextmanager
async def lifespan(app):
    screenshot_store.cleanup()
    report_store.cleanup()
    janitor = asyncio.create_task(_cleanup_loop())
    try:
        # Streamable HTTP needs its session manager started for the app's lifetime.
        async with mcp.session_manager.run():
            yield
    finally:
        janitor.cancel()
        with suppress(asyncio.CancelledError):
            await janitor
        screenshot_store.cleanup()
        report_store.cleanup()


app = Starlette(
    routes=[
        Route("/healthz", healthz, methods=["GET"]),
        Route("/mcp", mcp_get, methods=["GET"]),  # before the SDK route: intercepts GET only
        Route("/exports/{project_id}/{filename}", export_file, methods=["GET"]),
        Route("/decks/{project_id}/{stem}/", completion_page, methods=["GET"]),
        Route("/decks/{project_id}/{stem}/slides/{filename}", completion_slide,
              methods=["GET"]),
        Route("/infographics/{id}/", infographic_page, methods=["GET"]),
        Route(
            "/mcp-action/screenshots/{token:path}",
            screenshot_file,
            methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"],
        ),
        Route(
            "/mcp-action/reports/{token:path}",
            report_file,
            methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"],
        ),
        *streamable.routes,
        *sse.routes,
    ],
    lifespan=lifespan,
)

if __name__ == "__main__":
    # log_config=None: uvicorn must not attach its own handlers (they set
    # propagate=False, which would bypass our root file setup) — request
    # lines flow to the root handlers and land in the log file (spec 008).
    uvicorn.run(app, host=HOST, port=PORT, log_config=None)
