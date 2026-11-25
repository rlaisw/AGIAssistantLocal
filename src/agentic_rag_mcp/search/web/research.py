"""Grouped web research (spec 003): SSRF-guarded page fetching, outline-preserving
extraction, bounded-parallel orchestration, and rendering (FR-005..014).

Search stays in search/web/base.py (search_all); this module owns everything
that happens to a page AFTER the chain found it.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx

_UA = {"User-Agent": "Mozilla/5.0 (compatible; agentic-rag-mcp/0.1)"}
_MAX_REDIRECTS = 3


class ScrapeBlocked(Exception):
    """A fetch destination was refused by the SSRF guard (FR-013)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _assert_public_host(host: str | None) -> None:
    """Refuse private/loopback/link-local/unspecified destinations (FR-013).

    IP literals and localhost resolve without network; hostnames resolve via
    getaddrinfo and EVERY resolved address must be public.
    """
    if not host:
        raise ScrapeBlocked("ssrf:blocked-private-address: <no-host>")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise ScrapeBlocked(f"ssrf:resolve-failed: {host} ({exc})") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified:
            raise ScrapeBlocked(f"ssrf:blocked-private-address: {host}")


def guarded_get(url: str, timeout: float) -> httpx.Response:
    """GET with per-hop SSRF checks and a redirect cap (research.md D4)."""
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        parsed = urlparse(current)
        _assert_public_host(parsed.hostname)
        resp = httpx.get(current, timeout=timeout, follow_redirects=False, headers=_UA)
        if resp.is_redirect and "location" in resp.headers:
            current = urljoin(current, resp.headers["location"])
            continue
        return resp
    raise ScrapeBlocked("ssrf:too-many-redirects")


# ---- Outline-preserving extraction (FR-005/006/007; research.md D5) ----

_MIN_PARAGRAPH = 30  # substantive text floor

# shared with _fetch_url (server.py): obvious non-content images (spec 050)
IMG_SKIP = ("pixel", "tracker", "beacon", "spacer", "1x1", "blank.gif")
_IMG_LIMIT = 40  # per-page image refs handed to the model (spec 050)


