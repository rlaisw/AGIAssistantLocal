"""Spec 037 — dynamic-lane health (FR-010/FR-011): probe the Playwright
MCP server (:3002), report honestly, and name the recovery when down.
Never a hang, never a fabricated reachable."""

from __future__ import annotations

import socket

DEFAULT_URL_HOST = "127.0.0.1"
DEFAULT_URL_PORT = 3002
_RECOVERY = ("start the Scheduled Task: schtasks /run /tn "
             "playwright-mcp-server")


def probe_dynamic(host: str = DEFAULT_URL_HOST, port: int = DEFAULT_URL_PORT,
                  timeout_s: float = 2.0) -> dict:
    """Honest probe: reachable -> ok; anything else -> the unavailable
    envelope with the recovery text (FR-011)."""
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return {"status": "ok",
                    "dynamic": {"reachable": True,
                                "url": f"http://{host}:{port}/sse"}}
    except OSError as exc:
        return {"status": "error",
                "dynamic": {"reachable": False,
                            "url": f"http://{host}:{port}/sse"},
                "reason": (f"error:browser-lane-unavailable — the Playwright "
                           f"MCP server on {host}:{port} is unreachable "
                           f"({exc.__class__.__name__}); recover with "
                           f"{_RECOVERY}")}