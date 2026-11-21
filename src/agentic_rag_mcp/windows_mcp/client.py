"""Spec 040 — the Windows-MCP lane client: transport, validation, dispatch.

The tool surface below was captured LIVE from the running service on
2026-11-14 (research.md R2) via tools/list on the repaired transport —
no raw PowerShell tool exists on this build; the diagnostics acceptance
case maps to the native Process tool."""

from __future__ import annotations

import asyncio
import base64
import binascii
import os
import re
import time
from dataclasses import dataclass

from mcp import ClientSession
from mcp.client.sse import sse_client

from ..hermes_audit import HermesAudit

BRIDGE_SSE_URL = "http://172.17.0.1:18800/sse"
CANONICAL_HOST = "127.0.0.1:8800"
PROBE_TIMEOUT_S = 2.0
TEXT_BOUND = 4000
_IMAGE_BYTES_BOUND = 10 * 1024 * 1024
_IMAGE_BASE64_BOUND = 4 * ((_IMAGE_BYTES_BOUND + 2) // 3)


@dataclass(frozen=True)
class CapturedImage:
    data: bytes
    mime_type: str


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

# spec 041: the applet tiers' tools, schemas captured live (schemas.py)
from .schemas import GUI_TOOL_SCHEMAS

TOOL_SCHEMAS.update(GUI_TOOL_SCHEMAS)


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


def _extract_image(content: list) -> CapturedImage:
    """Decode exactly one PNG/JPEG without echoing its data into errors."""
    images = [item for item in content
              if getattr(item, "type", None) == "image"]
    if len(images) != 1:
        raise ValueError(
            f"expected exactly one ImageContent, got {len(images)}")
    image = images[0]
    mime_type = getattr(image, "mimeType", None)
    if mime_type not in {"image/png", "image/jpeg"}:
        raise ValueError("unsupported image MIME; expected PNG or JPEG")
    encoded = getattr(image, "data", None)
    if not isinstance(encoded, str):
        raise TypeError("malformed image Base64")
    if len(encoded) > _IMAGE_BASE64_BOUND:
        raise ValueError("decoded image exceeds the 10 MiB limit")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, TypeError, ValueError) as exc:
        raise ValueError("malformed image Base64") from exc
    if len(data) > _IMAGE_BYTES_BOUND:
        raise ValueError("decoded image exceeds the 10 MiB limit")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        detected_mime = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        detected_mime = "image/jpeg"
    else:
        raise ValueError("image bytes are not PNG or JPEG")
    if detected_mime != mime_type:
        raise ValueError("image magic bytes do not match the declared MIME")
    return CapturedImage(data=data, mime_type=mime_type)


def classify_refusal(text: str) -> bool:
    """A host consent that was declined/timed out is a named refusal —
    never reported as success, never retried without the owner.
    USER_CONTROL is NOT here: that code is the consent-WAIT signal the
    call loop handles by retrying (the gateway's documented pattern)."""
    low = (text or "").lower()
    return any(k in low for k in ("declin", "not approved", "cancelled",
                                  "canceled", "consent", "denied"))


def _user_control_wait(text: str) -> float | None:
    """Parse the USER_CONTROL consent-wait signal: the service asks the
    client to wait ~wait_seconds while the desktop user approves."""
    if '"code": "USER_CONTROL"' not in (text or ""):
        return None
    import json as _json
    try:
        data = _json.loads(text)
    except ValueError:
        return None
    if data.get("code") != "USER_CONTROL":
        return None
    wait = ((data.get("status") or {}).get("wait_seconds"))
    if isinstance(wait, (int, float)) and 0 < wait <= 30:
        return float(wait)
    return 10.0  # the signal without a sane number: the house default


# error-windows-mcp-tool-error (2026-11-14): the service's USER_CONTROL
# "state: user" is a desktop-activity deferral — when the consent retries
# exhaust with the signal still pending, the honest envelope is a named
# deferral (nothing ran, ask again shortly), NOT a generic tool-error and
# NOT the schtasks hint (the service is up)
_DEFERRAL = ("blocked: the Windows-MCP service deferred the call while "
             "the desktop user is active (USER_CONTROL) — nothing ran; "
             "wait a few seconds and ask again")


def _op(tool: str) -> str:
    return f"windows-mcp-{tool.lower()}"


def machine_processors() -> int:
    """The Windows host's logical-processor count, baked into the
    container at redeploy time by the deploy flow (the WSL VM's own
    cpu_count is capped and must never be used for host math). 0 when
    unknown -> the lane falls back to the raw + explanation presentation."""
    try:
        n = int(os.environ.get("WINDOWS_LOGICAL_PROCESSORS", "0"))
    except ValueError:
        return 0
    return n if 0 < n <= 1024 else 0


_ROW_RE = re.compile(
    r"^\s*(?P<pid>\d+)\s+(?P<name>.*?)\s+(?P<cpu>[\d.]+)%\s+(?P<mem>[\d.]+)\s*MB\s*$",
    re.MULTILINE)


