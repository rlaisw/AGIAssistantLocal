"""Unit: private, expiring MCP-Action screenshot storage (spec 047, T016)."""

from __future__ import annotations

import base64
import re
import stat
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import urlsplit

import pytest

import agentic_rag_mcp.mcp_action.screenshots as screenshot_module
from agentic_rag_mcp.mcp_action.screenshots import ScreenshotStore, StoredImage

FIXTURES = Path(__file__).parents[1] / "fixtures" / "mcp_action"
PNG = (FIXTURES / "tiny.png").read_bytes()
JPEG = (FIXTURES / "tiny.jpg").read_bytes()
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class FakeClock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_save_uses_256_bit_urlsafe_capability_tokens(tmp_path, monkeypatch):
    token_factory = Mock(return_value="A" * 43)
    monkeypatch.setattr(screenshot_module.secrets, "token_urlsafe", token_factory)
    store = ScreenshotStore(tmp_path / "shots", clock=lambda: 12.0)

    artifact = store.save(PNG)

    token_factory.assert_called_once_with(32)
    assert artifact.token == "A" * 43
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", artifact.token)


@pytest.mark.parametrize(
    ("data", "claimed_mime", "expected_mime"),
    [
        (PNG, "", "image/png"),
        (PNG, "image/jpeg", "image/png"),
        (PNG, "text/plain", "image/png"),
        (JPEG, "", "image/jpeg"),
        (JPEG, "image/png", "image/jpeg"),
        (JPEG, "application/octet-stream", "image/jpeg"),
    ],
)
def test_magic_bytes_not_claimed_mime_determine_the_stored_type(
    tmp_path, data, claimed_mime, expected_mime
):
    store = ScreenshotStore(tmp_path / "shots", clock=FakeClock())

    artifact = store.save(data, claimed_mime)

    assert artifact.mime == expected_mime
    resolved = store.resolve(artifact.token)
    assert isinstance(resolved, StoredImage)
    assert resolved.data == data
    assert resolved.mime_type == expected_mime


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not an image",
        b"\x89PNG\r\n\x1a",  # truncated PNG signature
        b"\xff\xd8",  # truncated JPEG signature
        b"GIF89a" + b"\0" * 16,
        base64.b64encode(PNG),
    ],
)
@pytest.mark.parametrize("claimed_mime", ["image/png", "image/jpeg"])
def test_invalid_image_bytes_are_rejected_without_leaving_files(
    tmp_path, data, claimed_mime
):
    root = tmp_path / "shots"
    store = ScreenshotStore(root, clock=FakeClock())

    with pytest.raises(ValueError):
        store.save(data, claimed_mime)

    assert list(root.iterdir()) == []


def test_one_image_may_be_exactly_10_mib_but_not_larger(tmp_path):
    root = tmp_path / "shots"
    store = ScreenshotStore(root, clock=FakeClock())
    at_cap = PNG + b"\0" * (MAX_IMAGE_BYTES - len(PNG))

    artifact = store.save(at_cap)

    assert artifact.path.read_bytes() == at_cap
    assert artifact.path.stat().st_size == MAX_IMAGE_BYTES
    with pytest.raises(ValueError):
        store.save(at_cap + b"\0")
    assert list(root.iterdir()) == [artifact.path]


def test_store_creates_private_directory_and_file_modes(tmp_path):
    root = tmp_path / "shots"
    store = ScreenshotStore(root, clock=FakeClock())

    assert root.is_dir()
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    artifact = store.save(JPEG)
    assert artifact.path.parent == root
    assert stat.S_IMODE(artifact.path.stat().st_mode) == 0o600


def test_public_url_contains_only_the_capability_and_expiry_is_metadata(tmp_path):
    clock = FakeClock()
    store = ScreenshotStore(
        tmp_path / "private-shots",
        clock=clock,
        public_base_url="https://public.test/mcp-action/screenshots/",
    )

    artifact = store.save(PNG)

    assert artifact.image_url == (
        f"https://public.test/mcp-action/screenshots/{artifact.token}"
    )
    assert artifact.expires == pytest.approx(clock.now + 900)
    parsed = urlsplit(artifact.image_url)
    assert parsed.path == f"/mcp-action/screenshots/{artifact.token}"
    assert parsed.query == ""
    assert parsed.fragment == ""
    assert str(tmp_path) not in artifact.image_url
    assert str(artifact.path) not in artifact.image_url
    assert PNG.hex() not in artifact.image_url
    assert base64.b64encode(PNG).decode("ascii") not in artifact.image_url


