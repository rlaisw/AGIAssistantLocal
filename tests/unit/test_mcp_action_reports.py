"""Unit: private, expiring MCP-Action health report storage (spec 048, T006).

The report store mirrors the screenshot store: one 256-bit capability token per
artifact, absolute 900-second expiry, private files, and no metadata database.
HTML is untrusted host input, so document-size, document-shape, and active /
external content boundaries are tested here.
"""

from __future__ import annotations

import base64
import os
import re
import stat
from unittest.mock import Mock
from urllib.parse import urlsplit

import agentic_rag_mcp.mcp_action.reports as reports_module
import pytest
from agentic_rag_mcp.mcp_action.reports import (
    MAX_REPORT_BYTES,
    TTL_SECONDS,
    ReportStore,
    StoredReport,
)

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
HTML_TAIL = b"</body></html>"


def _html(body: str = "<p>ok</p>") -> bytes:
    return (
        '<!doctype html><html lang="en"><head><title>System health</title>'
        "</head><body>" + body + "</body></html>"
    ).encode("utf-8")


def _html_of_size(size: int) -> bytes:
    prefix = _html()[: -len(HTML_TAIL)]
    padding = size - len(prefix) - len(HTML_TAIL)
    assert padding >= 0
    return prefix + b"x" * padding + HTML_TAIL


class FakeClock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_public_constants_match_the_contract():
    assert TTL_SECONDS == 900
    assert MAX_REPORT_BYTES == 5 * 1024 * 1024


def test_save_uses_256_bit_urlsafe_capability_tokens(tmp_path, monkeypatch):
    token_factory = Mock(return_value="A" * 43)
    monkeypatch.setattr(reports_module.secrets, "token_urlsafe", token_factory)
    store = ReportStore(tmp_path / "reports", clock=lambda: 12.0)

    artifact = store.save(_html())

    token_factory.assert_called_once_with(32)
    assert artifact.token == "A" * 43
    assert TOKEN_PATTERN.fullmatch(artifact.token)


@pytest.mark.parametrize(
    "document",
    [
        _html(),
        b"\xef\xbb\xbf" + _html(),
        _html("<p>&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;quoted&quot;</p>"),
        _html('<style>body{color:#333}</style><p style="color:#333">styled</p>'),
        _html('<svg xmlns="http://www.w3.org/2000/svg"><circle r="1"/></svg>'),
        _html('<img src="data:image/png;base64,iVBORw0KGgo=" alt="chart">'),
    ],
    ids=["plain", "bom", "escaped-active-text", "inline-style", "inline-svg", "data-image"],
)
def test_complete_utf8_documents_are_accepted_with_optional_bom(tmp_path, document):
    store = ReportStore(tmp_path / "reports", clock=FakeClock())

    artifact = store.save(document)

    resolved = store.resolve(artifact.token)
    assert isinstance(resolved, StoredReport)
    assert resolved.data == document
    assert artifact.path.read_bytes() == document


@pytest.mark.parametrize(
    "document",
    [
        b"",
        b"not html",
        b"<html><body>truncated",
        b"<html><body>missing closing html tag</body>",
        b"<html><body>nul\x00</body></html>",
        b"<html><body>bad utf-8 \xff</body></html>",
        "not bytes",
    ],
    ids=["empty", "text", "truncated-body", "missing-html", "nul", "invalid-utf8", "str"],
)
def test_invalid_or_truncated_documents_are_rejected_without_leaving_files(
    tmp_path, document
):
    root = tmp_path / "reports"
    store = ReportStore(root, clock=FakeClock())

    with pytest.raises(ValueError):
        store.save(document)

    assert list(root.iterdir()) == []


@pytest.mark.parametrize(
    "body",
    [
        "<script>alert(1)</script>",
        "<SCRIPT>alert(1)</SCRIPT>",
        '<iframe src="https://example.com"></iframe>',
        '<object data="x"></object>',
        '<embed src="x">',
        '<form action="/x"></form>',
        '<base href="https://example.com/">',
        '<link rel="stylesheet" href="https://example.com/x.css">',
        '<p onclick="alert(1)">x</p>',
        '<a href="javascript:alert(1)">x</a>',
        '<a href="data:text/html,<script>alert(1)</script>">x</a>',
        '<meta http-equiv="refresh" content="0;url=https://example.com">',
        "<svg><script>alert(1)</script></svg>",
    ],
    ids=[
        "script",
        "script-uppercase",
        "iframe",
        "object",
        "embed",
        "form",
        "base",
        "link",
        "event-handler-attribute",
        "javascript-url",
        "data-html-url",
        "meta-refresh",
        "svg-script",
    ],
)
def test_active_content_is_rejected(tmp_path, body):
    root = tmp_path / "reports"
    store = ReportStore(root, clock=FakeClock())

    with pytest.raises(ValueError):
        store.save(_html(body))

    assert list(root.iterdir()) == []


