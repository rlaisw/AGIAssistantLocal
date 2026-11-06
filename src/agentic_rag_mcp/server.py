"""FastMCP stdio server: ask, search, sources.*, status, graph.query."""

from __future__ import annotations

import argparse
import logging
import re
import uuid
from pathlib import Path
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import FastMCP, Context

from .agents import synthesis
from .agents.reflexion import ReflexionAgent
from .agents.tools import make_vector_tool, make_web_tool
from .config import Config, init_config, load_config
from .errors import FeatureDisabledError, NotFoundError, SourceAuthError
from .ingestion.pipeline import IngestionPipeline
from .ingestion.watchers import Watcher
from .logging_setup import configure_logging, current_setup
from .routing import decision as decision_mod
from .office_state import OfficeState
from .search.embeddings import Embedder

_office_state = OfficeState()


def get_office_state() -> OfficeState:
    """The Office lanes' conversation state (spec 030, research R4)."""
    return _office_state
from .search.graphify_search import GraphifySearch
from .search.web.base import build_providers, search_all
from .sources.sqlite_source import SqliteSource
from .store.state import StateStore
from .store.vectordb import VectorStore

log = logging.getLogger("agentic_rag_mcp")


_IMG_SRC_RE = re.compile(r"""<img[^>]+(?:src|data-src)=["']([^"']+)["']""", re.I)
_IMG_SKIP = ("pixel", "tracker", "beacon", "spacer", "1x1", "blank.gif")


def _fetch_url(url: str, max_chars: int = 4000) -> dict:
    """Fetch a live web page (httpx). Shared by the MCP tool and the deep loop.

    Returns page text plus `images`: every <img> source on the page, absolutized
    against the final URL (lazy data-src and relative paths included), with
    obvious trackers stripped — so the caller can inline step screenshots
    (2026-10-27 user request: collect as many page images as possible).
    """
    if not url.startswith(("http://", "https://")):
        raise ValueError("url must be http(s)")
    resp = httpx.get(url, timeout=20.0, follow_redirects=True,
                     headers={"User-Agent": "agentic-rag-mcp/0.1"})
    final_url = str(resp.url)
    images: list[str] = []
    seen: set[str] = set()
    for src in _IMG_SRC_RE.findall(resp.text):
        abs_url = urljoin(final_url, src.strip())
        low = abs_url.lower()
        if not abs_url.startswith(("http://", "https://")) or abs_url in seen:
            continue
        if any(bad in low for bad in _IMG_SKIP):
            continue
        seen.add(abs_url)
        images.append(abs_url)
    return {
        "url": final_url,
        "status": resp.status_code,
        "date_utc": resp.headers.get("date", ""),
        "text": resp.text[:max_chars],
        "images": images,
    }


def _onedrive_auth(src: dict):
    """MSAL auth for a stored onedrive source (delegated device flow or app-only)."""
    from pathlib import Path as _P

    from .sources.graph_auth import ClientCredentialsAuth, GraphAuth

    cfg = src["config"]
    if cfg.get("client_secret"):  # app-only auth — no user sign-in
        return ClientCredentialsAuth(cfg["client_id"], cfg["client_secret"],
                                     cfg.get("tenant_id", "common"))
    token_path = _P.home() / ".config/agentic-rag-mcp/tokens" / f"{src['id']}.json"
    return GraphAuth(cfg["client_id"], token_path, cfg.get("tenant_id", "common"))


def _onedrive_source(src: dict):
    from .sources.onedrive import OneDriveSource

    return OneDriveSource(_onedrive_auth(src), src["config"])


