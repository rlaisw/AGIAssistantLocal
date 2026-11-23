"""Private, expiring self-contained HTML health reports (spec 048)."""

from __future__ import annotations

import os
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

TTL_SECONDS = 900
MAX_REPORT_BYTES = 5 * 1024 * 1024
DEFAULT_PUBLIC_BASE_URL = "http://localhost:28080/mcp-action/reports"
DEFAULT_ROOT = Path("/tmp/agentic-rag-mcp-reports")

_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
_OWNED_FILE = re.compile(r"[A-Za-z0-9_-]{43}\.html")

_FORBIDDEN_TAG = re.compile(
    r"<\s*/?\s*(?:script|iframe|object|embed|form|base|link)\b", re.IGNORECASE
)
_EVENT_HANDLER = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)
_META_REFRESH = re.compile(
    r"<meta\b[^>]*\bhttp-equiv\s*=\s*[\"']?\s*refresh", re.IGNORECASE
)
_RESOURCE_ATTR = re.compile(
    r"\b(?:src|href|xlink:href)\s*=\s*[\"']?\s*([^\"'\s>]+)", re.IGNORECASE
)
_CSS_URL = re.compile(r"url\(\s*[\"']?\s*([^\"')]*)", re.IGNORECASE)


@dataclass(frozen=True)
class ReportArtifact:
    """Internal storage metadata; only the capability URL leaves the sidecar."""

    token: str
    path: Path
    expires: float
    report_url: str


@dataclass(frozen=True)
class StoredReport:
    data: bytes


def _reject(message: str) -> None:
    raise ValueError(message)


def _validate(document: bytes) -> None:
    """Enforce the report contract without echoing untrusted content."""
    if not isinstance(document, bytes) or len(document) > MAX_REPORT_BYTES:
        _reject("report must be bytes no larger than 5 MiB")
    try:
        text = document.decode("utf-8-sig")
    except UnicodeDecodeError:
        _reject("report must be complete UTF-8 HTML")
    if "\x00" in text:
        _reject("report must not contain NUL bytes")

    lowered = text.lower()
    if (
        "<html" not in lowered
        or "</html>" not in lowered
        or not lowered.rstrip().endswith("</html>")
    ):
        _reject("report must be one complete HTML document")

    if (
        _FORBIDDEN_TAG.search(text)
        or _EVENT_HANDLER.search(text)
        or _META_REFRESH.search(text)
        or "javascript:" in lowered
        or "data:text/html" in lowered
        or "@import" in lowered
    ):
        _reject("report must not contain active or external content")

    for value in _RESOURCE_ATTR.findall(text):
        if not value.lower().startswith(("data:", "#")):
            _reject("report must not reference external resources")
    for value in _CSS_URL.findall(text):
        if value and not value.strip().lower().startswith(("data:", "#")):
            _reject("report must not reference external resources")


class ReportStore:
    def __init__(
        self,
        root: Path,
        clock: Callable[[], float] = time.time,
        public_base_url: str = DEFAULT_PUBLIC_BASE_URL,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self._clock = clock
        self._public_base_url = public_base_url.rstrip("/")

    def save(self, html: bytes) -> ReportArtifact:
        _validate(html)

        token = secrets.token_urlsafe(32)
        if not isinstance(token, str) or _TOKEN.fullmatch(token) is None:
            raise RuntimeError("report token generator returned an invalid capability")

        expires = self._clock() + TTL_SECONDS
        path = self.root / f"{token}.html"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(html)
            path.chmod(0o600)
            # The private file's mtime is its absolute expiry, so cleanup also
            # works for leftovers found by a new store after process startup.
            os.utime(path, (expires, expires))
        except Exception:
            path.unlink(missing_ok=True)
            raise

        return ReportArtifact(
            token=token,
            path=path,
            expires=expires,
            report_url=f"{self._public_base_url}/{token}",
        )

    def resolve(self, token: str) -> StoredReport | None:
        if not isinstance(token, str) or _TOKEN.fullmatch(token) is None:
            return None
        path = self.root / f"{token}.html"
        try:
            if path.is_symlink() or not path.is_file():
                return None
            if self._clock() >= path.stat().st_mtime:
                path.unlink(missing_ok=True)
                return None
            data = path.read_bytes()
        except FileNotFoundError:
            return None
        if len(data) > MAX_REPORT_BYTES:
            path.unlink(missing_ok=True)
            return None
        return StoredReport(data=data)

    def cleanup(self) -> int:
        """Remove expired or future-skewed owned reports; repeated sweeps are harmless."""
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
                if not path.is_file():
                    continue
                mtime = path.stat().st_mtime
                if now >= mtime or mtime > now + TTL_SECONDS:
                    path.unlink()
                    removed += 1
            except FileNotFoundError:
                continue
        return removed


_default_store: ReportStore | None = None
_default_store_lock = threading.Lock()


def get_report_store() -> ReportStore:
    global _default_store
    with _default_store_lock:
        if _default_store is None:
            _default_store = ReportStore(DEFAULT_ROOT)
        return _default_store


class ReportPublisher:
    """Store one validated report and expose only temporary capability metadata."""

    def __init__(self, store: ReportStore | None = None) -> None:
        self.store = store if store is not None else get_report_store()

    def publish(self, html: str | bytes) -> dict:
        try:
            data = html.encode("utf-8") if isinstance(html, str) else html
            artifact = self.store.save(data)
            return {
                "status": "published",
                "report_url": artifact.report_url,
                "expires_in_s": int(TTL_SECONDS),
            }
        except Exception:  # noqa: BLE001 - no path/token/report content crosses here
            return {
                "status": "failed",
                "reason": "The temporary health report could not be published.",
            }
