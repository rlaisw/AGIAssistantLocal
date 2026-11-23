"""Application logging setup (spec 008; research.md D1–D8).

One root-logger configuration: rotating file + stderr console mirror, a
redaction filter enforcing the privacy rules, and honest fallbacks —
invalid level → WARNING record + default; unwritable destination →
console-only, never a blocked start. Console is stderr: stdout carries the
stdio MCP protocol.
"""

from __future__ import annotations

import logging
import re
import sys
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

log = logging.getLogger("agentic_rag_mcp.logging")

# RedactionRule (data-model.md, binding list) — applied to every record,
# every level, on both handlers.
_REDACTIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(/mcp-action/screenshots/)[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])"),
     r"\1[REDACTED:screenshot-token]"),
    (re.compile(r"(/mcp-action/reports/)[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])"),
     r"\1[REDACTED:report-token]"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+"), r"\1[REDACTED:token]"),
    (re.compile(r"(client_secret[\"']?\s*[:=]\s*[\"'])[^\"']+"), r"\1[REDACTED:secret]"),
    (re.compile(r"(api[_-]?key[\"']?\s*[:=]\s*[\"'])[^\"']+"), r"\1[REDACTED:secret]"),
    (re.compile(r"https://\S*(?:tempauth|api\.onedrive\.com)\S*"), "[REDACTED:download-url]"),
]

# WARN is the documented shorthand for the canonical WARNING level (spec 008)
_LEVELS = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING,
           "WARN": logging.WARNING, "ERROR": logging.ERROR}

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class RedactionFilter(logging.Filter):
    """Scrubs credential patterns from the rendered message before any write."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 — never block logging on bad args
            return True
        redacted = msg
        for pattern, repl in _REDACTIONS:
            redacted = pattern.sub(repl, redacted)
        if redacted != msg:
            record.msg = redacted
            record.args = None
        return True


@dataclass
class LoggingSetup:
    level_name: str
    level: int
    path: Path
    writable: bool
    fallback_reason: str | None = None

    def status_dict(self) -> dict:
        return {"level": self.level_name, "log_file": str(self.path),
                "writable": self.writable}


_setup: LoggingSetup | None = None


def current_setup() -> LoggingSetup:
    """The active setup (for the status tool); honest default before configure."""
    if _setup is not None:
        return _setup
    level = logging.getLogger().getEffectiveLevel()
    return LoggingSetup(level_name=logging.getLevelName(level), level=level,
                        path=Path(""), writable=False,
                        fallback_reason="logging not configured yet")


def configure_logging(cfg) -> LoggingSetup:
    """Attach the file+console setup to the root logger (FR-001..FR-011).

    Idempotent: resets root handlers so repeated server builds (per test or
    per process) never accumulate. Never raises — logging must not prevent
    the application from running.
    """
    global _setup
    raw_level = str(getattr(cfg, "log_level", "INFO"))
    level = _LEVELS.get(raw_level.strip().upper())
    pending_warn = None
    if level is None:
        level = logging.INFO
        pending_warn = raw_level
    path = Path(getattr(cfg, "log_file", None) or
                Path(cfg.state_db).parent / "logs" / "server.log")

    root = logging.getLogger()
    for handler in list(root.handlers):  # idempotent reconfigure
        root.removeHandler(handler)
    root.setLevel(level)

    formatter = logging.Formatter(_FORMAT)
    formatter.converter = time.gmtime  # UTC records (FR-001)

    console = logging.StreamHandler(sys.stderr)  # stdout belongs to the stdio protocol
    console.setFormatter(formatter)
    console.addFilter(RedactionFilter())
    root.addHandler(console)

    writable, reason = True, None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8"):  # probe-open: catch unwritable now
            pass
        file_handler = RotatingFileHandler(
            path, maxBytes=int(getattr(cfg, "rotation_size_mb", 10.0) * 1024 * 1024),
            backupCount=int(getattr(cfg, "rotation_count", 5)), encoding="utf-8",
            delay=True)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(RedactionFilter())
        root.addHandler(file_handler)
    except OSError as exc:
        writable, reason = False, str(exc)
        log.error("log file not writable: %s — falling back to console-only", exc)

    _setup = LoggingSetup(level_name=logging.getLevelName(level), level=level,
                          path=path, writable=writable, fallback_reason=reason)
    log.info("logging configured: level=%s file=%s writable=%s",
             _setup.level_name, path, writable)
    if pending_warn is not None:  # FR-003: honest fallback record, in the file
        log.warning("invalid log level %r — using INFO", raw_level)
    return _setup
