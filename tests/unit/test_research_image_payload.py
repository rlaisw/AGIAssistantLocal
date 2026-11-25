"""Spec 050 unit pins: web_research hit assembly carries the images projection
(contract §1: always present, [] on every non-ok scrape, existing fields intact).
"""

import asyncio
import json

from agentic_rag_mcp.config import Config
from agentic_rag_mcp.server import build_server

HIT = {"title": "Trace Guide", "url": "https://docs.example/trace",
       "snippet": "How to trace a message."}

OK_SECTIONS = [{"heading": "Trace a message", "blocks": [
    {"type": "p", "text": "Open the dialog."},
    {"type": "img", "src": "https://docs.example/img/step1.png", "alt": "Open the dialog"},
    {"type": "img", "src": "https://docs.example/img/step2.png", "alt": ""},
]}]


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

    def __init__(self, hits):
        self._hits = hits

    def search(self, query: str, limit: int = 5):
        return self._hits[:limit]


def _server(tmp_path, monkeypatch, hits):
    import agentic_rag_mcp.server as server_mod
    from agentic_rag_mcp.search.web import research as research_mod

    monkeypatch.setattr(server_mod, "build_providers", lambda cfg: [FakeProvider(hits)])
    cfg = Config(state_db=tmp_path / "s.sqlite3", vector_dir=tmp_path / "v",
                 decider_enabled=False)
    return build_server(cfg), research_mod


def _scrape(status="ok", reason=None, sections=None):
    return {"url": HIT["url"], "sections": sections or [], "truncated": False,
            "status": status, "status_reason": reason}


def test_ok_hit_has_images_projection(tmp_path, monkeypatch):
    server, research_mod = _server(tmp_path, monkeypatch, [HIT])
    monkeypatch.setattr(research_mod, "research_pages",
                        lambda *a, **k: {HIT["url"]: _scrape(sections=OK_SECTIONS)})

    result = call(server, "web_research", {"query": "trace", "limit": 1})
    hit = result["hits"][0]
    assert hit["images"] == [
        {"url": "https://docs.example/img/step1.png", "alt": "Open the dialog",
         "heading": "Trace a message"},
        {"url": "https://docs.example/img/step2.png", "alt": "",
         "heading": "Trace a message"},
    ]
    # existing fields untouched
    assert hit["title"] == HIT["title"]
    assert hit["snippet"] == HIT["snippet"]
    assert hit["content"] == "Trace a message\nOpen the dialog.\n[image: https://docs.example/img/step1.png]\n[image: https://docs.example/img/step2.png]"
    assert hit["scrape"]["status"] == "ok"
    assert hit["render_html"].startswith("<!DOCTYPE html>")


def test_non_ok_scrapes_yield_empty_images_list(tmp_path, monkeypatch):
    for status, reason in [("fallback", "no-extractable-content"),
                           ("blocked", "ssrf:private-ip"),
                           ("failed", "fetch-error"),
                           ("fallback", "not-attempted")]:
        server, research_mod = _server(tmp_path, monkeypatch, [HIT])
        monkeypatch.setattr(research_mod, "research_pages",
                            lambda *a, **k: {HIT["url"]: _scrape(status=status, reason=reason)})
        hit = call(server, "web_research", {"query": "trace", "limit": 1})["hits"][0]
        assert hit["images"] == [], status
        assert "images" in hit


def test_image_less_ok_page_yields_empty_list(tmp_path, monkeypatch):
    sections = [{"heading": "Text only", "blocks": [{"type": "p", "text": "No images."}]}]
    server, research_mod = _server(tmp_path, monkeypatch, [HIT])
    monkeypatch.setattr(research_mod, "research_pages",
                        lambda *a, **k: {HIT["url"]: _scrape(sections=sections)})
    hit = call(server, "web_research", {"query": "trace", "limit": 1})["hits"][0]
    assert hit["images"] == []
