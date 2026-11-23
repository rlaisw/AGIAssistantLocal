"""Fixed Windows system-health check integration."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

HEALTH_ACTION_ID = "system_health_check"
HOST_SCRIPT_PATH = r"C:\ProgramData\agentic-rag\health\health-check.ps1"
HOST_REPORT_DIR = r"C:\ProgramData\agentic-rag\health\reports"
HOST_REPORT_DIR_WSL = "/mnt/c/ProgramData/agentic-rag/health/reports"
HOST_USER_REPORT_PATH = r"%LOCALAPPDATA%\Temp\selfcheck.html"
HEALTH_SCRIPT_SHA256 = "8045e5438e6c5fad3bacb12f468a4a3e9c8fc5840480e9e93948f5fac3f1ee5e"
WRAPPER_TIMEOUT_S = 120
HEALTH_ACTION_BUDGET_S = 180.0
MAX_JSON_BYTES = 5 * 1024 * 1024
MAX_HTML_BYTES = 5 * 1024 * 1024
_RUN_ID = re.compile(r"[0-9a-f]{32}")
_STATUS = frozenset({"pass", "warn", "fail", "info", "skip"})
_BANNED_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "api_key",
    "apikey",
    "mfa",
)
_ACTIVE_HTML = re.compile(
    r"<\s*(script|iframe|object|embed|form|base|link)\b|\son[a-z]+\s*=|"
    r"javascript:|data:text/html|http-equiv\s*=\s*['\"]?refresh",
    re.IGNORECASE,
)


def validate_run_id(run_id: Any) -> None:
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError("invalid health run id")


def build_health_wrapper(run_id: str) -> str:
    validate_run_id(run_id)
    template = r'''
$ErrorActionPreference='Stop'
$script='__SCRIPT__'
$expected='__SHA__'
$json='__DIR__\__RUN__.json'
$html='__DIR__\__RUN__.html'
$userRoot=$env:LOCALAPPDATA
if (-not $userRoot -and $env:USERPROFILE) { $userRoot=Join-Path $env:USERPROFILE 'AppData\Local' }
if (-not $userRoot) { $userRoot='C:\Temp' }
$userHtml=Join-Path $userRoot 'Temp\selfcheck.html'
$actual=(Get-FileHash -LiteralPath $script -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) {
    $payload=@{status='error';reason='hash-mismatch'}|ConvertTo-Json -Compress
    Write-Output ('MCP_ACTION_JSON:'+[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload)))
    exit 3
}
$psi=[System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName='powershell.exe'
$psi.Arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$script+'" -NoReliabilityMonitor -ReportPath "'+$html+'"'
$psi.UseShellExecute=$false
$psi.RedirectStandardOutput=$true
$psi.RedirectStandardError=$true
$p=[System.Diagnostics.Process]::new()
$p.StartInfo=$psi
$null=$p.Start()
$stdout=$p.StandardOutput.ReadToEndAsync()
$stderr=$p.StandardError.ReadToEndAsync()
if (-not $p.WaitForExit(__TIMEOUT__000)) {
    try { $p.Kill() } catch { }
    $payload=@{status='error';reason='timeout';runId='__RUN__'}|ConvertTo-Json -Compress
    Write-Output ('MCP_ACTION_JSON:'+[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload)))
    exit 4
}
$out=$stdout.Result
$err=$stderr.Result
[System.IO.File]::WriteAllText($json,$out,[System.Text.UTF8Encoding]::new($false))
$jsonOk=Test-Path -LiteralPath $json
$htmlOk=Test-Path -LiteralPath $html
$userHtmlOk=$false
if ($htmlOk) {
    try {
        $null=New-Item -ItemType Directory -Force -Path (Split-Path -Parent $userHtml)
        Copy-Item -LiteralPath $html -Destination $userHtml -Force
        $userHtmlOk=Test-Path -LiteralPath $userHtml
    } catch { }
}
$payload=@{status=$(if($jsonOk -and $htmlOk){'ok'}else{'error'});runId='__RUN__';exitCode=$p.ExitCode;json=$jsonOk;html=$htmlOk;userHtml=$userHtmlOk;userHtmlPath=$userHtml}|ConvertTo-Json -Compress
Write-Output ('MCP_ACTION_JSON:'+[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload)))
exit $p.ExitCode
'''
    return (
        template.replace("__SCRIPT__", HOST_SCRIPT_PATH)
        .replace("__SHA__", HEALTH_SCRIPT_SHA256)
        .replace("__DIR__", HOST_REPORT_DIR)
        .replace("__TIMEOUT__", str(WRAPPER_TIMEOUT_S))
        .replace("__RUN__", run_id)
        .strip()
    )


def _read_bounded(path: Path, max_bytes: int) -> bytes:
    if not path.is_file():
        raise ValueError("health artifact missing")
    size = path.stat().st_size
    if size <= 0 or size > max_bytes:
        raise ValueError("health artifact size invalid")
    data = path.read_bytes()
    if b"\x00" in data:
        raise ValueError("health artifact contains NUL")
    return data


def _report_root(report_root: Path | str | None) -> Path:
    return Path(report_root) if report_root is not None else Path(HOST_REPORT_DIR_WSL)


def read_health_json(run_id: str, report_root: Path | str | None = None) -> dict:
    validate_run_id(run_id)
    data = _read_bounded(_report_root(report_root) / f"{run_id}.json", MAX_JSON_BYTES)
    try:
        payload = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("health JSON invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("health JSON must be an object")  # noqa: TRY004
    return payload


def read_health_html(run_id: str, report_root: Path | str | None = None) -> bytes:
    validate_run_id(run_id)
    html_bytes = _read_bounded(
        _report_root(report_root) / f"{run_id}.html", MAX_HTML_BYTES
    )
    html_text = html_bytes.decode("utf-8-sig", errors="strict")
    lowered = html_text.casefold()
    if (
        "<html" not in lowered
        or "</html>" not in lowered
        or _ACTIVE_HTML.search(html_text)
    ):
        raise ValueError("health HTML invalid")
    return html_bytes


def read_health_artifacts(
    run_id: str, report_root: Path | str | None = None
) -> tuple[dict, bytes]:
    return read_health_json(run_id, report_root), read_health_html(run_id, report_root)


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize(child)
            for key, child in value.items()
            if not any(part in str(key).casefold() for part in _BANNED_KEY_PARTS)
        }
    if isinstance(value, list):
        return [_sanitize(child) for child in value]
    return value


def normalize_health_payload(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("health payload must be an object")  # noqa: TRY004
    checks_in = payload.get("checks")
    if not isinstance(checks_in, list):
        raise ValueError("health checks must be a list")  # noqa: TRY004

    checks: list[dict] = []
    for raw in checks_in:
        if not isinstance(raw, dict):
            raise ValueError("health check must be an object")  # noqa: TRY004
        area = raw.get("area")
        name = raw.get("name")
        status = raw.get("status")
        detail = raw.get("detail")
        if not isinstance(area, str) or not isinstance(name, str) or not isinstance(detail, str):
            raise ValueError("health check fields invalid")  # noqa: TRY004
        if not isinstance(status, str) or status.casefold() not in _STATUS:
            raise ValueError("health check status invalid")
        check = {
            "area": area[:80],
            "name": name[:120],
            "status": status.casefold(),
            "detail": detail[:1000],
        }
        if isinstance(raw.get("recommendation"), str):
            check["recommendation"] = raw["recommendation"][:500]
        checks.append(check)

    counts = {status: 0 for status in ("pass", "warn", "fail", "info", "skip")}
    for check in checks:
        counts[check["status"]] += 1

    status = (
        "fail"
        if counts["fail"]
        else "warn"
        if counts["warn"]
        else "pass"
        if counts["pass"]
        else "unknown"
    )
    score = max(0, min(100, 100 - 15 * counts["fail"] - 5 * counts["warn"]))
    reliability = _sanitize(payload.get("reliability") or {})
    events = _sanitize(payload.get("events") or {})
    inventory = _sanitize(payload.get("inventory") or {})

    applicable = counts["pass"] + counts["warn"] + counts["fail"]
    reliability_available = isinstance(reliability, dict) and reliability.get("available") is True
    if not applicable:
        confidence = "low"
    elif (
        counts["info"] == 0
        and counts["skip"] == 0
        and reliability_available
    ):
        confidence = "high"
    else:
        confidence = "reduced"

    return {
        "status": status,
        "score": score,
        "counts": counts,
        "confidence": confidence,
        "checks": checks,
        "inventory": inventory,
        "events": events,
        "reliability": reliability,
    }


def build_cleanup_script(run_id: str) -> str:
    validate_run_id(run_id)
    return (
        "$ErrorActionPreference='SilentlyContinue'\n"
        f"$root='{HOST_REPORT_DIR}'\n"
        f"Remove-Item -LiteralPath (Join-Path $root '{run_id}.json') -Force\n"
        f"Remove-Item -LiteralPath (Join-Path $root '{run_id}.html') -Force\n"
        "'MCP_ACTION_CLEANUP:ok'"
    )
