"""Spec 037 — dynamic-lane health (FR-010/FR-011): probe the Playwright
MCP server (:3002), report honestly, and name the recovery when down.
Never a hang, never a fabricated reachable.

2026-11-14 (browser-lane-unavailable lifecycle): the old bare-TCP probe
connected to the WSL bridge, which accepts unconditionally regardless of
the far side — browser_status reported reachable:true while the engine
was dead. The probe now speaks HTTP: any HTTP response from the SSE
server proves the engine; a closed/reset connection (what the bridge
does when its dial to :3002 fails) proves it dead."""

from __future__ import annotations

import httpx

DEFAULT_URL_HOST = "127.0.0.1"
DEFAULT_URL_PORT = 3002
_RECOVERY = ("start the Scheduled Task: schtasks /run /tn "
             "playwright-mcp-server")


def probe_dynamic(host: str = DEFAULT_URL_HOST, port: int = DEFAULT_URL_PORT,
                  timeout_s: float = 2.0) -> dict:
    """Honest probe: an HTTP response (any status) from the SSE server ->
    ok; anything else -> the unavailable envelope with the recovery text
    (FR-011)."""
    url = f"http://{host}:{port}/sse"
    try:
        # stream, not get: a live SSE server holds /sse open — we only need
        # the response headers to prove the HTTP server exists, then close
        with httpx.Client(timeout=timeout_s) as client, client.stream("GET", url):
            return {"status": "ok",
                    "dynamic": {"reachable": True,
                                "url": url}}
    except (httpx.HTTPError, OSError) as exc:
        return {"status": "error",
                "dynamic": {"reachable": False,
                            "url": url},
                "reason": (f"error:browser-lane-unavailable — the Playwright "
                           f"MCP server on {host}:{port} is unreachable "
                           f"({exc.__class__.__name__}); recover with "
                           f"{_RECOVERY}")}