def build_server(cfg: Config | None = None, **fastmcp_kwargs) -> FastMCP:
    """Build the MCP server. `fastmcp_kwargs` override FastMCP settings
    (e.g. stateless_http=True for Dify's streamable-HTTP client)."""
    cfg = cfg or load_config()
    configure_logging(cfg)  # spec 008: file+console setup before anything serves
    state = StateStore(cfg.state_db)
    vectors = VectorStore(cfg.vector_dir)
    embedder = Embedder(cfg.embedding_model, cfg.embedding_device)
    pipeline = IngestionPipeline(state, vectors, embedder)
    # one-time migration (FR-016): legacy snapshot-less onedrive docs re-embed once;
    # wrapped — a migration failure never blocks server start (retried next startup)
    try:
        pipeline.migrate_onedrive_sources(
            {s["id"]: _onedrive_source(s) for s in state.list_sources()
             if s["type"] == "onedrive"})
    except Exception as exc:  # noqa: BLE001
        log.warning("onedrive migration skipped: %s", exc)
    watcher = Watcher(pipeline, state)
    watcher.start()

    web_providers = build_providers(cfg)
    graphify = GraphifySearch(Path("graphify-out/graph.json"), enabled=cfg.graphify_enabled)

    def _web_evidence(query: str, limit: int = 3) -> list[dict]:
        """FR-012: grouped web content as reflexion evidence (internal shape) —
        the snippet field carries the bounded, grouped page text so synthesis
        and citations consume it unchanged; document_id = url for citations."""
        from .search.web.research import research_pages, sections_to_text

        hits, _, _ = search_all(web_providers, query, limit)
        scrapes = research_pages(
            hits, t0=__import__("time").perf_counter(),
            fetch_timeout_s=cfg.research_fetch_timeout_s,
            per_page_chars=cfg.research_per_page_chars,
            overall_timeout_s=cfg.research_overall_timeout_s,
            max_concurrent=cfg.research_max_concurrent,
        )
        out = []
        for h in hits:
            scrape = scrapes.get(h["url"])
            content = (sections_to_text(scrape["sections"])
                       if scrape and scrape["status"] == "ok" and scrape["sections"]
                       else h["snippet"])
            if content:
                out.append({"title": h["title"], "url": h["url"], "snippet": content,
                            "document_id": h["url"]})
        return out

    agent_tools = {
        "vector_search": make_vector_tool(vectors, embedder),
        "web_search": _web_evidence,
        "fetch_url": _fetch_url,
    }
    if cfg.graphify_enabled:
        agent_tools["graphify"] = lambda q, limit=5: [
            {"content": graphify.explain(q)["answer"], "title": f"graph:{q}",
             "document_id": f"graphify:{q}"}
        ]
    agent = ReflexionAgent(agent_tools, cfg.max_iterations)

    fastmcp_kwargs.setdefault("host", cfg.mcp_host)
    fastmcp_kwargs.setdefault("port", cfg.mcp_port)
    mcp = FastMCP("agentic-rag-mcp", **fastmcp_kwargs)
    mcp._cfg = cfg  # live config handle for tests/ops (recovery toggles, status probes)
    if cfg.decider_enabled:
        from .routing import laya_runtime

        laya_runtime.warm_up(cfg)  # pre-load the decision model in the background

    def degraded_sources() -> list[str]:
        return [s["id"] for s in state.list_sources() if s["health"] != "healthy"]

    def _require_onedrive(source_id: str) -> dict:
        src = state.get_source(source_id)
        if not src:
            log.warning("source not found: %s", source_id)  # no silent failures (FR-002)
            raise NotFoundError(f"source not found: {source_id}")
        if src["type"] != "onedrive":
            log.warning("source %s is not a onedrive source", source_id)
            raise NotFoundError(f"source {source_id} is not a onedrive source")
        return src

    def route_question(question: str):
        """FR-001/FR-003: the decision node is primary; keyword heuristic only on outage."""
        if cfg.decider_enabled:
            d = decision_mod.decide(question, cfg)
            if d.valid:
                return d
        return decision_mod.fallback_route(question)

    @mcp.tool()
    def ask(question: str, collections: list[str] | None = None, mode: str = "auto",
            max_iterations: int | None = None) -> dict:
        """Answer a question with agentic retrieval and per-source citations."""
        request_id = uuid.uuid4().hex[:8]
        log.debug("ask[%s]: %s", request_id, question[:120])  # question text: DEBUG-only
        d = route_question(question)
        # forced modes override execution, not the decision itself (FR-001: every request decided)
        if mode == "fast":
            exec_route, classifier = "direct_retrieval", "forced"
        elif mode == "deep":
            exec_route, classifier = "deliberative_reasoning", "forced"
        else:
            exec_route = d.route
            classifier = d.provenance  # "decision_node" | "fallback"
        log.debug("routing[%s]: %s (%s)", request_id, exec_route, classifier)  # trace point
        agent._budget = max_iterations or cfg.max_iterations
        if exec_route in ("direct_retrieval", "source_management"):
            if exec_route == "source_management":
                # FR-005: guidance only, never operations. Misroute safety: a strong KB
                # match (Lance distance <= 1.0; measured 0.7 real vs 1.9 fuzzy) means
                # this was actually a knowledge question — answer it from the KB.
                hits = make_vector_tool(vectors, embedder)(question)
                if hits and hits[0].get("score", 99) <= 1.0:
                    answer = synthesis.synthesize(question, hits, "normal")
                    citations = synthesis.citations(hits)
                else:
                    answer = ("This looks like a source-management request. Use the sources_list, "
                              "sources_add, sources_sync, or sources_remove tools to manage the "
                              "knowledge base — they perform the actual operations.")
                    citations = []
            else:
                hits = make_vector_tool(vectors, embedder)(question)
                log.debug("retrieval[%s]: %d hits", request_id, len(hits))  # trace point
                if hits:
                    answer = synthesis.synthesize(question, hits, "normal")
                    citations = synthesis.citations(hits)
                else:
                    answer = "No relevant information was found in the available sources."
                    citations = []
            if exec_route == "source_management":
                suff, plan = "satisfied", []
            else:
                suff = "satisfied" if hits else "exhausted"
                plan = [{"id": "t1", "tool": "vector_search", "input": question}]
            result = {
                "answer": answer, "confidence": "normal", "classification": "fast",
                "classifier": classifier, "citations": citations, "iterations": 0,
                "sufficiency": suff, "error": None, "plan": plan, "reflections": [],
                "trace": [{"tool": "vector_search", "query": question, "hits": len(hits)}],
                "degraded_sources": degraded_sources(),
            }
        else:
            result = agent.run(question, web_first=(exec_route == "live_web"))
            result["classifier"] = classifier
            result["degraded_sources"] = degraded_sources()
        # freshness probe (FR-010): cited onedrive files only; a reminder is a
        # prompt — it never downloads (FR-011); failures never break the answer
        warnings: list[dict] = []
        try:
            onedrive_srcs = {s["id"]: s for s in state.list_sources() if s["type"] == "onedrive"}
            doc_refs = [c["ref"] for c in result.get("citations", [])
                        if c.get("kind") == "document"]
            if onedrive_srcs and doc_refs:
                from .sources.onedrive_freshness import probe_cited

                warnings = probe_cited(
                    doc_refs, state,
                    {sid: _onedrive_source(src) for sid, src in onedrive_srcs.items()})
        except Exception:  # noqa: BLE001 — probe is best-effort, never blocks the answer
            warnings = []
        if warnings:
            result["answer"] = result["answer"] + "\n\n" + "\n".join(
                w["message"] for w in warnings)
        result["freshness_warnings"] = warnings
        result["degraded_sources"] = degraded_sources()  # refresh after probe auth-fails
        result["decision"] = d.to_dict()  # FR-014: full System 1 trace on every response
        log.info("ask answered: %d citations, confidence=%s, classifier=%s",
                 len(result.get("citations", [])), result.get("confidence", "normal"),
                 result.get("classifier", "unknown"))
        state.save_session({"question": question, "classification": result.get("classification"),
                            "classifier": classifier, "plan": result.get("plan", []),
                            "iterations": result.get("iterations", 0),
                            "sufficiency": result.get("sufficiency"),
                            "answer": result["answer"], "confidence": result.get("confidence"),
                            "citations": result.get("citations", [])})
        return result

    @mcp.tool()
    def search(query: str, collections: list[str] | None = None, limit: int = 5) -> list[dict]:
        """Direct vector search without synthesis."""
        log.debug("tool search: %r (limit=%s)", query, limit)
        return make_vector_tool(vectors, embedder)(query, limit=limit)

    @mcp.tool()
    def web_search(query: str, limit: int = 5) -> list[dict]:
        """Live web search via configured providers (SearXNG first; falls back to Tavily/Exa). Returns [{title, url, snippet}]."""
        log.debug("tool web_search: %r (limit=%s)", query, limit)
        return make_web_tool(web_providers)(query, limit=limit)

    @mcp.tool()
    def specialty_profiles() -> dict:
        """List available specialty search profiles with their sites and descriptions.
        Call this first to discover which profiles exist, then use specialty_search."""
        from .search.web.specialty import load_profiles

        path = cfg.specialty_profiles_file or None
        profiles, error = load_profiles(path, return_error=True)
        if error:
            return {"error": error, "profiles": {}}
        return profiles

    @mcp.tool()
    def specialty_search(query: str, profile: str, limit: int = 5) -> list[dict] | dict:
        """Domain-scoped web search: results only from the profile's configured sites.
        The domain restriction is a hard filter (site: operator + post-filter)."""
        from .search.web.specialty import (
            construct_scoped_query,
            filter_by_domains,
            load_profiles,
            resolve_profile,
        )

        path = cfg.specialty_profiles_file or None
        profiles, file_error = load_profiles(path, return_error=True)
        if file_error:
            return {"error": file_error}                         # FR-004
        resolved = resolve_profile(profiles, profile)
        if "error" in resolved:
            return resolved                                      # FR-007/008
        scoped_query = construct_scoped_query(resolved["sites"], query)
        hits, _, _ = search_all(web_providers, scoped_query, limit)
        return filter_by_domains(hits, resolved["sites"])       # FR-006

    @mcp.tool()
    def web_research(query: str, limit: int = 6) -> dict:
        """Grouped web research: multi-engine search via the provider chain, then a
        per-page outline-preserving scrape (sections keep text + belonging image in
        document order), bounded for the LLM, with honest snippet fallbacks and a
        standalone rendered HTML artifact per page (spec 003, FR-011)."""
        import time as _time

        from .search.web.research import render_page, research_pages, sections_to_text

        limit = max(1, min(limit, cfg.research_max_pages))
        started = _time.perf_counter()
        hits, engines_used, error = search_all(web_providers, query, limit)
        scrapes = research_pages(
            hits, t0=started, fetch_timeout_s=cfg.research_fetch_timeout_s,
            per_page_chars=cfg.research_per_page_chars,
            overall_timeout_s=cfg.research_overall_timeout_s,
            max_concurrent=cfg.research_max_concurrent,
        )
        out_hits = []
        for h in hits:
            scrape = scrapes.get(h["url"], {"url": h["url"], "sections": [],
                                            "truncated": False, "status": "failed",
                                            "status_reason": "not-attempted"})
            ok = scrape["status"] == "ok" and scrape["sections"]
            # honest content (FR-008/SC-004): grouped sections when ok, else the snippet
            content = sections_to_text(scrape["sections"]) if ok else h["snippet"]
            render = (render_page(scrape["sections"], h["url"], h["title"]) if ok
                      else render_page([], h["url"], h["title"],
                                       fallback_snippet=h["snippet"] or None))
            out_hits.append({**h, "scrape": scrape, "content": content,
                             "render_html": render})
        return {
            "query": query,
            "engines_used": engines_used,
            "elapsed_ms": int((_time.perf_counter() - started) * 1000),
            "error": error,
            "hits": out_hits,
        }

    @mcp.tool()
    def fetch_url(url: str, max_chars: int = 4000) -> dict:
        """Fetch a live web page. Returns page text plus the server's `date_utc`
        (HTTP Date header = live UTC clock) — use it for current time/date
        questions instead of trusting cached search snippets."""
        return _fetch_url(url, max_chars)

    @mcp.tool()
    def sources_add(type: str, config: dict) -> dict:
        """Register a source. Types: local_folder, sqlite, onedrive."""
        log.debug("tool sources_add: %s %s", type, config)
        if type == "local_folder":
            source_id = state.add_source(type, config)
            stats = pipeline.sync_local_folder(source_id, config["path"])
        elif type == "sqlite":
            source_id = state.add_source(type, config)
            stats = pipeline.sync_sqlite(
                source_id, SqliteSource(config["db_path"], config["table"],
                                        config.get("template", "{row}")))
        elif type == "onedrive":
            if not config.get("client_id"):
                raise NotFoundError("onedrive source requires config.client_id")
            source_id = state.add_source(type, {
                "client_id": config["client_id"],
                "tenant_id": config.get("tenant_id", "common"),
                "client_secret": config.get("client_secret", ""),
                "user": config.get("user", ""),
                "folder_path": config.get("folder_path", "/"),
                "include_subfolders": config.get("include_subfolders", True),
                "max_file_size_mb": config.get("max_file_size_mb", 50),
            })
            try:
                _onedrive_source(state.get_source(source_id))._auth.token()  # existing token? (FR-002)
            except Exception:  # noqa: BLE001 — no token yet is expected for new sources
                state.set_health(source_id, "degraded", "needs sign-in")
                return {"source_id": source_id, "status": "needs_auth",
                        "message": "Call sources_auth to complete Microsoft sign-in."
                        if not config.get("client_secret")
                        else "Client credentials failed — check tenant_id/client_secret and Files.Read.All application permission."}
            # credentials verified — on-demand source registered; ingestion happens
            # ONLY via onedrive_embed_files (spec 007: never auto-synced)
            return {"source_id": source_id, "status": "ok",
                    "sync": {"message": "registered; on-demand source — use onedrive_list_files and onedrive_embed_files"}}
        else:
            raise NotFoundError(f"unsupported source type for manual add: {type}")
        return {"source_id": source_id, "status": "ok", "sync": stats}

    @mcp.tool()
    def sources_auth(source_id: str) -> dict:
        """Complete Microsoft sign-in for a OneDrive source (device code flow).
        Returns the sign-in URL and user code; the connection completes in the
        background after the user signs in. Call again to check status."""
        log.debug("tool sources_auth: %s", source_id)
        import threading
        from pathlib import Path as _P

        from .sources.graph_auth import GraphAuth

        sources = state.get_source(source_id)
        if not sources:
            raise NotFoundError(f"source not found: {source_id}")
        if sources["type"] != "onedrive":
            raise NotFoundError(f"source {source_id} is not a onedrive source")
        client_id = sources["config"]["client_id"]
        token_path = _P.home() / ".config/agentic-rag-mcp/tokens" / f"{source_id}.json"
        auth = GraphAuth(client_id, token_path, sources["config"].get("tenant_id", "common"))

        try:
            auth.token()  # already authenticated (FR-003: already_authenticated)
            return {"status": "already_authenticated",
                    "message": "This source has a valid token."}
        except Exception as exc:  # noqa: BLE001 — needs sign-in (expected, not a failure)
            log.debug("no valid token yet: %s", exc)

        # initiate device flow non-blocking (research.md D3) — ONE flow: the code
        # shown to the user is the code the background thread completes
        def _complete_sign_in():
            try:
                auth.device_sign_in(flow)
                state.set_health(source_id, "healthy", None)  # auth only — no ingestion (FR-002)
            except Exception as exc:  # noqa: BLE001
                state.set_health(source_id, "degraded", str(exc))

        try:
            flow = auth.begin_device_flow()
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "message": f"failed to start sign-in: {exc}"}

        # return URL+code immediately; background thread waits for completion
        threading.Thread(target=_complete_sign_in, daemon=True).start()
        return {
            "status": "sign_in_required",
            "sign_in_url": flow.get("verification_uri", "https://microsoft.com/devicelogin"),
            "user_code": flow["user_code"],
            "message": "Visit the URL, enter the code, and sign in with your Microsoft "
                       "account. The connection completes automatically.",
        }

    @mcp.tool()
    def sources_list() -> list[dict]:
        """List sources with health and sync metadata."""
        log.debug("tool sources_list")
        return [
            {"id": s["id"], "type": s["type"], "health": s["health"],
             "health_reason": s["health_reason"], "last_sync_at": s["last_sync_at"],
             "doc_hint": s["config"]}
            for s in state.list_sources()
        ]

    @mcp.tool()
    def sources_remove(source_id: str) -> dict:
        """Remove a source; drops documents whose last origin was this source."""
        log.debug("tool sources_remove: %s", source_id)
        deleted = state.remove_source(source_id)
        for doc_id in deleted:
            vectors.delete_document(vectors.default_collection(), doc_id)
        return {"removed": source_id, "documents_deleted": len(deleted)}

    @mcp.tool()
    def sources_sync(source_id: str | None = None) -> dict:
        """Manually trigger incremental sync (local_folder/sqlite). OneDrive sources
        are on-demand: use onedrive_embed_files to embed chosen files."""
        log.debug("tool sources_sync: %s", source_id)
        if source_id:
            src = state.get_source(source_id)
            if src and src["type"] == "onedrive":
                return {source_id: {"status": "on_demand",
                                   "message": "OneDrive sources are on-demand; use onedrive_embed_files to embed chosen files."}}
            results = watcher.sync_once()
            return {source_id: results.get(source_id, {"error": "unknown source"})}
        return watcher.sync_once()

    @mcp.tool()
    def onedrive_list_files(source_id: str, search: str = "", folder: str = "",
                            limit: int = 100) -> dict:
        """Browse OneDrive file metadata (path, name, size, modified time) without
        downloading content. Filter by name with `search`; scope with `folder`.
        OneDrive is on-demand: embed chosen files with onedrive_embed_files."""
        log.debug("tool onedrive_list_files: %s (search=%r)", source_id, search)
        src = _require_onedrive(source_id)
        try:
            out = _onedrive_source(src).list_files(search=search, folder=folder or None,
                                                  limit=limit)
        except SourceAuthError:
            state.set_health(source_id, "degraded", "needs sign-in")
            raise
        state.set_health(source_id, "healthy", None)
        root = folder or src["config"].get("folder_path", "/") or "/"
        return {"source_id": source_id, "folder": root, "files": out["files"],
                "truncated": out["truncated"]}

    @mcp.tool()
    def onedrive_embed_files(source_id: str, files: list) -> dict:
        """Embed ONLY the named OneDrive files (paths and/or item ids), one-time.
        Never syncs the drive. Returns per-file outcomes with honest reasons;
        mid-batch cloud failures continue the batch (re-run for failed files)."""
        log.debug("tool onedrive_embed_files: %s %s", source_id, list(files))
        src = _require_onedrive(source_id)
        try:
            out = pipeline.embed_onedrive_files(source_id, _onedrive_source(src), list(files))
        except SourceAuthError:
            state.set_health(source_id, "degraded", "needs sign-in")
            raise
        state.set_health(source_id, "healthy", None)
        return out

    @mcp.tool()
    def graph_query(query: str) -> dict:
        """Optional graph search (Graphify layer); disabled by default."""
        if not cfg.graphify_enabled:
            raise FeatureDisabledError("graphify layer disabled; enable in config.features")
        return graphify.explain(query)

    @mcp.tool()
    def status() -> dict:
        """Server health: decision node, per-source health, index counters."""
        probe = route_question("status probe")
        decider = probe.provenance  # "decision_node" | "fallback"
        stats = vectors.stats()
        return {
            "version": "0.1.0",
            "decision_layer": decider,
            "sources": sources_list(),
            "index": {"documents": state.doc_count(), "chunks": stats["chunks"],
                      "collections": stats["collections"]},
            "logging": current_setup().status_dict(),  # additive (spec 008, FR-012)
        }

    # ---- PPT-Master tools (spec 009): bridge to the ppt-master toolchain ----

    from .ppt import bridge as ppt_bridge
    from .ppt.errors import PptError, envelope as _ppt_envelope

    def _ppt(fn, *args, **kwargs):
        """Run a bridge call; PptError -> honest envelope (FR-010, Constitution IV)."""
        try:
            return fn(cfg, *args, **kwargs)
        except PptError as exc:
            log.warning("ppt tool error: %s", exc.code if hasattr(exc, "code") else exc)
            return _ppt_envelope(exc)

    @mcp.tool()
    def ppt_project_init(name: str) -> dict:
        """Create an isolated PPT generation workspace. Returns {project_id, workspace, max_pages}.
        Start every deck here; use the returned project_id in all other ppt_* tools."""
        return _ppt(ppt_bridge.project_init, name)

    @mcp.tool()
    def ppt_icon_sync(project_id: str, icons: list[str]) -> dict:
        """Prepare icons for a PPT project: syncs resolvable 'library/name' references into it.
        Missing icons are reported honestly with re-pick guidance — never substituted."""
        return _ppt(ppt_bridge.icon_sync, project_id, icons)

    @mcp.tool()
    def ppt_write_page(project_id: str, page_number: int, name: str, svg: str) -> dict:
        """Write one slide page as a complete SVG document (root viewBox='0 0 1280 720',
        grouped zones with data-pptx-bounds, native text). Page numbers run 1..max_pages."""
        return _ppt(ppt_bridge.write_page, project_id, page_number, name, svg)

    @mcp.tool()
    def ppt_check(project_id: str) -> dict:
        """Run the slide quality gate. Returns {passing, blocking_errors, warnings, details};
        each [ERROR] detail names the file and the fixable issue. Fix pages, then re-check."""
        return _ppt(ppt_bridge.check, project_id)

    @mcp.tool()
    def ppt_export(project_id: str) -> dict:
        """Export the deck as a native editable .pptx (only after ppt_check passes).
        Returns {file, url} — the url is a clickable download link for the chat answer."""
        return _ppt(ppt_bridge.export_pptx, project_id)

    # ---- AntV visualization tools (spec 012): charts + infographics ----

    from .antv import charts as antv_charts_mod
    from .antv import infographic as antv_infographic_mod
    from .antv.errors import AntvError, envelope as _antv_envelope

    def _antv(fn, *args):
        """Run an antv tool body; AntvError -> honest envelope (FR-006)."""
        try:
            return fn(cfg, *args)
        except AntvError as exc:
            log.warning("antv tool error: %s", exc.code)
            return _antv_envelope(exc)

    @mcp.tool()
    def antv_chart(chart_type: str, data: list, title: str = "",
                   axis_x_title: str = "", axis_y_title: str = "",
                   width: int = 0, height: int = 0) -> dict:
        """Generate a chart image from data. Returns {chart_type, image_url, usage}.

        MANDATORY data format — normalize BEFORE calling, or the chart renders empty:
        each item is an object with the canonical field names "category" and "value"
        (use "time" instead of "category" for time-series types line/area):
        [{"category": "Peter", "value": 180}, {"category": "Mary", "value": 165}]
        Rename any source columns to these exact fields ("Student"->"category",
        "Height (cm)"->"value"); values must be numbers, not strings.
        EXCEPT scatter: each point needs TWO numbers — {"x": <number>, "y": <number>}
        (e.g. height/weight, age/salary); numeric {"category","value"} pairs are
        mapped to x/y automatically, but "x"/"y" is the reliable shape.
        Any 2-field record shape is auto-normalized, but canonical fields are safest.

        axis_x_title / axis_y_title set human axis labels (e.g. "Students",
        "Height (cm)") — by default the axes are labeled with the raw field names.
        width/height (px, <= 4000, 0 = service default) override the render size.

        Chart-type selection guide: trends over time -> line/area; comparisons ->
        bar/column; proportions -> pie/treemap; distributions -> histogram/boxplot;
        relationships -> scatter/dual-axes; hierarchies -> treemap/organization;
        flows -> sankey/flow; funnels -> funnel; ranking -> sorted bar/column;
        multi-dimensional -> radar; part-of-whole emphasis -> liquid/venn.
        Supported types: line, area, bar, column, pie, radar, scatter, histogram,
        funnel, treemap, sankey, dual-axes, word-cloud, boxplot, venn, liquid,
        flow, mind-map, fishbone, organization, network."""
        return _antv(antv_charts_mod.generate_chart, chart_type, data, title,
                     axis_x_title, axis_y_title, width, height)

    @mcp.tool()
    def antv_infographic(description: str) -> dict:
        """Render an infographic from declarative AntV Infographic syntax.
        Returns {id, url, usage} — the url opens the rendered infographic in a browser.

        CRITICAL: `description` must be actual Infographic SYNTAX, NOT a prose design
        brief. The engine cannot render prose — write the template call and data
        directly. Complete working example:

        infographic list-row-simple-horizontal-arrow
        data
          lists
            - label Step 1
              desc Prepare accounts
            - label Step 2
              desc Team introduction
            - label Step 3
              desc Tool setup
            - label Step 4
              desc First sprint

        Structure: first line = "infographic <template-name>", then an indented
        "data" block whose list key depends on the template family. Items are
        "- label X / desc Y" lines ("value N" for charts). ~276 built-in
        presets across 8 families — VARY the choice to match the user's
        intent. Verified template names per family (data key in parentheses):
        - chart (values): chart-column-simple, chart-bar-plain-text,
          chart-pie-compact-card, chart-line-plain-text, chart-wordcloud
        - sequence (sequences): sequence-steps, sequence-timeline-done-list,
          sequence-snake-steps, sequence-roadmap-vertical-pill-badge,
          sequence-pyramid-simple (TRUE triangle pyramid — use when the user
          asks for a pyramid), sequence-funnel-simple,
          sequence-ascending-stairs-3d-simple (3D ascending steps)
        - sequence-interaction (UML message flows, template
          sequence-interaction-default-compact-card): participants = top-level
          items of "sequences" (lanes); each child message needs "id X" and
          "step N" (row order across all lanes); "relations" reference those
          MESSAGE ids: "- from m1 / to m2 / label call" — arrows only draw
          between messages that have ids
        - list (lists): list-row, list-grid, list-zigzag-up,
          list-sector-plain-text, list-pyramid-badge-card (stacked badge
          rows, NOT a triangle — prefer sequence-pyramid-simple for pyramids)
        - hierarchy (root with nested children): hierarchy-mindmap,
          hierarchy-structure, hierarchy-tree-tech-style-capsule-item
          (org charts)
        - relation (nodes plus relations from/to): relation-network-icon-badge,
          relation-circle-icon-badge, relation-dagre-flow-tb-capsule
          (flowcharts)
        - compare (compares): compare-binary-horizontal-simple-vs,
          compare-swot
        - quadrant (lists): quadrant-quarter-circular (2x2 grids)
        NEVER write "Title:", "Layout:", "Step 1 —", bullets, or any English
        description of the design — only the syntax. Choose the closest
        template to the user's intent and put their content into the data
        fields."""
        return _antv(antv_infographic_mod.create_infographic, description)

    # ---- Hermes Agent lane (spec 028): gated Windows file tasks ----

    from .hermes_audit import HermesAudit
    from .hermes_client import LAUNCH_INSTRUCTIONS as _HERMES_LAUNCH_INSTRUCTIONS
    from .hermes_client import run_task as _hermes_run_task
    from .hermes_gate import DEFAULT_ALLOWED_ROOT, gate_task, normalize_path, to_windows
    from .hermes_client import OFFICE_INSTRUCTIONS as _OFFICE_INSTRUCTIONS
    from .hermes_launch_gate import gate_launch

    async def _await_with_keepalive(fn, ctx=None, *, interval: float = 30.0,
                                    budget: float = 600.0):
        """Run blocking fn in a thread while emitting MCP progress frames every
        `interval` seconds. read-tool-response-failed (2026-11-06): the Hermes
        tools compute silently for minutes; the streamable-HTTP response stream
        idles past upstream read deadlines (~120 s observed) and gets cut with
        'peer closed connection … incomplete chunked read' while the work
        actually completes server-side. Progress frames keep bytes flowing on
        the response stream (resetting idle read timers) and give the caller
        real liveness. ctx may be None (tests / transports without injection):
        the helper then just awaits."""
        import asyncio
        import logging as _logging
        fut: asyncio.Future = asyncio.ensure_future(asyncio.to_thread(fn))
        elapsed = 0.0
        while True:
            try:
                return await asyncio.wait_for(asyncio.shield(fut), timeout=interval)
            except asyncio.TimeoutError:
                elapsed += interval
                if ctx is not None:
                    try:
                        await ctx.report_progress(
                            elapsed, budget,
                            message=f"still working ({int(elapsed)}s elapsed)")
                    except Exception as exc:  # noqa: S110 — liveness pings must never fail a real result
                        _logging.getLogger("agentic_rag_mcp").warning(
                            "keepalive progress ping failed: %r (ctx=%r)", exc, type(ctx).__name__)
                        pass
    from .office_gate import (
        OP_CANCEL, OP_COMPOSE_EMAIL, OP_CONTINUE, OP_SEND_CONFIRMATION,
        gate_office,
    )

    import re as _re
    _RE_LAUNCH_RESULT = _re.compile(r"LAUNCH:\s*(SUCCESS|FAILED)", _re.IGNORECASE)
    _RE_STEP = _re.compile(
        r"^STEP\s+\d+:\s+.+?\s+(OK|FAILED)\s*[—-]\s*(.*)$", _re.IGNORECASE | _re.MULTILINE)
    _RE_ACTIVE_FILE = _re.compile(r"^ACTIVE FILE:\s*(.+)$", _re.IGNORECASE | _re.MULTILINE)
    _RE_DRAFT_ID = _re.compile(r"^DRAFT ID:\s*(\S+)", _re.IGNORECASE | _re.MULTILINE)
    _RE_TASK = _re.compile(r"^TASK:\s*(COMPLETED|PARTIAL|FAILED)",
                           _re.IGNORECASE | _re.MULTILINE)
    _OFFICE_START_HINT = (" — if the Office automation service is down, start "
                          "it with: officemcp sse --port 8888 --host 127.0.0.1 "
                          "--folder C:\\OfficeMCP")

    @mcp.tool()
    async def hermes_file_task(task: str, allowed_root: str = "",
                               ctx: Context = None) -> dict:
        """Perform a LOCAL FILE TASK on the user's Windows computer via the Hermes
        agent (create folders, write files, read files, list folders) — strictly
        inside one allowed root (default C:\\temp via /mnt/c/temp; pass
        allowed_root to use another root, Windows or host style).
        EVERY task is security-gated BEFORE execution: paths naming anything
        outside the active root (other drives, C:\\Windows, /etc, ".."
        traversal) are BLOCKED with a reason and never executed; delete /
        rename / move / bulk-clear requests are BLOCKED everywhere (v1 scope:
        create/write/read/list only); a task naming NO location is BLOCKED
        with an ask-back — relay that question to the user verbatim instead
        of guessing. Windows-style and host-style paths are both accepted.
        Returns {status: ok|blocked|error, result?, reason?, windows_path?} —
        relay the verdict honestly: on "ok" report the result and windows_path;
        on "blocked" tell the user the reason; on "error" say the local agent
        failed and include the recovery hint. Never claim an operation ran
        when the status is not ok."""
        home = str(Path.home())
        root_arg = allowed_root.strip() or None
        active_root = (normalize_path(allowed_root.strip() or DEFAULT_ALLOWED_ROOT, home)
                       or DEFAULT_ALLOWED_ROOT)
        verdict = gate_task(task, allowed_root=root_arg, home=home)
        audit = HermesAudit(cfg.hermes_audit_path)

        if verdict.decision == "blocked":
            audit.write_attempt(decision="blocked", operation=verdict.operation,
                                normalized_path=verdict.normalized_path,
                                allowed_root=active_root, reason=verdict.reason)
            return {"status": "blocked", "decision": "blocked",
                    "reason": verdict.reason}

        outcome = await _await_with_keepalive(
            lambda: _hermes_run_task(cfg, task), ctx)
        if not outcome.get("ok"):
            error = outcome.get("error", "error:unknown Hermes failure")
            audit.write_attempt(decision="error", operation=verdict.operation,
                                normalized_path=verdict.normalized_path,
                                allowed_root=active_root, reason=error)
            return {"status": "error", "reason": error}

        output = outcome["output"]
        audit.write_attempt(decision="executed", operation=verdict.operation,
                            normalized_path=verdict.normalized_path,
                            allowed_root=active_root,
                            outcome=output[:200])
        result: dict = {"status": "ok", "decision": "executed", "result": output}
        if verdict.normalized_path:
            result["windows_path"] = to_windows(verdict.normalized_path)
        return result

    @mcp.tool()
    async def hermes_launch_app(task: str, ctx: Context = None) -> dict:
        """Launch a DESKTOP APPLICATION on the user's Windows computer via the Hermes
        agent (e.g. open Outlook/Excel/Notepad, or run C:\\tools\\mytool.exe). ANY
        executable by name or full .exe path — there is no allowlist. EVERY task is
        security-gated BEFORE execution: launch arguments, command lines, and
        shell/PowerShell phrasing are BLOCKED with a reason and never executed; script
        (.bat/.cmd/.ps1) and shortcut (.lnk) targets are BLOCKED (executables only); a
        task naming NO application is BLOCKED with an ask-back — relay that question to
        the user verbatim; two applications in one prompt is an ask-back too (one launch
        per request). Returns {status: ok|blocked|error, result?, reason?, target?} —
        relay the verdict honestly: on "ok" report what the agent observed (started
        fresh / already running); on "blocked" give the user the reason verbatim; on
        "error" say the local agent failed and include the recovery hint. Never claim
        a launch happened when the status is not ok."""
        home = str(Path.home())
        verdict = gate_launch(task, home=home)
        audit = HermesAudit(cfg.hermes_audit_path)

        if verdict.decision == "blocked":
            audit.write_attempt(decision="blocked", operation=verdict.operation,
                                normalized_path=verdict.target, allowed_root="",
                                reason=verdict.reason)
            return {"status": "blocked", "decision": "blocked",
                    "reason": verdict.reason}

        outcome = await _await_with_keepalive(
            lambda: _hermes_run_task(cfg, verdict.sanitized_task or task,
                                      instructions=_HERMES_LAUNCH_INSTRUCTIONS), ctx)
        if not outcome.get("ok"):
            error = outcome.get("error", "error:unknown Hermes failure")
            audit.write_attempt(decision="error", operation=verdict.operation,
                                normalized_path=verdict.target, allowed_root="",
                                reason=error)
            return {"status": "error", "reason": error}

        output = outcome["output"]
        # Honest envelope (FR-007): ok only on the agent's explicit SUCCESS
        # attestation — a report without it (or a FAILED marker) is an error,
        # never a fabricated launch.
        m = _RE_LAUNCH_RESULT.search(output)
        if not m or m.group(1).upper() == "FAILED":
            reason = (f"error:the local agent could not launch the program — "
                      f"{output.strip()[-300:]}")
            audit.write_attempt(decision="error", operation=verdict.operation,
                                normalized_path=verdict.target, allowed_root="",
                                reason=reason)
            return {"status": "error", "reason": reason}
        audit.write_attempt(decision="executed", operation=verdict.operation,
                            normalized_path=verdict.target, allowed_root="",
                            outcome=output[:200])
        return {"status": "ok", "decision": "executed",
                "result": output, "target": verdict.target}

    @mcp.tool()
    async def hermes_office_task(task: str, conversation_id: str,
                                 ctx: Context = None) -> dict:
        """Execute a Microsoft Office task on the user's Windows computer via the
        Hermes agent and the Office automation service — Word, Excel, PowerPoint,
        Outlook (e.g. "open Excel and put 12345 in cell A1", "create a Word doc
        with ...", "write an email to a@b.com saying ..."). EVERY task is
        security-gated BEFORE execution: save or read at any location the user
        names — any drive, any folder; unnamed saves use the default work folder
        (C:\\OfficeMCP); macro/script/DDE or executable cell
        content is BLOCKED; email is COMPOSED first and shown verbatim — it is
        sent ONLY after the user confirms in chat (the draft shown is the draft
        sent, unchanged); recipients come only from the user, never from
        contacts. Follow-ups continue on the conversation's active document
        (named in every answer). Multi-step tasks report each step honestly;
        failures stop at the failing step with the partial state. Returns
        {status, decision?, result?, reason?, active_file?, draft_pending?} —
        relay honestly: on "ok" report the steps; on "blocked" give the reason
        verbatim (ask-backs go to the user verbatim); on "error" include the
        recovery hint. Never claim a step that did not run."""
        root = cfg.hermes_office_root
        verdict = gate_office(task, office_root=root)
        audit = HermesAudit(cfg.hermes_audit_path)
        state = get_office_state()

        def _audit(decision: str, reason: str | None = None,
                   outcome: str | None = None) -> None:
            audit.write_attempt(decision=decision, operation="office-task",
                                normalized_path=state.active_document(conversation_id),
                                allowed_root=root, reason=reason, outcome=outcome)

        def _error_envelope(err: str) -> dict:
            reason = err if "officemcp sse" in err.lower() else err + _OFFICE_START_HINT
            if "did not finish within" in err:
                # budget exhaustion is resumable — record it for 'continue' (FR-005)
                state.set_interrupted(conversation_id,
                                      {"original_task": task,
                                       "partial_report": err})
            _audit("error", reason=reason)
            return {"status": "error", "reason": reason}

        async def _run_agent(directive: str) -> dict:
            out = await _await_with_keepalive(
                lambda: _hermes_run_task(cfg, directive,
                                         instructions=_OFFICE_INSTRUCTIONS), ctx)
            if not out.get("ok"):
                return _error_envelope(out.get("error", "error:unknown Hermes failure"))
            output = out["output"]
            # completed-message-wait-long-time (2026-11-06): remember the strip
            # conversation-wide — follow-on tasks skip the detection tax; and
            # a healed gateway channel clears the flag (self-correcting)
            if "stripped" in output.lower() or "switched to the direct" in output.lower():
                state.mark_gateway_stripped(conversation_id)
            elif _RE_STEP.search(output) and "direct channel" not in output.lower():
                pass  # steps ran on the gateway channel → it delivered → clear below
            if "direct channel" not in output.lower() and _RE_STEP.search(output):
                state.clear_gateway_stripped(conversation_id)
            # parse ALL markers first, THEN audit the steps — so every audit
            # entry carries the actual target from ACTIVE FILE (spec 031 FR-006)
            af = _RE_ACTIVE_FILE.search(output)
            if af:
                state.set_active_document(conversation_id, af.group(1).strip())
            for m in _RE_STEP.finditer(output):
                line = m.group(0).strip()
                if m.group(1).upper() == "OK":
                    # 1000 (was 200): STEP BATCHING made single blocks carry all
                    # sub-operation details — 200 cut them mid-sentence
                    # (do-not-write-data-in-worksheet, 2026-11-06)
                    _audit("executed", outcome=line[:1000])
                else:
                    _audit("error", reason=line[:1000])
            di = _RE_DRAFT_ID.search(output)
            tm_early = _RE_TASK.search(output)
            if di:
                state.set_pending_draft(conversation_id,
                                        {"entry_id": di.group(1).strip(),
                                         "composed_for": task[:300]})
            elif (verdict.kind == OP_COMPOSE_EMAIL and tm_early
                  and tm_early.group(1).upper() == "COMPLETED"):
                # robust fallback (bug fix 2026-11-03): a completed compose
                # whose report carried no DRAFT ID line still registers the
                # pending draft — the send directive locates it by content
                state.set_pending_draft(conversation_id,
                                        {"entry_id": None,
                                         "composed_for": task[:300]})
            envelope = {"active_file": state.active_document(conversation_id),
                        "draft_pending": bool(state.pending_draft(conversation_id))}
            tm = _RE_TASK.search(output)
            if not tm:
                reason = ("error:the local agent did not end with a TASK: "
                          "COMPLETED/PARTIAL/FAILED marker — never claiming "
                          f"success. Report was: {output.strip()[-300:]}"
                          + _OFFICE_START_HINT)
                _audit("error", reason=reason)
                return {"status": "error", "reason": reason, **envelope}
            if tm.group(1).upper() == "COMPLETED":
                return {"status": "ok", "decision": "executed",
                        "result": output, **envelope}
            failed = [m.group(0).strip() for m in _RE_STEP.finditer(output)
                      if m.group(1).upper() == "FAILED"]
            reason = ("error:the Office task did not complete — "
                      + tm.group(1).upper()
                      + (f"; failing steps: {'; '.join(failed)}" if failed else "")
                      + f"; partial report: {output.strip()[-300:]}")
            if not _RE_STEP.search(output):
                _audit("error", reason=reason[:400])   # nothing else recorded it
            if tm.group(1).upper() == "PARTIAL":
                # a partial task is resumable — record it for 'continue' (FR-005)
                state.set_interrupted(conversation_id,
                                      {"original_task": task,
                                       "partial_report": output.strip()[-800:]})
            return {"status": "error", "reason": reason, **envelope}

        if verdict.decision == "blocked":
            _audit("blocked", reason=verdict.reason)
            return {"status": "blocked", "decision": "blocked",
                    "reason": verdict.reason}

        if verdict.kind == OP_SEND_CONFIRMATION:
            pending = state.pending_draft(conversation_id)
            if not pending:
                reason = ("Blocked: no email is waiting to be sent — which "
                          "email should I compose? Compose first; sending "
                          "always needs your confirmation (spec 030 FR-009)")
                _audit("blocked", reason=reason)
                return {"status": "blocked", "decision": "blocked", "reason": reason}
            entry = pending.get("entry_id")
            context = str(pending.get("composed_for", ""))[:200]
            if entry:
                locate = (f"Send the Outlook draft with EntryID {entry} — do "
                          f"not modify it. It is the one this conversation "
                          f"composed: {context}")
            else:
                locate = (f"Locate the unsent draft in Outlook's Drafts folder "
                          f"that this conversation composed — {context} — and "
                          f"send it exactly as composed; do not modify it. If "
                          f"more than one matching draft exists, send the most "
                          f"recent and say which one was sent.")
            directive = (f"SEND PENDING DRAFT — {locate} Report the send as "
                         f"one step and never modify the draft.")
            result = await _run_agent(directive)
            if result.get("status") == "ok":
                state.drop_pending_draft(conversation_id)
                result["draft_pending"] = False
            return result

        if verdict.kind == OP_CANCEL:
            dropped = state.drop_pending_draft(conversation_id)
            outcome = ("cancelled — the pending email was not sent" if dropped
                       else "nothing was pending")
            _audit("executed", outcome=outcome)
            return {"status": "ok", "decision": "executed", "result": outcome,
                    "draft_pending": False}

        if verdict.kind == OP_CONTINUE:
            it = state.interrupted(conversation_id)
            if not it:
                reason = ("Blocked: no interrupted Office task to resume — "
                          "state the Office task you want (a task only becomes "
                          "resumable when it stops part-way)")
                _audit("blocked", reason=reason)
                return {"status": "blocked", "decision": "blocked", "reason": reason}
            directive = (f"Resume an interrupted Office task. The original "
                         f"request was: {it['original_task']}. The previous "
                         f"attempt stopped with: {it['partial_report']}. "
                         f"Complete the remaining steps now and follow the "
                         f"step-report protocol.")
            result = await _run_agent(directive)
            if result.get("status") == "ok":
                state.clear_interrupted(conversation_id)
            return result

        active = state.active_document(conversation_id)
        # directive_ctx (was `ctx` — shadowed the Context parameter and the
        # keepalive ping saw this string instead: read-tool-response-failed, 2026-11-06)
        directive_ctx = (
            f"The conversation's active document is {active} — continue on "
            f"it unless the task names another file. ") if active else ""
        stripped_at = state.gateway_stripped_at(conversation_id)
        if stripped_at:
            directive_ctx += (
                "The gateway's RunPython channel is KNOWN STRIPPED in this "
                f"conversation (observed {stripped_at}) — skip all gateway "
                "canaries and channel detection and run this task's steps "
                "directly on the direct OfficeMCP channel "
                "(http://127.0.0.1:8888/sse) from the start; if the direct "
                "channel itself fails, re-probe the gateway channel then. ")
        if verdict.kind == OP_COMPOSE_EMAIL:
            extra = ("This is a COMPOSE task: create an email draft with the "
                     "dictated recipient(s)/subject/body verbatim in Outlook's "
                     "Drafts folder — NEVER send it; report the draft with its "
                     "DRAFT ID and show the content. ")
        else:
            extra = ("Save at the location the user names (any drive, any "
                     "folder; create missing parent folders as needed) or, "
                     "if none is named, in the default work folder; write "
                     "literal values only. ")
        directive = (f"{directive_ctx}Office task ({verdict.kind}, {verdict.app or 'office'}): "
                     f"{task}. {extra}Unnamed saves use the default work "
                     f"folder {root}. "
                     f"Follow the step-report protocol.")
        return await _run_agent(directive)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(prog="agentic-rag-mcp")
    parser.add_argument("--init", action="store_true", help="write default config and exit")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8811)
    args, _unknown = parser.parse_known_args()
    if args.init:
        path = init_config()
        print(f"config written: {path}")  # exits before logging exists (bootstrap)
        return
    cfg = load_config()
    mcp = build_server(cfg)  # configure_logging runs inside build_server (spec 008)
    if args.transport == "streamable-http":
        logging.getLogger("agentic_rag_mcp").info(
            "agentic-rag-mcp MCP endpoint: http://%s:%s/mcp", cfg.mcp_host, cfg.mcp_port)
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