def render_cpu_scale(text: str, processors: int) -> str:
    """Present CPU on the human scale: the whole-machine share IS the
    value (Task-Manager-style, 100% = every core fully busy); the raw
    per-core aggregate moves to a footnote so no >100% number leads the
    table (the-value-of-cpu-is-impossibel round 3, 2026-11-14). Falls
    back to the raw text when the count is unknown or the self-check
    fails (a share above ~100% means the count is inconsistent with the
    data — never present wrong numbers)."""
    if processors <= 0:
        return text
    rows = []
    for m in _ROW_RE.finditer(text):
        cpu = float(m.group("cpu"))
        share = cpu / processors
        if share > 100.5:
            return text
        rows.append((m, cpu, share))
    if not rows:
        return text
    out = text
    for m, cpu, share in reversed(rows):
        cell = f"{share:.1f}%"
        end = m.end("cpu")
        if out[end:end + 1] == "%":
            end += 1  # consume the raw value's trailing percent sign
        out = out[:m.start("cpu")] + cell + out[end:]
    out = out.replace("CPU%", "CPU% (of machine)", 1)
    raws = ", ".join(f"{m.group('name')} raw {cpu:g}%" for m, cpu, _ in rows)
    out += (f"\nCPU% is normalized to the whole machine (all {processors} "
            f"logical processors; 100% = every core fully busy). Raw "
            f"per-core aggregates (the service's own values): {raws}.")
    return out


def _unavailable(exc: Exception) -> str:
    return (f"error:windows-mcp-lane-unavailable — the Windows-MCP "
            f"service ({BRIDGE_SSE_URL}) is unreachable "
            f"({exc.__class__.__name__}); recover with {_RECOVERY}")


async def call_tool(tool: str, args: dict, conversation_id: str,
                    audit: HermesAudit | None = None, *,
                    include_images: bool = False,
                    consent_attempts: int = 8) -> dict:
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
    if (not isinstance(consent_attempts, int)
            or isinstance(consent_attempts, bool)
            or not 1 <= consent_attempts <= 8):
        reason = "rejected: consent_attempts must be an integer in 1..8"
        if audit:
            audit.write_attempt(decision="blocked", operation=_op(tool),
                                normalized_path=None, allowed_root="",
                                reason=reason,
                                conversation_id=conversation_id,
                                duration_s=time.monotonic() - t0)
        return {"status": "blocked", "reason": reason}
    try:
        async with sse_client(BRIDGE_SSE_URL, headers=_headers()) \
                as (read, write), \
                ClientSession(read, write) as session:
                await session.initialize()
                # USER_CONTROL (the consent-WAIT protocol, gateway pattern
                # "retries USER_CONTROL consent waits"): the service returns
                # wait_seconds for the desktop user to approve — wait and
                # retry, bounded; a wait that never resolves is an honest
                # refusal, never a hang
                res = None
                text = ""
                # open-the-installed-programs-applet (2026-11-16): the
                # service yields to the desktop user (USER_CONTROL) — a
                # safety guard, but a chat user is ALWAYS active just after
                # typing; 4 attempts (~32 s) often wasn't enough. The default
                # 8 attempts (~64 s) fits the 300 s turn budget; callers may
                # choose a smaller bound without changing the legacy default.
                for _consent_attempt in range(consent_attempts):
                    res = await session.call_tool(tool, args)
                    text = "\n".join(getattr(c, "text", "")
                                     for c in res.content
                                     if getattr(c, "text", None))
                    if res.isError:
                        wait = _user_control_wait(text)
                        if wait is not None:
                            await asyncio.sleep(min(wait, 15.0))
                            continue
                    break
                if res.isError:
                    if _user_control_wait(text) is not None:
                        # the retries exhausted with the deferral still
                        # pending — the desktop user stayed active
                        envelope = {"status": "blocked", "reason": _DEFERRAL}
                        decision = "blocked"
                    elif classify_refusal(text):
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
                if include_images:
                    try:
                        captured = _extract_image(res.content)
                    except (TypeError, ValueError) as exc:
                        envelope = {
                            "status": "error",
                            "reason": f"error:windows-mcp-image — {exc}"}
                        if audit:
                            audit.write_attempt(
                                decision="error", operation=_op(tool),
                                normalized_path=None, allowed_root="",
                                reason=envelope["reason"],
                                conversation_id=conversation_id,
                                duration_s=time.monotonic() - t0)
                        return envelope
                    for field in ("data", "logs"):
                        value = getattr(res, field, None)
                        if value is not None:
                            envelope[field] = value
                    envelope["images"] = [captured]
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
    the given sort, genuine output relayed. CPU values are presented on
    both scales (the-value-of-cpu-is-impossibel, 2026-11-14): the
    service's raw per-core aggregate plus the '(x% of machine)' share,
    when the host's logical-processor count is known."""
    out = await call_tool("Process",
                          {"mode": "list", "sort_by": sort_by,
                           "limit": limit},
                          conversation_id, audit)
    if out.get("status") == "ok":
        out["text"] = render_cpu_scale(out.get("text", ""),
                                       machine_processors())
    return out
