"""Spec 038 — gateway client envelope suite (task T007): outage vs
malformed vs clean, honest envelopes on every path (FR-009, R5)."""

from __future__ import annotations

import httpx
import pytest

from agentic_rag_mcp.task_gateway.client import TaskGatewayClient

URL = "http://127.0.0.1:9999"   # nothing listens — outage path


@pytest.fixture()
def client():
    return TaskGatewayClient(URL, connect_timeout_s=0.2, read_timeout_s=0.5)


class TestOutage:
    def test_unavailable_envelope_with_recovery(self, client):
        out = client.tier1("print", "printing broken", cid="c1")
        assert out["status"] == "error"
        assert "task-gateway-unavailable" in out["reason"]
        assert "task-gateway-service" in out["reason"]  # recovery text names the Scheduled Task

    def test_never_a_hang(self, client):
        import time
        t0 = time.monotonic()
        out = client.job_status("j1", cid="c1")
        assert time.monotonic() - t0 < 3
        assert out["status"] == "error"


class TestMalformed:
    def test_html_is_malformed_not_content(self, client):
        def handler(request):
            return httpx.Response(200, text="<html>502 Bad Gateway</html>")

        transport = httpx.MockTransport(handler)
        client._client = httpx.Client(transport=transport,
                                      timeout=httpx.Timeout(1.0))
        out = client.tier1("print", "x", cid="c1")
        assert out["status"] == "error"
        assert "malformed" in out["reason"]

    def test_json_with_unknown_recommendation_rejected(self, client):
        def handler(request):
            return httpx.Response(200, json={"recommendation": "maybe"})

        transport = httpx.MockTransport(handler)
        client._client = httpx.Client(transport=transport, timeout=httpx.Timeout(1.0))
        out = client.tier1("print", "x", cid="c1")
        assert out["status"] == "error"
        assert "malformed" in out["reason"] or "recommendation" in out["reason"]

    def test_clean_none_passes_through(self, client):
        def handler(request):
            return httpx.Response(200, json={
                "recommendation": "none",
                "actions": [{"name": "restart spooler", "ok": True}],
                "detail": "restarted"})

        transport = httpx.MockTransport(handler)
        client._client = httpx.Client(transport=transport, timeout=httpx.Timeout(1.0))
        out = client.tier1("print", "x", cid="c1")
        assert out["status"] == "ok"
        assert out["recommendation"] == "none"
        assert out["actions"][0]["ok"] is True

    def test_tier2_recommendation_shape(self, client):
        def handler(request):
            return httpx.Response(200, json={
                "recommendation": "tier2",
                "repair_name": "sfc_scan",
                "repair_text": "sfc /scannow",
                "actions": [], "detail": "tier2 advised"})

        transport = httpx.MockTransport(handler)
        client._client = httpx.Client(transport=transport, timeout=httpx.Timeout(1.0))
        out = client.tier1("general", "x", cid="c1")
        assert out["status"] == "ok" and out["recommendation"] == "tier2"
        assert out["repair_name"] == "sfc_scan"
        assert out["repair_text"] == "sfc /scannow"

    def test_job_shapes(self, client):
        def handler(request):
            if request.url.path.startswith("/api/office"):
                return httpx.Response(200, json={"job_id": "j9", "status": "queued"})
            return httpx.Response(200, json={
                "job_id": "j9", "kind": "office-install", "status": "running",
                "detail": "installing"})

        transport = httpx.MockTransport(handler)
        client._client = httpx.Client(transport=transport, timeout=httpx.Timeout(1.0))
        assert client.install("365", "Current", cid="c1")["job_id"] == "j9"
        out = client.job_status("j9", cid="c1")
        assert out["status"] == "ok" and out["job"]["status"] == "running"

    def test_job_not_found_honest(self, client):
        def handler(request):
            return httpx.Response(404, json={"error": "unknown job"})

        transport = httpx.MockTransport(handler)
        client._client = httpx.Client(transport=transport, timeout=httpx.Timeout(1.0))
        out = client.job_status("ghost", cid="c1")
        assert out["status"] == "error" and "not-found" in out["reason"]