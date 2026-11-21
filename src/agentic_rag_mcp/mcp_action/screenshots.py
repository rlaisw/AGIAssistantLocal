"""Private temporary screenshot files with capability-token delivery."""

from __future__ import annotations

import os
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

MAX_IMAGE_BYTES = 10 * 1024 * 1024
TTL_SECONDS = 900.0
DEFAULT_PUBLIC_BASE_URL = "http://localhost:28080/mcp-action/screenshots"
DEFAULT_ROOT = Path("/tmp/agentic-rag-mcp-screenshots")

_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
_OWNED_FILE = re.compile(r"[A-Za-z0-9_-]{43}\.(?:png|jpg)")
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


@dataclass(frozen=True)
class ScreenshotArtifact:
    """Internal storage metadata; public results use only image_url/expiry."""

    token: str
    mime: str
    path: Path
    expires: float
    image_url: str


@dataclass(frozen=True)
class StoredImage:
    data: bytes
    mime_type: str


def _detect_mime(data: bytes) -> str | None:
    if data.startswith(_PNG_MAGIC):
        return "image/png"
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    return None


class ScreenshotStore:
    def __init__(
        self,
        root: Path,
        clock: Callable[[], float] = time.monotonic,
        public_base_url: str = DEFAULT_PUBLIC_BASE_URL,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self._clock = clock
        self._public_base_url = public_base_url.rstrip("/")

    def save(self, data: bytes, mime_type: str = "") -> ScreenshotArtifact:
        """Store one image; magic bytes, not the caller's MIME claim, are authoritative."""
        if not isinstance(data, bytes) or len(data) > MAX_IMAGE_BYTES:
            raise ValueError("screenshot must be bytes no larger than 10 MiB")
        mime = _detect_mime(data)
        if mime is None:
            raise ValueError("screenshot must contain PNG or JPEG magic bytes")

        token = secrets.token_urlsafe(32)
        if not isinstance(token, str) or _TOKEN.fullmatch(token) is None:
            raise RuntimeError("screenshot token generator returned an invalid capability")

        expires = self._clock() + TTL_SECONDS
        suffix = ".png" if mime == "image/png" else ".jpg"
        path = self.root / f"{token}{suffix}"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
            path.chmod(0o600)
            # The private file's mtime is its absolute expiry, so cleanup also
            # works for leftovers found by a new store after process startup.
            os.utime(path, (expires, expires))
        except Exception:
            path.unlink(missing_ok=True)
            raise

        return ScreenshotArtifact(
            token=token,
            mime=mime,
            path=path,
            expires=expires,
            image_url=f"{self._public_base_url}/{token}",
        )

    def resolve(self, token: str) -> StoredImage | None:
        if not isinstance(token, str) or _TOKEN.fullmatch(token) is None:
            return None
        paths = [
            path
            for suffix in (".png", ".jpg")
            if (path := self.root / f"{token}{suffix}").is_file()
            and not path.is_symlink()
        ]
        if len(paths) != 1:
            return None
        path = paths[0]
        try:
            if self._clock() >= path.stat().st_mtime:
                path.unlink(missing_ok=True)
                return None
            data = path.read_bytes()
        except FileNotFoundError:
            return None
        mime = _detect_mime(data) if len(data) <= MAX_IMAGE_BYTES else None
        if mime is None:
            path.unlink(missing_ok=True)
            return None
        return StoredImage(data=data, mime_type=mime)

    def cleanup(self) -> int:
        """Remove every expired owned screenshot; repeated sweeps are harmless."""
        now = self._clock()
        removed = 0
        try:
            paths = list(self.root.iterdir())
        except FileNotFoundError:
            return 0
        for path in paths:
            if _OWNED_FILE.fullmatch(path.name) is None or path.is_symlink():
                continue
            try:
                if path.is_file() and now >= path.stat().st_mtime:
                    path.unlink()
                    removed += 1
            except FileNotFoundError:
                continue
        return removed


_default_store: ScreenshotStore | None = None
_default_store_lock = threading.Lock()


def get_screenshot_store() -> ScreenshotStore:
    global _default_store
    with _default_store_lock:
        if _default_store is None:
            _default_store = ScreenshotStore(DEFAULT_ROOT)
        return _default_store