def extract_sections(html: str, page_url: str, per_page_chars: int) -> tuple[list[dict], bool]:
    """Sections preserve document order: heading, then text blocks and the
    images belonging to that text interleaved (never all-text-then-images).

    Noise rules (FR-006): paragraphs below the floor dropped, `data:` URIs
    skipped, relative image srcs absolutized, empty sections omitted.
    Returns (sections, truncated) — truncated=True when cut at per_page_chars.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    main = soup.find("article") or soup.find("main") or soup.body
    if main is None:
        return [], False
    h1 = soup.find("h1")
    current: dict = {"heading": h1.get_text(strip=True) if h1 else "", "blocks": []}
    sections: list[dict] = []
    truncated = False
    budget = per_page_chars

    for el in main.find_all(["h2", "h3", "p", "img", "figure"]):
        if el.name in ("h2", "h3"):
            if current["blocks"]:
                sections.append(current)
            current = {"heading": el.get_text(strip=True), "blocks": []}
        elif el.name == "p":
            txt = el.get_text(strip=True)
            if len(txt) <= _MIN_PARAGRAPH:
                continue
            if len(txt) > budget:
                txt, truncated = txt[:budget], True
            current["blocks"].append({"type": "p", "text": txt})
            budget -= len(txt)
            if truncated:
                break  # per-page bound reached (FR-007)
        else:  # img / figure
            img = el if el.name == "img" else el.find("img")
            if img is None or el.name == "img" and el.find_parent("figure") is not None:
                continue  # handled via its figure — don't double-count
            src = (img.get("src") or img.get("data-src") or "").strip()
            if not src or src.startswith("data:"):
                continue
            abs_src = urljoin(page_url, src)
            if not abs_src.startswith(("http://", "https://")):
                continue
            current["blocks"].append({
                "type": "img", "src": abs_src,
                "alt": (img.get("alt") or "").strip(),  # source description only
            })
    if current["blocks"]:
        sections.append(current)
    return sections, truncated


def flatten_images(sections: list, limit: int = _IMG_LIMIT) -> list[dict]:
    """Ordered, deduped image refs for the model (spec 050, contract 050).

    Projection of the section blocks — never a second extraction path. Every
    page result is bounded (limit) and noise-filtered; malformed input yields []
    instead of raising, so one bad page cannot fail a whole research call.
    """
    images: list[dict] = []
    seen: set[str] = set()
    if not isinstance(sections, list):
        return images
    for sec in sections:
        if not isinstance(sec, dict) or not isinstance(sec.get("blocks"), list):
            continue
        heading = sec.get("heading") or ""
        for block in sec["blocks"]:
            if not isinstance(block, dict) or block.get("type") != "img":
                continue
            url = block.get("src") or ""
            if not url or url in seen:
                continue
            low = url.lower()
            if any(bad in low for bad in IMG_SKIP):
                continue
            seen.add(url)
            images.append({"url": url, "alt": block.get("alt") or "", "heading": heading})
            if len(images) >= limit:
                return images
    return images


def sections_to_text(sections: list[dict]) -> str:
    """LLM-facing text of grouped sections: headings, paragraphs, image refs."""
    lines: list[str] = []
    for sec in sections:
        if sec["heading"]:
            lines.append(sec["heading"])
        for b in sec["blocks"]:
            lines.append(b["text"] if b["type"] == "p" else f"[image: {b['src']}]")
    return "\n".join(lines)


# ---- Rendering (FR-010; research.md D7 — stdlib templates, no engine) ----

_RENDER_STYLE = (
    "body{max-width:800px;margin:40px auto;font-family:serif;line-height:1.8;padding:20px}"
    ".section{margin-bottom:50px;padding:24px;background:#fafafa;border-radius:16px}"
    "img{max-width:100%;border-radius:12px;margin:16px 0}"
    ".fallback{background:#fff3cd;padding:16px;border-radius:12px}"
)


def render_page(sections: list[dict], original_url: str, title: str,
                *, fallback_snippet: str | None = None) -> str:
    """Standalone HTML artifact mirroring the grouped structure, openable in
    any browser without a server (FR-010). Fallback hits show the snippet with
    a visible marker — the artifact always shows honest content."""
    html = (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<title>{title}</title><style>{_RENDER_STYLE}</style></head><body>'
            f'<h1>{title}</h1><p><a href="{original_url}">{original_url}</a></p>')
    if sections:
        for sec in sections:
            html += "<div class='section'>"
            if sec["heading"]:
                html += f"<h2>{sec['heading']}</h2>"
            for b in sec["blocks"]:
                if b["type"] == "p":
                    html += f"<p>{b['text']}</p>"
                else:
                    html += f"<img src='{b['src']}' loading='lazy' alt=''>"
            html += "</div>"
    elif fallback_snippet:
        html += (f"<div class='fallback'><strong>Fallback content "
                 f"(page could not be scraped):</strong><p>{fallback_snippet}</p></div>")
    else:
        html += "<div class='fallback'><p>No content could be extracted for this page.</p></div>"
    return html + "</body></html>"


# ---- Per-page outcome (FR-008/009; data-model ScrapeResult states) ----

def research_page(url: str, *, fetch_timeout_s: float, per_page_chars: int) -> dict:
    """Fetch (guarded) + extract one page. Any failure yields an honest
    fallback/blocked ScrapeResult — never an exception to the caller."""
    base = {"url": url, "sections": [], "truncated": False}
    try:
        resp = guarded_get(url, fetch_timeout_s)
    except ScrapeBlocked as exc:
        return {**base, "status": "blocked", "status_reason": exc.reason}
    except httpx.TimeoutException:
        return {**base, "status": "fallback", "status_reason": "timeout"}
    except Exception as exc:  # noqa: BLE001 — fetch isolation
        return {**base, "status": "failed", "status_reason": f"fetch-error: {exc}"}
    if resp.status_code >= 400:
        return {**base, "status": "fallback", "status_reason": f"http:{resp.status_code}"}
    sections, truncated = extract_sections(resp.text, str(resp.url), per_page_chars)
    if not sections:
        return {**base, "status": "fallback", "status_reason": "no-extractable-content"}
    return {**base, "status": "ok", "status_reason": None,
            "sections": sections, "truncated": truncated}


# ---- Bounded-parallel orchestration (FR-014; research.md D3) ----

def research_pages(hits: list[dict], *, t0: float, fetch_timeout_s: float,
                   per_page_chars: int, overall_timeout_s: float,
                   max_concurrent: int) -> dict[str, dict]:
    """Scrape every hit in parallel, bounded by the overall deadline.

    Returns {url: ScrapeResult}. At the deadline, in-flight pages end as
    fallback with reason `cut-off-at-overall-bound` — the call never hangs.
    ponytail: threads abandoned at cut-off finish in the background; switch to
    a process pool if that ever leaks meaningfully.
    """
    results: dict[str, dict] = {}
    if not hits:
        return results
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time as _time

    executor = ThreadPoolExecutor(max_workers=max_concurrent)
    try:
        futures = {
            executor.submit(research_page, h["url"], fetch_timeout_s=fetch_timeout_s,
                             per_page_chars=per_page_chars): h["url"]
            for h in hits
        }
        remaining = overall_timeout_s - (_time.perf_counter() - t0)
        try:
            for fut in as_completed(futures, timeout=max(0.0, remaining)):
                results[futures[fut]] = fut.result()
        except TimeoutError:
            for fut, url in futures.items():
                if url in results:
                    continue
                fut.cancel()
                if fut.done() and not fut.cancelled():  # finished while we timed out
                    results[url] = fut.result()
                else:
                    results[url] = {"url": url, "sections": [], "truncated": False,
                                    "status": "fallback",
                                    "status_reason": "cut-off-at-overall-bound"}
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return results
