"""Temporary HTML health report HTTP contracts (spec 048, T007).

The sidecar is loaded from its hyphenated Docker directory with importlib, and
ASGI requests run in-process. The report store, screenshot store, config, MCP
construction, and clock are isolated, so no Docker daemon, network listener, or
real user state is involved.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from agentic_rag_mcp.mcp_action.reports import ReportStore

from agentic_rag_mcp.config import Config
from agentic_rag_mcp.mcp_action.screenshots import ScreenshotStore

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "mcp_action"
SIDECAR = ROOT / "dify" / "docker" / "mcp-server" / "server.py"
PUBLIC_BASE = "http://testserver/mcp-action/reports"

REQUIRED_HEADERS = {
    "cache-control": "no-store, max-age=0",
    "pragma": "no-cache",
    "expires": "0",
    "content-disposition": 'inline; filename="system-health-report.html"',
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "cross-origin-resource-policy": "same-origin",
    "x-robots-tag": "noindex, nofollow, noarchive",
    "content-security-policy": (
        "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
        "script-src 'none'; object-src 'none'; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'; sandbox"
    ),
}

FORBIDDEN_HEADERS = (
    "access-control-allow-origin",
    "access-control-allow-credentials",
    "access-control-allow-methods",
    "accept-ranges",
    "etag",
    "last-modified",
)


def _html(body: str = "<p>ok</p>") -> bytes:
    return (
        '<!doctype html><html lang="en"><head><title>System health</title>'
        "</head><body>" + body + "</body></html>"
    ).encode("utf-8")


class _Clock:
    def __init__(self):
        self.value = 1_000.0

    def __call__(self):
        return self.value


class _SessionManager:
    @asynccontextmanager
    async def run(self):
        yield


class _DummyMcp:
    session_manager = _SessionManager()

    def streamable_http_app(self):
        return SimpleNamespace(routes=[])

    def sse_app(self):
        return SimpleNamespace(routes=[])


def _config(tmp_path):
    return Config(
        state_db=tmp_path / "state.sqlite3",
        vector_dir=tmp_path / "vectors",
        decider_enabled=False,
        graphify_enabled=False,
    )


@pytest.fixture()
def route_env(tmp_path, monkeypatch):
    import agentic_rag_mcp.mcp_action.reports as reports_module

    import agentic_rag_mcp.config as config_module
    import agentic_rag_mcp.mcp_action.screenshots as screenshots_module
    import agentic_rag_mcp.server as server_module

    clock = _Clock()
    report_root = tmp_path / "reports"
    report_store = ReportStore(
        root=report_root, clock=clock, public_base_url=PUBLIC_BASE
    )
    shot_root = tmp_path / "screenshots"
    shot_store = ScreenshotStore(
        root=shot_root,
        clock=clock,
        public_base_url="http://testserver/mcp-action/screenshots",
    )

    # Any shared store constructed while the sidecar loads must be this isolated
    # instance. Patching the factory before import also covers a direct
    # ``from ... import get_report_store`` binding in the sidecar.
    monkeypatch.setattr(
        reports_module, "ReportStore", lambda *a, **kw: report_store, raising=False
    )
    monkeypatch.setattr(
        reports_module, "get_report_store", lambda: report_store, raising=False
    )
    monkeypatch.setattr(reports_module, "_default_store", None, raising=False)
    monkeypatch.setattr(
        screenshots_module, "ScreenshotStore", lambda *a, **kw: shot_store, raising=False
    )
    monkeypatch.setattr(
        screenshots_module, "get_screenshot_store", lambda: shot_store, raising=False
    )
    monkeypatch.setattr(config_module, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(server_module, "build_server", lambda *a, **kw: _DummyMcp())
    monkeypatch.setattr(sys, "path", sys.path.copy())

    spec = importlib.util.spec_from_file_location(
        "_mcp_action_sidecar_report_contract", SIDECAR
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "report_store", report_store, raising=False)
    monkeypatch.setattr(module, "screenshot_store", shot_store, raising=False)
    return SimpleNamespace(
        app=module.app,
        report_store=report_store,
        screenshot_store=shot_store,
        clock=clock,
        root=report_root,
        shot_root=shot_root,
    )


def _request(app, token, method="GET", route="reports"):
    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.request(method, f"/mcp-action/{route}/{token}")

    return asyncio.run(send())


def _fingerprint(response):
    # Date is transport metadata, not part of the failure-class contract.
    headers = tuple(
        sorted(
            (name, value)
            for name, value in response.headers.items()
            if name.lower() != "date"
        )
    )
    return response.content, headers


def test_get_returns_exact_html_bytes_mime_and_all_delivery_headers(route_env):
    document = _html()
    artifact = route_env.report_store.save(document)

    response = _request(route_env.app, artifact.token)

    assert response.status_code == 200
    assert response.content == document  # exact stored bytes, never re-encoded
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["content-length"] == str(len(document))
    for name, value in REQUIRED_HEADERS.items():
        assert response.headers[name] == value
    for name in FORBIDDEN_HEADERS:
        assert name not in response.headers


def test_get_returns_exact_bom_bytes(route_env):
    document = b"\xef\xbb\xbf" + _html()
    artifact = route_env.report_store.save(document)

    response = _request(route_env.app, artifact.token)

    assert response.status_code == 200
    assert response.content == document
    assert response.content.startswith(b"\xef\xbb\xbf")


def test_repeated_gets_do_not_delete_or_renew_absolute_expiry(route_env):
    document = _html()
    artifact = route_env.report_store.save(document)

    first = _request(route_env.app, artifact.token)
    second = _request(route_env.app, artifact.token)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content == document

    route_env.clock.value += 899
    near_expiry = _request(route_env.app, artifact.token)
    assert near_expiry.status_code == 200
    assert near_expiry.content == document

    route_env.clock.value += 1
    expired = _request(route_env.app, artifact.token)
    assert expired.status_code == 404
    assert "no-store" in expired.headers["cache-control"]
    assert not artifact.path.exists()


def test_malformed_unknown_and_expired_tokens_are_indistinguishable(route_env):
    artifact = route_env.report_store.save(_html())
    unknown = ("A" if artifact.token[0] != "A" else "B") + artifact.token[1:]
    route_env.clock.value += 900

    tokens = ["bad-token", "A" * 42, "A" * 44, unknown, artifact.token]
    responses = [_request(route_env.app, token) for token in tokens]

    assert {response.status_code for response in responses} == {404}
    # Status, body, and headers must not reveal which failure class occurred.
    assert len({_fingerprint(response) for response in responses}) == 1
    for response in responses:
        assert "no-store" in response.headers["cache-control"]
        assert artifact.token not in response.text
        assert str(route_env.root) not in response.text
        assert "<html" not in response.text.lower()
        assert "base64" not in response.text.lower()
    assert not artifact.path.exists()


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_non_get_methods_are_405_with_get_allow_and_no_store(route_env, method):
    artifact = route_env.report_store.save(_html())

    response = _request(route_env.app, artifact.token, method=method)

    assert response.status_code == 405
    assert {value.strip() for value in response.headers["allow"].split(",")} == {"GET"}
    assert "no-store" in response.headers["cache-control"]
    assert artifact.token not in response.text
    assert str(route_env.root) not in response.text
    assert artifact.path.exists()


def test_report_and_screenshot_tokens_are_isolated(route_env):
    report = route_env.report_store.save(_html())
    image = (FIXTURES / "tiny.png").read_bytes()
    shot = route_env.screenshot_store.save(image)

    report_as_screenshot = _request(
        route_env.app, report.token, route="screenshots"
    )
    shot_as_report = _request(route_env.app, shot.token, route="reports")

    assert report_as_screenshot.status_code == 404
    assert shot_as_report.status_code == 404
    assert report.token not in report_as_screenshot.text
    assert shot.token not in shot_as_report.text

    # Each token still works on its own route.
    assert _request(route_env.app, report.token).status_code == 200
    assert _request(route_env.app, shot.token, route="screenshots").status_code == 200


def test_404_responses_do_not_echo_token_path_or_report_content(route_env):
    secret = "report-secret-4f9b"
    artifact = route_env.report_store.save(_html(f"<p>{secret}</p>"))
    route_env.clock.value += 900

    expired = _request(route_env.app, artifact.token)
    malformed = _request(route_env.app, "A" * 42)

    for response in (expired, malformed):
        assert response.status_code == 404
        assert artifact.token not in response.text
        assert secret not in response.text
        assert str(route_env.root) not in response.text
        assert str(artifact.path) not in response.text
        assert "Traceback" not in response.text
