"""Spec 040 — the Windows-MCP lane health probe (FR-002).

The browser-lane lesson (2026-11-14): a bare TCP connect to the bridge
succeeds unconditionally while the far side may be dead. The probe speaks
HTTP through the bridge with the canonical Host header — any HTTP
response proves the service; reset/EOF/timeout proves it down, with the
honest envelope naming a recovery that exists."""

from __future__ import annotations

import httpx

from .client import BRIDGE_SSE_URL, PROBE_TIMEOUT_S, RECOVERY_TEXT, _headers


def probe_windows_mcp(url: str = BRIDGE_SSE_URL,
                      timeout_s: float = PROBE_TIMEOUT_S) -> dict:
    """Honest probe: an HTTP response (any status — the service answers
    200 on /sse when alive) -> ok; anything else -> the unavailable
    envelope with the recovery text. Never a fabricated reachable."""
    try:
        # stream, not get: a live SSE server holds /sse open — the
        # response headers prove the service exists, then we close
        with httpx.Client(timeout=timeout_s) as client, \
                client.stream("GET", url, headers=_headers()):
                return {"status": "ok",
                        "windows_mcp": {"reachable": True, "url": url}}
    except (httpx.HTTPError, OSError) as exc:
        return {"status": "error",
                "windows_mcp": {"reachable": False, "url": url},
                "reason": (f"error:windows-mcp-lane-unavailable — the "
                           f"Windows-MCP service ({url}) is unreachable "
                           f"({exc.__class__.__name__}); recover with "
                           f"{RECOVERY_TEXT}")}
