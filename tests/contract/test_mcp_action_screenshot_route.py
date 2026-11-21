"""Temporary screenshot HTTP and public-tool contracts (spec 047, T017).

The sidecar is loaded from its hyphenated Docker directory with importlib. ASGI
requests run in-process; config, MCP construction, storage root, and clock are
isolated, so no Docker daemon, network listener, or real user state is involved.
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from agentic_rag_mcp.config import Config
from agentic_rag_mcp.mcp_action.screenshots import ScreenshotStore

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "mcp_action"
SIDECAR = ROOT / "dify" / "docker" / "mcp-server" / "server.py"
PUBLIC_BASE = "http://testserver/mcp-action/screenshots"
REQUIRED_HEADERS = {
    "cache-control": "no-store, max-age=0",
    "pragma": "no-cache",
    "expires": "0",
    "access-control-allow-origin": "*",
    "cross-origin-resource-policy": "cross-origin",
    "x-content-type-options": "nosniff",
    "content-disposition": "inline",
}


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
    import agentic_rag_mcp.config as config_module
    import agentic_rag_mcp.mcp_action.screenshots as screenshots_module
    import agentic_rag_mcp.server as server_module

    clock = _Clock()
    root = tmp_path / "screenshots"
    store = ScreenshotStore(root=root, clock=clock, public_base_url=PUBLIC_BASE)

    # Any shared store constructed while the sidecar loads must be this isolated
    # instance. The explicit module attribute also pins the route wiring seam.
    monkeypatch.setattr(screenshots_module, "ScreenshotStore", lambda *a, **kw: store)
    monkeypatch.setattr(config_module, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(server_module, "build_server", lambda *a, **kw: _DummyMcp())
    monkeypatch.setattr(sys, "path", sys.path.copy())

    spec = importlib.util.spec_from_file_location("_mcp_action_sidecar_contract", SIDECAR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "screenshot_store", store, raising=False)
    return SimpleNamespace(app=module.app, store=store, clock=clock, root=root)


def _request(app, token, method="GET"):
    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.request(method, f"/mcp-action/screenshots/{token}")

    return asyncio.run(send())


def _call_tool(server, name, args):
    raw = asyncio.run(server.call_tool(name, args))
    structured = [block["result"] for block in raw if isinstance(block, dict) and "result" in block]
    if structured:
        return structured[0]
    text = "".join(getattr(block, "text", "") for block in raw).strip()
    return json.loads(text) if text else None


@pytest.mark.parametrize(
    ("filename", "mime_type"),
    [("tiny.png", "image/png"), ("tiny.jpg", "image/jpeg")],
)
def test_get_returns_exact_image_bytes_mime_and_all_delivery_headers(
    route_env, filename, mime_type
):
    image = (FIXTURES / filename).read_bytes()
    artifact = route_env.store.save(image, mime_type=mime_type)

    response = _request(route_env.app, artifact.token)

    assert response.status_code == 200
    assert response.content == image  # decoded bytes, never a Base64/data-URL wrapper
    assert response.headers["content-type"] == mime_type
    for name, value in REQUIRED_HEADERS.items():
        assert response.headers[name] == value


def test_repeated_gets_do_not_delete_or_renew_absolute_expiry(route_env):
    image = (FIXTURES / "tiny.png").read_bytes()
    artifact = route_env.store.save(image)

    first = _request(route_env.app, artifact.token)
    second = _request(route_env.app, artifact.token)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content == image

    route_env.clock.value += 899
    near_expiry = _request(route_env.app, artifact.token)
    assert near_expiry.status_code == 200
    assert near_expiry.content == image

    route_env.clock.value += 1
    expired = _request(route_env.app, artifact.token)
    assert expired.status_code == 404
    assert "no-store" in expired.headers["cache-control"]
    assert not artifact.path.exists()


def test_malformed_unknown_and_expired_tokens_are_indistinguishable(route_env):
    artifact = route_env.store.save((FIXTURES / "tiny.png").read_bytes())
    unknown = ("A" if artifact.token[0] != "A" else "B") + artifact.token[1:]
    route_env.clock.value += 900

    responses = [
        _request(route_env.app, token)
        for token in ("bad-token", unknown, artifact.token)
    ]

    assert {response.status_code for response in responses} == {404}
    # Status, body, and headers must not reveal which failure class occurred.
    assert len({
        (response.content, tuple(sorted(response.headers.items())))
        for response in responses
    }) == 1
    for response in responses:
        assert "no-store" in response.headers["cache-control"]
        assert artifact.token not in response.text
        assert str(route_env.root) not in response.text
        assert "base64" not in response.text.lower()
    assert not artifact.path.exists()


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_non_get_methods_are_405_with_get_allow_and_no_store(route_env, method):
    artifact = route_env.store.save((FIXTURES / "tiny.png").read_bytes())

    response = _request(route_env.app, artifact.token, method=method)

    assert response.status_code == 405
    assert {value.strip() for value in response.headers["allow"].split(",")} == {"GET"}
    assert "no-store" in response.headers["cache-control"]
    assert artifact.token not in response.text
    assert str(route_env.root) not in response.text
    assert artifact.path.exists()


def test_captured_public_tool_result_has_no_base64_or_local_path(tmp_path, monkeypatch):
    """C04: the MCP boundary exposes only the capability delivery envelope."""
    import agentic_rag_mcp.server as server_module

    clock = _Clock()
    root = tmp_path / "screenshots"
    store = ScreenshotStore(root=root, clock=clock, public_base_url=PUBLIC_BASE)
    image = (FIXTURES / "tiny.png").read_bytes()

    class CapturedService:
        async def handle(self, **_kwargs):
            artifact = store.save(image)
            return {
                "status": "ok",
                "screenshot": {
                    "status": "captured",
                    "image_url": artifact.image_url,
                    "expires_in_s": int(artifact.expires - clock()),
                    "usage": "Inline this temporary image once as "
                    "![Verification screenshot](<image_url>).",
                },
            }

    # Build only the MCP registration surface; heavy stores, logging, watchers,
    # and action orchestration stay behind deterministic test doubles.
    state = SimpleNamespace(list_sources=list)
    pipeline = SimpleNamespace(migrate_onedrive_sources=lambda sources: None)
    monkeypatch.setattr(server_module, "McpActionService", CapturedService)
    monkeypatch.setattr(server_module, "configure_logging", lambda cfg: None)
    monkeypatch.setattr(server_module, "StateStore", lambda path: state)
    monkeypatch.setattr(server_module, "VectorStore", lambda path: object())
    monkeypatch.setattr(server_module, "Embedder", lambda *args: object())
    monkeypatch.setattr(server_module, "IngestionPipeline", lambda *args: pipeline)
    monkeypatch.setattr(
        server_module,
        "Watcher",
        lambda *args: SimpleNamespace(start=lambda: None),
    )
    server = server_module.build_server(_config(tmp_path))

    out = _call_tool(
        server,
        "mcp_action",
        {"phase": "confirm", "conversation_id": "c1", "dialogue_count": 5, "query": "yes"},
    )

    screenshot = out["screenshot"]
    assert set(screenshot) == {"status", "image_url", "expires_in_s", "usage"}
    assert screenshot["status"] == "captured"
    assert screenshot["image_url"].startswith(PUBLIC_BASE + "/")
    assert screenshot["expires_in_s"] == 900
    serialized = json.dumps(out)
    assert base64.b64encode(image).decode() not in serialized
    assert str(root) not in serialized
    assert "base64" not in serialized.lower()
