"""Spec 040 — the Windows-MCP lane: the repaired channel the stack drives.

Transport fix (research.md R1, verified live 2026-11-14): the Windows-MCP
service enforces an HTTP Host allowlist and the WSL port bridge forwards
headers verbatim — every request MUST carry the canonical
`Host: 127.0.0.1:8800` header or the service rejects with
`400 Invalid host header`.

The lane follows the house contracts: consent-gated host operations (the
service's own user-control), genuine output relayed verbatim and bounded
with the truncation named, every failure class in a named honest
envelope, every attempt audited through the shared HermesAudit funnel
(append-only; also feeds the loop-gate classification as an operational,
non-exempt class)."""

from agentic_rag_mcp.windows_mcp.client import (
    BRIDGE_SSE_URL,
    CANONICAL_HOST,
    PROBE_TIMEOUT_S,
    RECOVERY_TEXT,
    TEXT_BOUND,
    TOOL_SCHEMAS,
    bound_text,
    call_tool,
    classify_refusal,
    process_list,
    validate_args,
)
from agentic_rag_mcp.windows_mcp.health import probe_windows_mcp

__all__ = [
    "BRIDGE_SSE_URL",
    "CANONICAL_HOST",
    "PROBE_TIMEOUT_S",
    "RECOVERY_TEXT",
    "TEXT_BOUND",
    "TOOL_SCHEMAS",
    "bound_text",
    "call_tool",
    "classify_refusal",
    "probe_windows_mcp",
    "process_list",
    "validate_args",
]
