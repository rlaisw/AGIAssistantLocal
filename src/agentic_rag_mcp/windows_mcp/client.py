"""Spec 040 — the Windows-MCP lane client: transport, validation, dispatch.

The tool surface below was captured LIVE from the running service on
2026-11-14 (research.md R2) via tools/list on the repaired transport —
no raw PowerShell tool exists on this build; the diagnostics acceptance
case maps to the native Process tool."""

from __future__ import annotations

import time

from mcp import ClientSession
from mcp.client.sse import sse_client

from ..hermes_audit import HermesAudit

BRIDGE_SSE_URL = "http://172.17.0.1:18800/sse"
CANONICAL_HOST = "127.0.0.1:8800"
PROBE_TIMEOUT_S = 2.0
TEXT_BOUND = 4000

_RECOVERY = ("start the Scheduled Task: "
             "schtasks /run /tn windows-mcp-server")
RECOVERY_TEXT = _RECOVERY

TOOL_SCHEMAS: dict[str, dict] = {
    "Process": {"args": {"mode", "name", "pid", "sort_by", "limit", "force"},
                "required": {"mode"}},
    "Clipboard": {"args": {"mode", "text"}, "required": {"mode"}},
    "Notification": {"args": {"title", "message", "app_id"},
                      "required": {"title", "message", "app_id"}},
    "Registry": {"args": {"mode", "path", "name", "value", "type"},
                 "required": {"mode", "path"}},
}


def _headers() -> dict:
    """The transport fix: the canonical Host header on every request —
    the service 400s 'Invalid host header' without it (research.md R1)."""
    return {"Host": CANONICAL_HOST}


def validate_args(tool: str, args: dict | None) -> tuple[bool, str | None]:
    """Shape validation against the captured schemas: invalid shape ->
    blocked envelope text, NO service call (contracts/windowsmcp-lane.md)."""
    schema = TOOL_SCHEMAS.get(tool)
    if schema is None:
        return False, (f"rejected: unknown tool {tool!r} "
                       f"(surface: {sorted(TOOL_SCHEMAS)})")
    args = args or {}
    missing = sorted(schema["required"] - set(args))
    if missing:
        return False, f"rejected: {tool} requires {missing}"
    unknown = sorted(set(args) - schema["args"])
    if unknown:
        return False, (f"rejected: unknown args for {tool}: {unknown} "
                       f"(allowed: {sorted(schema['args'])})")
    return True, None


def bound_text(text: str) -> tuple[str, bool]:
    """House-rule bounding: the relay never exceeds TEXT_BOUND characters
    and the truncation is named honestly by the caller when it happens."""
    t = text or ""
    return t[:TEXT_BOUND], len(t) > TEXT_BOUND


def classify_refusal(text: str) -> bool:
    """A host consent that was declined/timed out is a named refusal —
    never reported as success, never retried without the owner."""
    low = (text or "").lower()
    return any(k in low for k in ("declin", "not approved", "cancelled",
                                  "canceled", "user_control", "consent",
                                  "denied"))


def _op(tool: str) -> str:
    return f"windows-mcp-{tool.lower()}"


def _unavailable(exc: Exception) -> str:
    return (f"error:windows-mcp-lane-unavailable — the Windows-MCP "
            f"service ({BRIDGE_SSE_URL}) is unreachable "
            f"({exc.__class__.__name__}); recover with {_RECOVERY}")


async def call_tool(tool: str, args: dict, conversation_id: str,
                    audit: HermesAudit | None = None) -> dict:
    """One consented tool call through the repaired lane. Every path —
    executed, blocked, error — audits exactly one row."""
    t0 = time.monotonic()
    ok, reason = validate_args(tool, args)
    if not ok:
        if audit:
            audit.write_attempt(decision="blocked", operation=_op(tool),
                                normalized_path=None, allowed_root="",
                                reason=reason,
                                conversation_id=conversation_id,
                                duration_s=time.monotonic() - t0)
        return {"status": "blocked", "reason": reason}
    if not conversation_id:
        if audit:
            audit.write_attempt(
                decision="blocked", operation=_op(tool),
                normalized_path=None, allowed_root="",
                reason="rejected: conversation_id is required (audited)",
                conversation_id=conversation_id,
                duration_s=time.monotonic() - t0)
        return {"status": "blocked",
                "reason": "rejected: conversation_id is required (audited)"}
    try:
        async with sse_client(BRIDGE_SSE_URL, headers=_headers()) \
                as (read, write), \
                ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool(tool, args)
                text = "\n".join(getattr(c, "text", "")
                                 for c in res.content
                                 if getattr(c, "text", None))
                if res.isError:
                    if classify_refusal(text):
                        envelope = {
                            "status": "blocked",
                            "reason": ("blocked: the host did not approve "
                                       "execution — nothing ran; no retry "
                                       "without the owner")}
                        decision = "blocked"
                    else:
                        envelope = {
                            "status": "error",
                            "reason": (f"error:windows-mcp-tool-error — "
                                       f"{text}")}
                        decision = "error"
                    if audit:
                        audit.write_attempt(
                            decision=decision, operation=_op(tool),
                            normalized_path=None, allowed_root="",
                            reason=envelope["reason"][:250],
                            conversation_id=conversation_id,
                            duration_s=time.monotonic() - t0)
                    return envelope
                bounded, truncated = bound_text(text)
                envelope = {"status": "ok", "tool": tool, "text": bounded,
                            "truncated": truncated}
                if truncated:
                    envelope["note"] = (f"output truncated at {TEXT_BOUND} "
                                        f"characters")
                if audit:
                    audit.write_attempt(
                        decision="executed", operation=_op(tool),
                        normalized_path=None, allowed_root="",
                        outcome=envelope["text"][:200],
                        conversation_id=conversation_id,
                        duration_s=time.monotonic() - t0)
                return envelope
    except Exception as exc:  # noqa: BLE001 — every failure mode is one
        # honest envelope, the house FR-013 pattern shared by all lanes
        reason = _unavailable(exc)
        if audit:
            audit.write_attempt(decision="error", operation=_op(tool),
                                normalized_path=None, allowed_root="",
                                reason=reason,
                                conversation_id=conversation_id,
                                duration_s=time.monotonic() - t0)
        return {"status": "error", "reason": reason}


async def process_list(sort_by: str = "memory", limit: int = 5,
                       conversation_id: str = "",
                       audit: HermesAudit | None = None) -> dict:
    """The acceptance case (spec 040, quickstart E2E-1): top processes by
    the given sort, genuine output relayed verbatim."""
    return await call_tool("Process",
                           {"mode": "list", "sort_by": sort_by,
                            "limit": limit},
                           conversation_id, audit)
