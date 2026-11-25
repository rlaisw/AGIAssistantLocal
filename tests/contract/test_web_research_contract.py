"""Contract: web_research response schema v1 (FR-011 search half; D6 rows 10, 13)
and the web_search freeze canary (FR-002 / SC-001)."""

import asyncio
import json

import pytest

from agentic_rag_mcp.config import Config
from agentic_rag_mcp.errors import ProviderError
from agentic_rag_mcp.server import build_server


def call(server, name, args):
    raw = asyncio.run(server.call_tool(name, args))
    structured = [b["result"] for b in raw if isinstance(b, dict) and "result" in b]
    if structured:
        return structured[0]
    texts = [getattr(b, "text", "") for b in raw if getattr(b, "text", "")]
    joined = "".join(texts).strip()
    return json.loads(joined) if joined else None


class FakeProvider:
    name = "searxng"

    def __init__(self, hits=None, error=False):
        self._hits = hits or []
        self._error = error

    def search(self, query: str, limit: int = 5):
        if self._error:
            raise ProviderError("searxng failed")
        return self._hits[:limit]


HITS = [{"title": "Trace Guide", "url": "https://docs.example/trace",
         "snippet": "How to trace a message."}]


def _server(tmp_path, monkeypatch, provider):
    import agentic_rag_mcp.server as server_mod

    monkeypatch.setattr(server_mod, "build_providers", lambda cfg: [provider])
    cfg = Config(state_db=tmp_path / "s.sqlite3", vector_dir=tmp_path / "v",
                 decider_enabled=False)
    return build_server(cfg)


def test_web_research_schema_v2(tmp_path, monkeypatch):
    srv = _server(tmp_path, monkeypatch, FakeProvider(HITS))
    out = call(srv, "web_research", {"query": "how to trace an email", "limit": 3})
    assert out["query"] == "how to trace an email"
    assert out["engines_used"] == ["searxng"]
    assert isinstance(out["elapsed_ms"], int) and out["elapsed_ms"] >= 0
    assert out["error"] is None
    h = out["hits"][0]
    assert h["title"] == "Trace Guide" and h["url"] == "https://docs.example/trace"
    assert h["snippet"] == "How to trace a message." and h["engine"] == "searxng"
    assert set(h["scrape"]) >= {"url", "status", "status_reason", "sections", "truncated"}
    assert isinstance(h["content"], str) and h["content"]          # SC-004: never empty
    assert h["render_html"].startswith("<!DOCTYPE html>")          # invariant 9: inline artifact
    assert "<title>Trace Guide</title>" in h["render_html"]
    assert "https://docs.example/trace" in h["render_html"]


def test_web_research_limit_capped_at_max_pages(tmp_path, monkeypatch):
    many = [{"title": f"r{i}", "url": f"https://x.example/{i}", "snippet": "s"} for i in range(10)]
    srv = _server(tmp_path, monkeypatch, FakeProvider(many))
    out = call(srv, "web_research", {"query": "q", "limit": 10})
    assert len(out["hits"]) == 3          # config max_pages = 3 (cap 5, research D8)


def test_web_research_all_engines_down_honest_empty(tmp_path, monkeypatch):
    srv = _server(tmp_path, monkeypatch, FakeProvider(error=True))
    out = call(srv, "web_research", {"query": "q"})
    assert out["hits"] == [] and out["engines_used"] == []
    assert out["error"] is not None       # never fabricated (US1-AC4)


def test_web_search_stays_byte_identical_without_engine_field(tmp_path, monkeypatch):
    """FR-002 / SC-001: the frozen tool's hits are exactly today's shape."""
    srv = _server(tmp_path, monkeypatch, FakeProvider(HITS))
    out = call(srv, "web_search", {"query": "trace"})
    assert out == HITS                    # no engine key, no extra fields


# ---- spec 050: additive images field (contract web-research-images.md) ----

def test_hits_carry_images_field(tmp_path, monkeypatch):
    from agentic_rag_mcp.search.web import research as research_mod

    server = _server(tmp_path, monkeypatch, FakeProvider(hits=HITS))
    monkeypatch.setattr(research_mod, "research_pages", lambda *a, **k: {
        HITS[0]["url"]: {"url": HITS[0]["url"], "truncated": False, "status": "ok",
                         "status_reason": None,
                         "sections": [{"heading": "Trace", "blocks": [
                             {"type": "img", "src": "https://docs.example/i.png",
                              "alt": 'a "quoted"\nline'}]}]},
    })
    result = call(server, "web_research", {"query": "trace", "limit": 1})
    hit = result["hits"][0]
    assert isinstance(hit["images"], list)
    ref = hit["images"][0]
    assert set(ref) == {"url", "alt", "heading"}
    assert ref["url"].startswith("https://") and ref["alt"] == 'a "quoted"\nline'
    assert json.loads(json.dumps(hit)) == hit                     # serializes/re-parses


def test_fallback_hit_has_empty_images(tmp_path, monkeypatch):
    from agentic_rag_mcp.search.web import research as research_mod

    server = _server(tmp_path, monkeypatch, FakeProvider(hits=HITS))
    monkeypatch.setattr(research_mod, "research_pages", lambda *a, **k: {
        HITS[0]["url"]: {"url": HITS[0]["url"], "sections": [], "truncated": False,
                         "status": "fallback", "status_reason": "timeout"},
    })
    hit = call(server, "web_research", {"query": "trace", "limit": 1})["hits"][0]
    assert hit["images"] == []


def test_fetch_url_images_remain_strings(tmp_path, monkeypatch):
    import httpx
    import agentic_rag_mcp.server as server_mod

    server = _server(tmp_path, monkeypatch, FakeProvider(hits=HITS))

    def fake_get(*a, **k):
        req = httpx.Request("GET", "https://docs.example/trace")
        return httpx.Response(200, request=req, text='<img src="/a.png"><img src="/b.png">')

    monkeypatch.setattr(server_mod.httpx, "get", fake_get)
    result = call(server, "fetch_url", {"url": "https://docs.example/trace"})
    assert result["images"] == ["https://docs.example/a.png", "https://docs.example/b.png"]
    assert all(isinstance(u, str) for u in result["images"])
