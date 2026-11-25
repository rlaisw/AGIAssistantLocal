"""Outline-preserving extraction (FR-005/006/007; research.md D6 rows 5, 7, 8, 9)
against deterministic fixtures — document order, text+image grouping, noise
rules, and the per-page bound."""

from pathlib import Path

from agentic_rag_mcp.search.web.research import extract_sections

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "research"
PAGE_URL = "https://docs.example/guide"


def _html(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_ordered_page_sections_preserve_document_order():
    """D6 row 9 / SC-003: h2 -> p -> img -> p stays in order, grouped."""
    sections, truncated = extract_sections(_html("ordered.html"), PAGE_URL, 6000)
    assert truncated is False
    first = sections[0]
    assert first["heading"] == "Trace a message"
    kinds = [b["type"] for b in first["blocks"]]
    assert kinds == ["p", "img", "p"]                       # document order (FR-005)
    assert first["blocks"][1]["src"] == "https://docs.example/img/trace-step1.png"  # urljoin (FR-006)
    assert sections[1]["heading"] == "Understand the results"
    assert sections[1]["blocks"][-1]["src"] == "https://cdn.example.com/img/trace-results.png"


def test_js_only_page_yields_no_sections_without_crashing():
    """D6 row 5: no extractable content -> empty sections (fallback path)."""
    sections, truncated = extract_sections(_html("js_only.html"), PAGE_URL, 6000)
    assert sections == [] and truncated is False


def test_oversized_page_truncated_at_bound_and_flagged():
    """D6 row 7 / FR-007: content cut at per_page_chars, truncated=True
    (reduced bound — the fixture must exceed it, mirroring the default 6000)."""
    sections, truncated = extract_sections(_html("oversized.html"), PAGE_URL, 500)
    assert truncated is True
    total = sum(len(b.get("text", "")) for s in sections for b in s["blocks"])
    assert total <= 500
    # and the same fixture at the default bound is NOT truncated
    sections2, truncated2 = extract_sections(_html("oversized.html"), PAGE_URL, 6000)
    assert truncated2 is False


def test_dirty_markup_noise_rules():
    """D6 row 8 / FR-006: data: URIs skipped, relative src absolutized,
    short paragraphs dropped, figure data-src honored, empty sections omitted."""
    sections, _ = extract_sections(_html("dirty.html"), PAGE_URL, 6000)
    assert len(sections) == 1                       # "Empty Section" dropped
    sec = sections[0]
    assert sec["heading"] == "Real Section"
    texts = [b["type"] for b in sec["blocks"]]
    assert texts == ["p", "img", "img"]              # 'short'/'tiny' <p dropped
    srcs = [b["src"] for b in sec["blocks"] if b["type"] == "img"]
    assert srcs == ["https://docs.example/img/relative-photo.jpg",
                    "https://docs.example/img/lazy-loaded.jpg"]  # data: skipped, data-src honored


# ---- spec 050: alt capture for the image-rich answer payload ----

def test_img_block_captures_trimmed_alt():
    sections, _ = extract_sections(_html("images-alt.html"), PAGE_URL, 6000)
    imgs = [b for s in sections for b in s["blocks"] if b["type"] == "img"]
    assert imgs[0]["alt"] == "Open the Trace dialog"          # trimmed
    assert imgs[1]["alt"] == "Results panel"                  # figure data-src honored
    assert imgs[1]["src"] == "https://docs.example/img/results-panel.png"


def test_missing_alt_is_empty_string_not_none():
    sections, _ = extract_sections(_html("images-alt.html"), PAGE_URL, 6000)
    imgs = [b for s in sections for b in s["blocks"] if b["type"] == "img"]
    no_alt = [b for b in imgs if b["src"].endswith("no-alt.png")]
    assert no_alt and no_alt[0]["alt"] == ""


def test_figure_supplies_data_src_and_alt_once():
    sections, _ = extract_sections(_html("images-alt.html"), PAGE_URL, 6000)
    imgs = [b for s in sections for b in s["blocks"] if b["type"] == "img"]
    assert len([b for b in imgs if b["src"].endswith("results-panel.png")]) == 1


def test_data_uri_and_srcless_images_skipped():
    sections, _ = extract_sections(_html("images-alt.html"), PAGE_URL, 6000)
    srcs = [b["src"] for s in sections for b in s["blocks"] if b["type"] == "img"]
    assert all(not s.startswith("data:") for s in srcs)
    sections, _ = extract_sections(_html("images-noise.html"), PAGE_URL, 6000)
    srcs = [b["src"] for s in sections for b in s["blocks"] if b["type"] == "img"]
    # extraction keeps page structure; noise filtering is the projection's job
    assert all(not x.startswith(("data:", "javascript:")) for x in srcs)
    assert srcs == ["https://docs.example/pixel.gif", "https://docs.example/1x1.png",
                    "https://docs.example/tracker.png", "https://docs.example/img/real.png"]
