"""Spec 041 — the tier-1 bounded settings launcher (FR-002).

Open any reviewed Control Panel applet or Settings page from chat:
targets come from the reviewed inventory only (targets.py); unknown or
ambiguous targets ask back with the list; one target per request; the
launcher passes NOTHING beyond the identifier to the service. The
launcher itself is nondestructive — a window opens; nothing changes
until a human acts inside it."""

from __future__ import annotations

import time

from ..hermes_audit import HermesAudit
from .client import call_tool
from .targets import resolve_target


async def open_settings(target_text: str, conversation_id: str,
                         audit: HermesAudit | None = None) -> dict:
    """Open one settings surface. Audits every attempt as
    `windows-mcp-open` (executed/blocked/error)."""
    t0 = time.monotonic()
    res = resolve_target(target_text)
    if res["status"] != "ok":
        if audit:
            audit.write_attempt(decision="blocked", operation="windows-mcp-open",
                                normalized_path=None, allowed_root="",
                                reason=res["reason"],
                                conversation_id=conversation_id,
                                duration_s=time.monotonic() - t0)
        return {"status": "blocked", "reason": res["reason"]}
    target = res["target"]
    # Start-Process through cmd is the robust form on the service's
    # executor (plain `control`/`start` resolve but don't spawn the
    # window; verified live 2026-11-15 — mmc appears in session 2 only
    # via this form)
    command = (f"Start-Process cmd.exe -ArgumentList '/c','control',"
               f"'{target['identifier']}'"
               if target["kind"] == "cpl"
               else f"Start-Process cmd.exe -ArgumentList '/c','start',"
               f"'ms-settings:{target['identifier']}'")
    out = await call_tool("PowerShell", {"command": command, "timeout": 20},
                          conversation_id, audit=None)
    ok = out.get("status") == "ok"
    if audit:
        audit.write_attempt(
            decision="executed" if ok else "error",
            operation="windows-mcp-open", normalized_path=None,
            allowed_root="",
            outcome=f"opened {res['display_name']}: {command}"
            if ok else out.get("reason", "")[:250],
            reason=None if ok else out.get("reason"),
            conversation_id=conversation_id,
            duration_s=time.monotonic() - t0)
    if ok:
        return {"status": "ok", "target": res["display_name"],
                "command": command}
    return out