@pytest.mark.parametrize(
    "body",
    [
        '<img src="https://example.com/chart.png">',
        '<link rel="preload" href="https://example.com/x">',
        '<style>@import url("https://example.com/x.css");</style>',
        "<style>body{background:url(https://example.com/x.png)}</style>",
    ],
    ids=["external-image", "external-link", "css-import", "css-url"],
)
def test_external_resources_are_rejected(tmp_path, body):
    root = tmp_path / "reports"
    store = ReportStore(root, clock=FakeClock())

    with pytest.raises(ValueError):
        store.save(_html(body))

    assert list(root.iterdir()) == []


def test_one_report_may_be_exactly_5_mib_but_not_larger(tmp_path):
    root = tmp_path / "reports"
    store = ReportStore(root, clock=FakeClock())
    at_cap = _html_of_size(MAX_REPORT_BYTES)
    assert len(at_cap) == MAX_REPORT_BYTES

    artifact = store.save(at_cap)

    assert artifact.path.read_bytes() == at_cap
    assert artifact.path.stat().st_size == MAX_REPORT_BYTES
    with pytest.raises(ValueError):
        store.save(_html_of_size(MAX_REPORT_BYTES + 1))
    assert list(root.iterdir()) == [artifact.path]


def test_store_creates_private_directory_and_file_modes(tmp_path):
    root = tmp_path / "reports"
    store = ReportStore(root, clock=FakeClock())

    assert root.is_dir()
    assert stat.S_IMODE(root.stat().st_mode) == 0o700

    artifact = store.save(_html())

    assert artifact.path.parent == root
    assert stat.S_IMODE(artifact.path.stat().st_mode) == 0o600


def test_public_url_contains_only_the_capability(tmp_path):
    clock = FakeClock()
    document = _html()
    store = ReportStore(
        tmp_path / "private-reports",
        clock=clock,
        public_base_url="https://public.test/mcp-action/reports/",
    )

    artifact = store.save(document)

    assert artifact.report_url == (
        f"https://public.test/mcp-action/reports/{artifact.token}"
    )
    assert artifact.expires == pytest.approx(clock.now + 900)
    parsed = urlsplit(artifact.report_url)
    assert parsed.path == f"/mcp-action/reports/{artifact.token}"
    assert parsed.query == ""
    assert parsed.fragment == ""
    assert str(tmp_path) not in artifact.report_url
    assert str(artifact.path) not in artifact.report_url
    assert document.hex() not in artifact.report_url
    assert base64.b64encode(document).decode("ascii") not in artifact.report_url


def test_default_public_base_url(tmp_path):
    store = ReportStore(tmp_path / "reports", clock=FakeClock())

    artifact = store.save(_html())

    assert artifact.report_url == (
        "http://localhost:28080/mcp-action/reports/" + artifact.token
    )


def test_ttl_boundary_899_99_900_and_900_01_seconds(tmp_path):
    clock = FakeClock()
    document = _html()
    store = ReportStore(tmp_path / "reports", clock=clock)
    artifact = store.save(document)

    clock.advance(899.99)
    resolved = store.resolve(artifact.token)
    assert isinstance(resolved, StoredReport)
    assert resolved.data == document
    assert artifact.path.exists()

    clock.advance(0.01)  # exactly 900 seconds: expired
    assert store.resolve(artifact.token) is None
    assert not artifact.path.exists()

    later_clock = FakeClock()
    later_store = ReportStore(tmp_path / "reports-later", clock=later_clock)
    later = later_store.save(document)
    later_clock.advance(900.01)
    assert later_store.resolve(later.token) is None
    assert not later.path.exists()


