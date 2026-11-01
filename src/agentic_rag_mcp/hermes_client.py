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