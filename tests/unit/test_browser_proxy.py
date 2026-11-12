"""Dynamic-lane v2 (2026-11-12 speed revision): the single-hop Playwright
proxy — session handshake (Host allowlist override, mcp-session-id, SSE
frames), trimmed reads, honest-unavailable envelopes on every failure."""

from __future__ import annotations

import json

import httpx
import pytest

from agentic_rag_mcp.browser_lanes.proxy import PlaywrightProxy

BASE = "http://172.17.0.1:13002"


def _sse(obj: dict) -> httpx.Response:
    body = "event: message\ndata: " + json.dumps(obj) + "\n\n"
    return httpx.Response(200, text=body,
                          headers={"mcp-session-id": "sess-1"})


class TestHandshake:
    def test_open_sets_host_and_session(self):
        seen = {}

        def handler(request):
            seen["host"] = request.headers.get("host")
            seen["url"] = str(request.url)
            body = json.loads(request.content)
            seen.setdefault("methods", []).append(body.get("method"))
            if request.headers.get("mcp-session-id"):
                seen["sid"] = request.headers["mcp-session-id"]
                return _sse({"result": {"content": []}})
            return _sse({"result": {"protocolVersion": "2025-03-26"}})

        px = PlaywrightProxy(BASE)
        px._client = httpx.Client(transport=httpx.MockTransport(handler))
        px.open()
        assert seen["host"] == "localhost:3002"  # the allowlist override
        assert seen["url"].endswith("/mcp")
        assert seen["methods"][0] == "initialize"
        assert seen["methods"][-1] == "notifications/initialized"
        assert px._session_id == "sess-1"

    def test_call_parses_sse_content(self):
        def handler(request):
            return _sse({"result": {"content": [
                {"type": "text", "text": "page says 22C sunny"}]}})

        px = PlaywrightProxy(BASE)
        px._session_id = "sess-1"
        px._client = httpx.Client(transport=httpx.MockTransport(handler))
        out = px.call("browser_evaluate", {"function": "() => 1"})
        assert out == {"status": "ok", "text": "page says 22C sunny"}

    def test_dead_server_is_honest_unavailable(self):
        def handler(request):
            raise httpx.ConnectError("refused")

        px = PlaywrightProxy(BASE)
        px._client = httpx.Client(transport=httpx.MockTransport(handler))
        with pytest.raises(ConnectionError) as ei:
            px.open()
        msg = str(ei.value.args[0])
        assert "browser-lane-unavailable" in msg
        assert "playwright-mcp-server" in msg  # the recovery hint


class TestTrimmedPrimitives:
    def test_read_text_trims(self):
        def handler(request):
            body = json.loads(request.content)
            args = body["params"]["arguments"]
            assert body["params"]["name"] == "browser_evaluate"
            assert "innerText" in args["function"]
            return _sse({"result": {"content": [
                {"type": "text", "text": "x" * 9000}]}})

        px = PlaywrightProxy(BASE, timeout_s=5)
        px._session_id = "sess-1"
        px._client = httpx.Client(transport=httpx.MockTransport(handler))
        out = px.read_text(max_chars=4000)
        assert out["status"] == "ok"
        assert len(out["text"]) == 4000  # TRIMMED — not the full tree

    def test_navigate_passes_url(self):
        def handler(request):
            body = json.loads(request.content)
            assert body["params"]["arguments"] == {"url": "https://x"}
            return _sse({"result": {"content": [
                {"type": "text", "text": "Page loaded"}]}})

        px = PlaywrightProxy(BASE)
        px._session_id = "sess-1"
        px._client = httpx.Client(transport=httpx.MockTransport(handler))
        assert px.navigate("https://x")["status"] == "ok"

    def test_click_text_builds_js_with_needle(self):
        def handler(request):
            body = json.loads(request.content)
            fn = body["params"]["arguments"]["function"]
            assert "next page" in fn and ".click()" in fn
            return _sse({"result": {"content": [
                {"type": "text", "text": "clicked"}]}})

        px = PlaywrightProxy(BASE)
        px._session_id = "sess-1"
        px._client = httpx.Client(transport=httpx.MockTransport(handler))
        out = px.click_text("Next Page")
        assert out["status"] == "ok" and "clicked" in out["text"]


class TestErrorShapes:
    def test_tool_error_relays_reason(self):
        def handler(request):
            return _sse({"error": {"message": "browser is closed"}})

        px = PlaywrightProxy(BASE)
        px._session_id = "sess-1"
        px._client = httpx.Client(transport=httpx.MockTransport(handler))
        out = px.call("browser_snapshot", {})
        assert out["status"] == "error"
        assert "browser is closed" in out["reason"]

    def test_is_error_content_is_error(self):
        def handler(request):
            return _sse({"result": {"content": [
                {"type": "text", "text": "Navigation failed: timeout"}],
                "isError": True}})

        px = PlaywrightProxy(BASE)
        px._session_id = "sess-1"
        px._client = httpx.Client(transport=httpx.MockTransport(handler))
        out = px.call("browser_navigate", {"url": "https://x"})
        assert out["status"] == "error"