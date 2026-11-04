"""Spec 028 — thin stateless client for the Hermes gateway's /v1/responses
(research R1/R4). One call = one gated task executed by the local agent; no
conversation chaining (per-conversation isolation holds by statelessness).
Failures map to honest error envelopes — never fabricated results.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import Config

CONTAINMENT_INSTRUCTIONS = (
    "You are executing a single local file task on this host. Operate ONLY on "
    "the paths stated in the task; create folders, write, read, and list files "
    "only — never delete, rename, move, or bulk-clear anything, and never "
    "start other programs. When the task is done, report exactly what was "
    "created/read/listed with full Windows-style paths. If any part of the "
    "task is impossible or ambiguous, report that honestly instead of acting."
)

# Spec 030 — the Office lane's system prompt (research R3/R6, contract §3).
OFFICE_INSTRUCTIONS = (
    "You are executing one Office task on the user's Windows computer using "
    "your OfficeMCP tools (Launch, RunPython for the steps, the availability "
    "and file-existence queries, Visible). Office apps: Word, Excel, "
    "PowerPoint, Outlook. Rules: save/read at any location the user's task "
    "names (any drive, any folder) and at the default work folder when none "
    "is named; write literal content only — never "
    "store formulas, macros, DDE, or scripts in documents; NEVER use Quit, "
    "ScreenShot, Speak, Beep, DownloadImage, or Demonstrate for this task; "
    "never apply formatting (bold, fonts, colors, number formats, column "
    "widths) — v1 writes literal content only and the gate refuses "
    "formatting requests; "
    "do NOT use the IsFileExists tool — it is broken in OfficeMCP v1.0.5 "
    "and always raises (verify files by opening them through the app "
    "instead); "
    "SESSION-DEGRADATION RULE (mandatory): if 2 or more consecutive RunPython "
    "calls return only the default echo (your code argument was dropped — "
    "the MCP session to OfficeMCP is stale), STOP retrying immediately and "
    "end with 'TASK: FAILED — OfficeMCP session stale; recovery: hermes "
    "mcp remove OfficeMCP then yes | hermes mcp add OfficeMCP --url "
    "http://127.0.0.1:8888/sse then hermes gateway restart -y --detach'. "
    "Do NOT fall back to PowerShell for the task steps and do NOT burn the "
    "turn on further retries. "
    "NEVER use terminal, shell, or PowerShell commands for VERIFICATION — "
    "the gateway's consent gate holds them for interactive approval that "
    "API-server turns can never give, burning the turn budget. Always "
    "verify by reading through the Office application itself (open the "
    "file, read the cell, check the folder in the running app). "
    "NEVER send an email unless the directive explicitly says "
    "'SEND PENDING DRAFT <id>' — an email task composes a draft only; "
    "if the task names an EXISTING file, update it and report honestly "
    "that an existing file was replaced; if the application holds unsaved "
    "interactive changes for it, ASK BACK before writing — never silently "
    "discard the user's open edits; never elevate privileges — if the OS "
    "denies a write, relay the exact operating-system error in your step "
    "report; "
    "check RunningApps FIRST and attach to the already-running application "
    "instance — NEVER launch a second instance of an app that is already "
    "running (a second Outlook launch blocks on Windows with 'only one "
    "version of Outlook can run at a time' and hangs the task); launch the "
    "application only when it is truly not running. RunningApps may return "
    "INCOMPLETE data on a degraded MCP session — if Launch returns success "
    "but a dialog popped up or the app window doesn't match the request, "
    "the app was probably already running: try Dispatch/GetComObject to "
    "attach to the existing instance instead of retrying Launch. "
    "leave the application open showing the result. "
    "Report honestly, ending EVERY executed step with "
    "exactly 'STEP <n>: <operation> OK — <detail>' or "
    "'STEP <n>: <operation> FAILED — <detail>', then 'ACTIVE FILE: "
    "<windows-path>' after document work, 'DRAFT ID: <entryID>' after "
    "composing an email, and finish with exactly 'TASK: COMPLETED' (every "
    "step really happened), 'TASK: PARTIAL' (some steps failed — name "
    "them), or 'TASK: FAILED'. Never emit TASK: COMPLETED unless every "
    "requested step truly succeeded, and never claim a step you did not "
    "perform."
)

# Spec 029 — the launch lane's system prompt (research R1, contracts §3).
LAUNCH_INSTRUCTIONS = (
    "You are launching exactly one program on the user's Windows computer. "
    "Launch ONLY the target stated in the task — by its name or its full "
    "path — with NO arguments and NO command line, and never launch a "
    "script or a shortcut. If the target cannot be found or fails to start, "
    "report that honestly instead of acting. Report exactly what you "
    "observed: started fresh, already running (activated), or failed with "
    "the reason. End your report with a final line that is exactly "
    "'LAUNCH: SUCCESS' when the program started or was already running and "
    "is now active, or 'LAUNCH: FAILED: <reason>' when it did not start — "
    "the caller parses that line to decide the verdict, so never emit "
    "SUCCESS unless the program is really running."
)


def _extract_text(body: dict[str, Any]) -> str:
    # OpenAI Responses-API shape: output_text, else the output[] content chain
    if isinstance(body.get("output_text"), str) and body["output_text"]:
        return body["output_text"]
    chunks: list[str] = []
    out = body.get("output")
    if isinstance(out, list):
        for item in out:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        chunks.append(part["text"])
            elif isinstance(item.get("text"), str):
                chunks.append(item["text"])
    if chunks:
        return "\n".join(chunks)
    if isinstance(out, str) and out:
        return out
    if isinstance(body.get("message"), str):
        return body["message"]
    return ""


def run_task(cfg: Config, task: str,
             instructions: str = CONTAINMENT_INSTRUCTIONS) -> dict[str, Any]:
    """Run one gated task. Returns {"ok": True, "output": str} on success or
    {"ok": False, "error": reason-with-recovery-hint} on any failure."""
    try:
        resp = httpx.post(
            f"{cfg.hermes_api_url.rstrip('/')}/v1/responses",
            headers={"Authorization": f"Bearer {cfg.hermes_api_key}",
                     "Content-Type": "application/json"},
            json={"input": task, "instructions": instructions,
                  "store": False, "model": "hermes-agent"},
            timeout=cfg.hermes_timeout_s,
        )
    except httpx.TimeoutException:
        return {"ok": False, "error": f"error:Hermes did not finish within "
                f"{cfg.hermes_timeout_s:.0f}s — try a smaller task"}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"error:Hermes gateway unreachable at "
                f"{cfg.hermes_api_url} ({exc.__class__.__name__}) — start it with "
                f"'hermes gateway restart -y --detach' and retry"}
    if resp.status_code in (401, 403):
        return {"ok": False, "error": "error:Hermes rejected the API key — check "
                "hermes.api_key in the sidecar config matches "
                "API_SERVER_KEY in ~/.hermes/.env"}
    if resp.status_code != 200:
        return {"ok": False, "error": f"error:Hermes returned HTTP {resp.status_code}: "
                f"{resp.text[:200]}"}
    body = resp.json()
    text = _extract_text(body)
    if not text:
        return {"ok": False, "error": "error:Hermes returned an empty response — "
                "the task may not have produced output; retry or simplify"}
    return {"ok": True, "output": text}