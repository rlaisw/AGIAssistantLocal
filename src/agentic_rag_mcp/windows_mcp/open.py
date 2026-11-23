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
    # some-success-some-unsuccess (2026-11-16): three launch forms, one per
    # host process, each proven live on the service's executor —
    #   .msc  -> direct mmc.exe (the cmd/control indirection dies silently
    #            on the console session; the direct form puts the window
    #            in the visible session, verified live)
    #   .cpl  -> cmd /c control (Explorer-hosted applets; proven)
    #   page  -> cmd /c start ms-settings:<page> (Settings; proven)
    identifier = target["identifier"]
    if target["kind"] == "perfmon_rel":
        # 2026-11-22 (bug show-full-html-report-and-page-reliability-view):
        # the Control Panel ActionCenter form is the requested Reliability
        # Monitor surface; mmc perfmon.msc /rel opens a different console.
        command = ("Start-Process control.exe -ArgumentList "
                   "'/name','Microsoft.ActionCenter','/page','pageReliabilityView'")
    elif identifier.endswith(".msc"):
        command = f"Start-Process mmc.exe -ArgumentList '{identifier}'"
    elif target["kind"] == "cpl":
        command = (f"Start-Process cmd.exe -ArgumentList '/c','control',"
                   f"'{identifier}'")
    else:
        command = (f"Start-Process cmd.exe -ArgumentList '/c','start',"
                   f"'ms-settings:{identifier}'")
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