def test_repeated_resolve_neither_deletes_nor_renews_absolute_ttl(tmp_path):
    clock = FakeClock()
    store = ReportStore(tmp_path / "reports", clock=clock)
    document = _html()
    artifact = store.save(document)
    expires = artifact.expires

    clock.advance(450)
    assert store.resolve(artifact.token).data == document
    clock.advance(449.999)
    assert store.resolve(artifact.token).data == document
    assert artifact.expires == expires
    assert artifact.path.exists()

    clock.advance(0.001)
    assert store.resolve(artifact.token) is None
    assert not artifact.path.exists()


def test_thirty_second_cleanup_sweeps_each_report_at_900_seconds(tmp_path):
    clock = FakeClock()
    store = ReportStore(tmp_path / "reports", clock=clock)
    first = store.save(_html())
    clock.advance(30)
    second = store.save(_html())

    clock.advance(840)  # first age 870, second age 840
    assert store.cleanup() == 0
    assert first.path.exists() and second.path.exists()

    clock.advance(30)  # first age exactly 900
    assert store.cleanup() == 1
    assert not first.path.exists()
    assert second.path.exists()

    clock.advance(30)  # second age exactly 900
    assert store.cleanup() == 1
    assert not second.path.exists()
    assert store.cleanup() == 0


def test_cleanup_is_reusable_for_startup_and_shutdown_sweeps(tmp_path):
    clock = FakeClock()
    root = tmp_path / "reports"
    initial = ReportStore(root, clock=clock)
    leftover = initial.save(_html())

    clock.advance(900)
    started = ReportStore(root, clock=clock)
    assert started.cleanup() == 1  # lifespan startup sweep
    assert not leftover.path.exists()

    final = started.save(_html())
    clock.advance(900)
    assert started.cleanup() == 1  # lifespan shutdown sweep
    assert not final.path.exists()
    assert started.cleanup() == 0  # repeated shutdown is harmless


def test_cleanup_removes_future_skewed_owned_files(tmp_path):
    clock = FakeClock()
    store = ReportStore(tmp_path / "reports", clock=clock)
    artifact = store.save(_html())
    skewed = clock.now + TTL_SECONDS + 60
    os.utime(artifact.path, (skewed, skewed))

    assert store.cleanup() == 1
    assert not artifact.path.exists()


@pytest.mark.parametrize(
    "token",
    [
        "",
        "short",
        "A" * 42,
        "A" * 44,
        "A" * 42 + "!",
        "../outside.html",
        "..\\outside.html",
        "/etc/passwd",
        "A" * 20 + "/" + "B" * 22,
    ],
)
def test_malformed_and_traversal_tokens_return_none(tmp_path, token):
    store = ReportStore(tmp_path / "reports", clock=FakeClock())
    artifact = store.save(_html())
    outside = tmp_path / "outside.html"
    outside.write_bytes(_html("<p>outside</p>"))

    assert store.resolve(token) is None
    assert store.resolve(artifact.token) is not None
    assert outside.read_bytes() == _html("<p>outside</p>")


def test_unknown_but_well_formed_token_returns_none(tmp_path):
    store = ReportStore(tmp_path / "reports", clock=FakeClock())
    artifact = store.save(_html())
    unknown = ("A" if artifact.token[0] != "A" else "B") + artifact.token[1:]

    assert store.resolve(unknown) is None
    assert store.resolve(artifact.token) is not None


def test_symlinked_report_is_neither_served_nor_cleaned_as_a_target(tmp_path):
    clock = FakeClock()
    store = ReportStore(tmp_path / "reports", clock=clock)
    outside = tmp_path / "outside.html"
    outside.write_bytes(_html("<p>outside</p>"))
    artifact = store.save(_html())
    artifact.path.unlink()
    artifact.path.symlink_to(outside)

    assert store.resolve(artifact.token) is None
    assert outside.read_bytes() == _html("<p>outside</p>")

    clock.advance(900)
    assert store.cleanup() == 0
    assert outside.read_bytes() == _html("<p>outside</p>")
    assert artifact.path.is_symlink()


def test_no_metadata_database_or_tombstone_is_created(tmp_path):
    clock = FakeClock()
    root = tmp_path / "reports"
    store = ReportStore(root, clock=clock)
    artifact = store.save(_html())

    assert list(root.iterdir()) == [artifact.path]
    assert store.resolve(artifact.token) is not None
    assert list(root.iterdir()) == [artifact.path]

    clock.advance(900)
    assert store.resolve(artifact.token) is None
    assert list(root.iterdir()) == []
