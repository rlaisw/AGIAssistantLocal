"""Tool-cache re-sync: live tools/list → Dify's provider cache (spec 011, R4).

The console "Update" flow is known-broken for tool re-sync in Dify 1.17 (tools
only refresh when the server URL changes — source-verified during spec 009
deployment), so the re-sync uses the validated DB path, version-gated.
"""

from __future__ import annotations

import json
import re

import httpx

from . import docker_ops

# 1.18 validated live (spec 029): same tool_mcp_providers.tools column shape;
# read path verified on the running Dify before widening the gate.
SUPPORTED_DB_RESYNC = ("1.17", "1.18")


def fetch_live_tools(mcp_url: str = "http://localhost:28080/mcp") -> list[dict]:
    resp = httpx.post(
        mcp_url,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"tools/list failed ({resp.status_code})")
    for line in resp.text.splitlines():
        if line.startswith("data:") and '"tools"' in line:
            return json.loads(line[5:])["result"]["tools"]
    raise RuntimeError("tools/list response contained no tools")


def build_payload(live_tools: list[dict]) -> list[dict]:
    """The exact cached-blob shape Dify stores on registration."""
    return [
        {
            "name": t.get("name", ""),
            "title": None,
            "description": t.get("description") or "",
            "inputSchema": t.get("inputSchema", {"type": "object", "properties": {}}),
        }
        for t in live_tools
    ]


def resync_path(version: str | None) -> str:
    """Version gate (FR-010): which re-sync path applies."""
    if version and any(version.startswith(prefix) for prefix in SUPPORTED_DB_RESYNC):
        return "db-resync"
    return "skipped"


def sync_provider(dcfg, report) -> None:
    """Register-if-absent + version-gated re-sync, with before/after counts."""
    live = fetch_live_tools()
    payload = build_payload(live)
    names = sorted(t["name"] for t in payload)

    if dcfg.console_email and dcfg.console_password:
        from .dify_console import DifyConsole

        console = DifyConsole(dcfg)
        console.login()
        providers = console.list_mcp_providers()
        existing = any(p.get("name") == "agentic-rag" for p in providers)
        if not existing:
            console.create_mcp_provider("agentic-rag", "http://agentic-rag:28080/mcp")
            report.add("register-mcp", evidence="created agentic-rag (console)")
            report.add("sync-tools", evidence=f"{len(names)} tools via create-path")
            return
    else:
        cached = docker_ops.cached_tools(dcfg.db_container, "agentic-rag")
        if cached is None:
            report.add(
                "register-mcp", "failed",
                evidence="provider not registered and no console credentials to register it — "
                         "set [dify] console_email/console_password",
            )
            return

    version = docker_ops.dify_version(dcfg.api_container)
    path = resync_path(version)
    if path == "db-resync":
        before = docker_ops.cached_tools(dcfg.db_container, "agentic-rag") or []
        docker_ops.update_cached_tools(dcfg.db_container, "agentic-rag",
                                        json.dumps(payload))
        report.add("sync-tools",
                   evidence=f"path={path} version={version} "
                            f"before={len(before)} after={len(names)}")
    else:
        report.add("sync-tools", "skipped",
                   evidence=f"path={path} (version={version or 'unknown'} not in "
                            f"{SUPPORTED_DB_RESYNC}; update manually via Dify UI or add support)")


def ensure_no_secret_leak(text: str, secrets: list[str]) -> str:  # defensive helper for tests
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text