def test_default_public_base_url(tmp_path):
    store = ScreenshotStore(tmp_path / "shots", clock=FakeClock())

    artifact = store.save(PNG)

    assert artifact.image_url == (
        "http://localhost:28080/mcp-action/screenshots/" + artifact.token
    )


def test_repeated_resolve_neither_deletes_nor_renews_absolute_ttl(tmp_path):
    clock = FakeClock()
    store = ScreenshotStore(tmp_path / "shots", clock=clock)
    artifact = store.save(PNG)

    clock.advance(450)
    first = store.resolve(artifact.token)
    assert first is not None and first.data == PNG
    assert artifact.path.exists()
    assert artifact.expires == pytest.approx(1_900)

    clock.advance(449.999)
    second = store.resolve(artifact.token)
    assert second is not None and second.data == PNG
    assert artifact.path.exists()
    assert artifact.expires == pytest.approx(1_900)

    clock.advance(0.001)
    assert store.resolve(artifact.token) is None
    assert not artifact.path.exists()
    assert store.resolve(artifact.token) is None


def test_thirty_second_cleanup_sweeps_expire_each_image_at_900_seconds(tmp_path):
    clock = FakeClock()
    store = ScreenshotStore(tmp_path / "shots", clock=clock)
    first = store.save(PNG)
    clock.advance(30)
    second = store.save(JPEG)

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


def test_expired_resolve_deletes_the_owned_file(tmp_path):
    clock = FakeClock()
    store = ScreenshotStore(tmp_path / "shots", clock=clock)
    artifact = store.save(JPEG)

    clock.advance(899.999)
    assert store.resolve(artifact.token) is not None
    clock.advance(0.001)

    assert store.resolve(artifact.token) is None
    assert not artifact.path.exists()


def test_cleanup_is_reusable_for_startup_and_shutdown_sweeps(tmp_path):
    clock = FakeClock()
    root = tmp_path / "shots"
    initial = ScreenshotStore(root, clock=clock)
    leftover = initial.save(PNG)

    clock.advance(900)
    started = ScreenshotStore(root, clock=clock)
    assert started.cleanup() == 1  # lifespan startup sweep
    assert not leftover.path.exists()

    final = started.save(JPEG)
    clock.advance(900)
    assert started.cleanup() == 1  # lifespan shutdown sweep
    assert not final.path.exists()
    assert started.cleanup() == 0  # repeated shutdown is harmless


@pytest.mark.parametrize(
    "token",
    [
        "",
        "short",
        "A" * 42,
        "A" * 44,
        "A" * 42 + "!",
        "../outside.png",
        "..\\outside.png",
        "/etc/passwd",
        "A" * 20 + "/" + "B" * 22,
    ],
)
def test_malformed_and_traversal_tokens_return_none(tmp_path, token):
    store = ScreenshotStore(tmp_path / "shots", clock=FakeClock())
    artifact = store.save(PNG)
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG)

    assert store.resolve(token) is None
    assert store.resolve(artifact.token) is not None
    assert outside.read_bytes() == PNG


def test_unknown_but_well_formed_token_returns_none(tmp_path):
    store = ScreenshotStore(tmp_path / "shots", clock=FakeClock())
    artifact = store.save(PNG)
    unknown = ("A" if artifact.token[0] != "A" else "B") + artifact.token[1:]

    assert store.resolve(unknown) is None
    assert store.resolve(artifact.token) is not None


def test_no_metadata_database_or_tombstone_is_created(tmp_path):
    clock = FakeClock()
    root = tmp_path / "shots"
    store = ScreenshotStore(root, clock=clock)
    artifact = store.save(PNG)

    assert list(root.iterdir()) == [artifact.path]
    assert store.resolve(artifact.token) is not None
    assert list(root.iterdir()) == [artifact.path]

    clock.advance(900)
    assert store.resolve(artifact.token) is None
    assert list(root.iterdir()) == []
