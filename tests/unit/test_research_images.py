"""Spec 050 unit pins: flatten_images projection (data-model §2, contract §1).

Red before implementation: this module imports a function that does not exist
yet, so the suite must fail at collection until T008 lands.
"""

from pathlib import Path

from agentic_rag_mcp.search.web.research import extract_sections, flatten_images

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "research"
PAGE_URL = "https://docs.example/guide"


def _sections(name, bound=6000):
    return extract_sections((FIXTURES / name).read_text(encoding="utf-8"), PAGE_URL, bound)[0]


def test_document_order_and_heading_attribution():
    refs = flatten_images(_sections("images-alt.html"))
    urls = [r["url"] for r in refs]
    assert urls == [
        "https://docs.example/img/trace-step1.png",
        "https://docs.example/img/results-panel.png",
        "https://docs.example/img/no-alt.png",
    ]
    assert [r["heading"] for r in refs] == ["Trace a message"] * 3


def test_duplicates_appear_once_first_wins():
    refs = flatten_images(_sections("images-alt.html"))
    assert len([r for r in refs if r["url"].endswith("trace-step1.png")]) == 1
    assert refs[0]["url"].endswith("trace-step1.png")


def test_noise_urls_skipped_case_insensitive():
    refs = flatten_images(_sections("images-noise.html"))
    assert [r["url"] for r in refs] == ["https://docs.example/img/real.png"]


def test_alt_passthrough_including_quotes_and_newlines():
    sections = [{"heading": "H", "blocks": [
        {"type": "img", "src": "https://x.example/a.png", "alt": 'A "quoted"\nline'},
    ]}]
    refs = flatten_images(sections)
    assert refs == [{"url": "https://x.example/a.png",
                     "alt": 'A "quoted"\nline', "heading": "H"}]


def test_cap_at_40_in_document_order():
    refs = flatten_images(_sections("images-many.html"))
    assert len(refs) == 40
    assert [r["url"].rsplit("/", 1)[-1] for r in refs[:2]] == ["s1-00.png", "s1-01.png"]
    assert refs[-1]["url"].endswith("s2-19.png")            # 40th overall


def test_empty_and_malformed_sections_yield_empty_list():
    assert flatten_images([]) == []
    assert flatten_images(None) == []
    assert flatten_images({}) == []
    assert flatten_images([{"heading": "H"}]) == []
    assert flatten_images([{"heading": "H", "blocks": None}]) == []


def test_block_without_src_is_skipped_defensively():
    sections = [{"heading": "H", "blocks": [{"type": "img"}, None, {"type": "p", "text": "x"}]}]
    assert flatten_images(sections) == []
