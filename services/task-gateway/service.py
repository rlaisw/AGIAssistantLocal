"""Spec 038 — the task-gateway service (Windows host, 127.0.0.1:8080).

Stdlib-only (Constitution III): three endpoints + job status, a job table
with append-only JSONL rows, and a curated tier-1 script set. The tier-2
repair catalog is bounded (~120 s per repair, honest timeout). Structured
JSON on every path — this is the CONTRACT the sidecar client pins.

Start:  python service.py            (or run_service.cmd via Scheduled Task)
Probe:  curl http://127.0.0.1:8080/api/healthz
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

JOBS_FILE = Path("C:/ProgramData/agentic-rag/task-gateway/jobs.jsonl")
TIER2_TIMEOUT_S = 120.0

# tier-1 quick-fix catalog: safe, fast, read-repair class (research R1 —
# curated, NOT a general script-runner)
TIER1_SCRIPTS: dict[str, list[str]] = {
    "print": [
        "Restart-Service Spooler -ErrorAction SilentlyContinue",
        "Get-Service Spooler | Select-Object Status",
    ],
    "general": [
        "Get-Service | Where-Object {$_.StartType -eq 'Automatic' -and $_.Status -ne 'Running'} | Select-Object -First 5 Name,Status",
    ],
    "office": [
        "Get-Process WINWORD,EXCEL,POWERPNT -ErrorAction SilentlyContinue | Select-Object Name,Id",
    ],
}

# tier-2 repair catalog: repair-class, integrity-SAFE (the never-list class
# lives in the SIDECAR gate; this catalog only offers what passes it)
TIER2_REPAIRS: dict[str, dict[str, str]] = {
    "general": {
        "repair_name": "system_file_check",
        "repair_text": "sfc /scannow",
    },
    "component": {
        "repair_name": "component_store_repair",
        "repair_text": "DISM /Online /Cleanup-Image /RestoreHealth",
    },
    "print": {
        "repair_name": "system_file_check",
        "repair_text": "sfc /scannow",
    },
}

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _ps(cmds: list[str], timeout_s: float) -> dict:
    """Run a bounded PowerShell script batch; structured result only."""
    try:
        proc = subprocess.run(  # noqa: PLW1510 — returncode IS the check
            ["powershell", "-NoProfile", "-NonInteractive",
             "-Command", "; ".join(cmds)],
            capture_output=True, text=True, timeout=timeout_s)
        return {"ok": proc.returncode == 0,
                "output": (proc.stdout or proc.stderr or "")[:2000]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"timed out after {timeout_s}s"}


def _append_job_row(job: dict) -> None:
    JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(JOBS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(job, ensure_ascii=False) + "\n")


def _job_transition(job_id: str, **fields) -> None:
    with JOBS_LOCK:
        JOBS[job_id].update(fields)
        row = dict(JOBS[job_id])
    _append_job_row(row)


def _run_install(job_id: str, version: str, channel: str) -> None:
    _job_transition(job_id, status="running",
                    detail="Office install starting (ODT/winget class)")
    # the actual install is ODT/winget-configured outside this service's
    # scope; the service runs the configured installer command bounded
    result = _ps([("winget install --id Microsoft.Office "
                   "--source winget --accept-package-agreements "
                   "--accept-source-agreements --silent")],
                timeout_s=1800.0)
    if result["ok"]:
        _job_transition(job_id, status="completed",
                        detail="Office install completed", ended_at=_now())
    else:
        _job_transition(job_id, status="failed",
                        detail=result["output"][:500], ended_at=_now())


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


class Handler(BaseHTTPRequestHandler):
    server_version = "task-gateway/1.0"

    def log_message(self, fmt, *args):  # quiet — JSONL is the record
        pass

    def _json(self, code: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/healthz":
            return self._json(200, {"status": "ok"})
        if self.path.startswith("/api/helpdesk/job/"):
            job_id = self.path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
            if not job:
                return self._json(404, {"error": f"unknown job {job_id}"})
            return self._json(200, job)
        return self._json(404, {"error": "unknown endpoint"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "malformed JSON body"})
        if self.path == "/api/helpdesk/tier1":
            return self._tier1(payload)
        if self.path == "/api/helpdesk/tier2":
            return self._tier2(payload)
        if self.path == "/api/office/install":
            return self._install(payload)
        return self._json(404, {"error": "unknown endpoint"})

    def _tier1(self, payload: dict) -> None:
        issue_type = str(payload.get("issue_type") or "general")
        cmds = TIER1_SCRIPTS.get(issue_type, TIER1_SCRIPTS["general"])
        result = _ps(cmds, timeout_s=30.0)
        actions = [{"name": cmd.split()[0] if cmd.split() else "script",
                     "ok": result["ok"],
                     "summary": result["output"][:300]}
                    for cmd in cmds]
        repair = TIER2_REPAIRS.get(issue_type)
        recommendation = "tier2" if (not result["ok"] and repair) else "none"
        body = {"recommendation": recommendation, "actions": actions,
                "detail": result["output"][:300]}
        if repair:
            body.update(repair)
        return self._json(200, body)

    def _tier2(self, payload: dict) -> None:
        issue_type = str(payload.get("issue_type") or "general")
        repair = TIER2_REPAIRS.get(issue_type)
        if not repair:
            return self._json(404, {"error": f"no tier-2 repair for {issue_type}"})
        # NOTE: the never-list + confirmation live in the SIDECAR lane
        # (R3/R2) — the service runs only what the catalog names, bounded
        result = _ps([repair["repair_text"]], timeout_s=TIER2_TIMEOUT_S)
        return self._json(200, {
            "repair_name": repair["repair_name"],
            "repair_text": repair["repair_text"],
            "result": "ok" if result["ok"] else "failed",
            "detail": result["output"][:500]})

    def _install(self, payload: dict) -> None:
        version = str(payload.get("version") or "365")
        channel = str(payload.get("channel") or "Current")
        job_id = uuid.uuid4().hex[:12]
        job = {"job_id": job_id, "kind": "office-install", "status": "queued",
               "detail": f"queued ({version}, {channel})",
               "started_at": _now()}
        with JOBS_LOCK:
            JOBS[job_id] = job
        _append_job_row(dict(job))
        threading.Thread(target=_run_install,
                          args=(job_id, version, channel),
                          daemon=True).start()
        return self._json(200, {"job_id": job_id, "status": "queued"})


def main(host: str = "127.0.0.1", port: int = 8080) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"task-gateway listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()