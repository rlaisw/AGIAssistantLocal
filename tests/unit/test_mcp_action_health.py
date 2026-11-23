"""Unit: system health host script, wrapper, artifacts, normalization (spec 048, T005).

Every host interaction is mocked or reduced to a string/path assertion. Artifact
reads use a tmp report root; no Windows host or PowerShell process is executed.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from agentic_rag_mcp.mcp_action import health

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "windows" / "health-check.ps1"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "system_health"
RUN_ID = "0123456789abcdef0123456789abcdef"
RUN_ID_2 = "fedcba9876543210fedcba9876543210"

FORBIDDEN_SCRIPT = (
    r"Start-Process",
    r"\bSet-[A-Za-z]",
    r"\bNew-Item\b",
    r"\bRemove-[A-Za-z]",
    r"Invoke-CimMethod",
    r"\breg(?:\.exe)?\s+add\b",
    r"\brunas\b",
    r"Get-Credential",
)


def _valid_payload() -> dict:
    return json.loads((FIXTURES / "valid_health.json").read_text(encoding="utf-8"))


def _valid_html() -> bytes:
    return (FIXTURES / "valid_report.html").read_bytes()


def _write_pair(
    root: Path,
    payload: dict | None = None,
    html: bytes | str | None = None,
    run_id: str = RUN_ID,
    json_encoding: str = "utf-8",
    html_encoding: str = "utf-8",
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = _valid_payload() if payload is None else payload
    html = _valid_html() if html is None else html
    (root / f"{run_id}.json").write_bytes(json.dumps(payload).encode(json_encoding))
    if isinstance(html, str):
        html = html.encode(html_encoding)
    (root / f"{run_id}.html").write_bytes(html)


def _keys(value) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            found.add(str(key).lower())
            found |= _keys(child)
    elif isinstance(value, list):
        for child in value:
            found |= _keys(child)
    return found


def test_pinned_hash_matches_repo_script():
    digest = hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest()
    assert health.HEALTH_SCRIPT_SHA256 == digest


def test_constants_are_fixed_and_bounded():
    assert health.HOST_SCRIPT_PATH == r"C:\ProgramData\agentic-rag\health\health-check.ps1"
    assert health.HOST_REPORT_DIR_WSL == "/mnt/c/ProgramData/agentic-rag/health/reports"
    assert health.WRAPPER_TIMEOUT_S == 120


def test_active_html_guard_ignores_compound_words_but_blocks_handlers():
    assert not health._ACTIVE_HTML.search(
        "<html><body>sessionType=Local <span data-x=1>ok</span></body></html>"
    )
    assert health._ACTIVE_HTML.search(
        '<html><body><img src="x" onclick="evil()"></body></html>'
    )


def test_repo_script_is_read_only():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    allowed_report_or_display = (
        "perfmon.exe",  # Reliability Monitor display only
        "New-Item -ItemType Directory -Path $dir -Force",  # report output directory
        "Set-Content -Path $Path -Value $sb.ToString() -Encoding UTF8",  # report file
    )
    found = []
    for line in text.splitlines():
        if any(marker in line for marker in allowed_report_or_display):
            continue
        for pattern in FORBIDDEN_SCRIPT:
            if re.search(pattern, line):
                found.append((pattern, line.strip()))
    assert found == []


@pytest.mark.parametrize("run_id", [RUN_ID, RUN_ID_2])
def test_validate_run_id_accepts_lowercase_32_hex(run_id):
    health.validate_run_id(run_id)


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        "0" * 31,
        "0" * 33,
        "A" * 32,
        "g" * 32,
        "../" + "0" * 29,
        "0" * 31 + "\n",
        "0" * 31 + " ",
        None,
        1234,
    ],
)
def test_validate_run_id_rejects_everything_else(run_id):
    with pytest.raises(ValueError):
        health.validate_run_id(run_id)


def test_wrapper_is_fixed_hash_checked_and_bounded():
    wrapper = health.build_health_wrapper(RUN_ID)
    assert isinstance(wrapper, str)
    assert health.HOST_SCRIPT_PATH in wrapper
    assert health.HEALTH_SCRIPT_SHA256 in wrapper
    assert "Get-FileHash" in wrapper
    assert "SHA256" in wrapper
    assert "-NoReliabilityMonitor" in wrapper
    assert "-File" in wrapper
    assert str(health.WRAPPER_TIMEOUT_S) in wrapper
    assert "WaitForExit" in wrapper
    assert "Kill" in wrapper or "kill" in wrapper
    assert "MCP_ACTION_JSON:" in wrapper
    assert "reports" in wrapper
    assert f"{RUN_ID}.json" in wrapper
    assert f"{RUN_ID}.html" in wrapper
    assert "$env:LOCALAPPDATA" in wrapper
    assert "$env:USERPROFILE" in wrapper
    assert "selfcheck.html" in wrapper
    assert "Copy-Item" in wrapper


def test_wrapper_has_no_model_interpolation():
    wrapper = health.build_health_wrapper(RUN_ID)
    other = health.build_health_wrapper(RUN_ID_2)
    assert wrapper != other
    assert RUN_ID in wrapper and RUN_ID_2 in other
    assert RUN_ID_2 not in wrapper
    assert "{{" not in wrapper and "}}" not in wrapper
    assert "$args" not in wrapper
    with pytest.raises(ValueError):
        health.build_health_wrapper(RUN_ID + "'; Remove-Item C:\\temp -Recurse; #")


def test_read_health_artifacts_valid_fixture(tmp_path):
    _write_pair(tmp_path)
    payload, html = health.read_health_artifacts(RUN_ID, report_root=tmp_path)
    assert payload == _valid_payload()
    assert html == _valid_html()


def test_read_health_artifacts_accepts_utf8_bom(tmp_path):
    _write_pair(tmp_path, json_encoding="utf-8-sig", html_encoding="utf-8-sig")
    payload, html = health.read_health_artifacts(RUN_ID, report_root=tmp_path)
    assert payload == _valid_payload()
    assert html.lstrip(b"\xef\xbb\xbf").startswith(b"<!DOCTYPE html>")


def test_read_health_artifacts_missing_files(tmp_path):
    with pytest.raises((ValueError, OSError)):
        health.read_health_artifacts(RUN_ID, report_root=tmp_path)


def test_read_health_artifacts_missing_html(tmp_path):
    _write_pair(tmp_path)
    (tmp_path / f"{RUN_ID}.html").unlink()
    with pytest.raises((ValueError, OSError)):
        health.read_health_artifacts(RUN_ID, report_root=tmp_path)


def test_read_health_artifacts_rejects_malformed_json(tmp_path):
    malformed = (FIXTURES / "malformed_health.json").read_bytes()
    _write_pair(tmp_path, html=_valid_html())
    (tmp_path / f"{RUN_ID}.json").write_bytes(malformed)
    with pytest.raises(ValueError):
        health.read_health_artifacts(RUN_ID, report_root=tmp_path)


def test_read_health_artifacts_rejects_nul_bytes(tmp_path):
    _write_pair(tmp_path)
    (tmp_path / f"{RUN_ID}.json").write_bytes(b'{"checks": []}\x00')
    with pytest.raises(ValueError):
        health.read_health_artifacts(RUN_ID, report_root=tmp_path)

    _write_pair(tmp_path)
    (tmp_path / f"{RUN_ID}.html").write_bytes(_valid_html().replace(b"</body>", b"\x00</body>"))
    with pytest.raises(ValueError):
        health.read_health_artifacts(RUN_ID, report_root=tmp_path)


def test_read_health_artifacts_rejects_oversized_json(tmp_path):
    oversized = {"checks": [], "pad": "x" * (6 * 1024 * 1024)}
    _write_pair(tmp_path, payload=oversized)
    with pytest.raises(ValueError):
        health.read_health_artifacts(RUN_ID, report_root=tmp_path)


def test_read_health_artifacts_rejects_oversized_html(tmp_path):
    oversized = b"<!DOCTYPE html><html><body>" + b"x" * (5 * 1024 * 1024 + 1)
    _write_pair(tmp_path, html=oversized)
    with pytest.raises(ValueError):
        health.read_health_artifacts(RUN_ID, report_root=tmp_path)


@pytest.mark.parametrize(
    "html",
    [
        b"not html",
        b"<html><body><p>unterminated",
        b"<!DOCTYPE html><html><body><script>alert(1)</script></body></html>",
    ],
)
def test_read_health_artifacts_rejects_invalid_html(tmp_path, html):
    _write_pair(tmp_path, html=html)
    with pytest.raises(ValueError):
        health.read_health_artifacts(RUN_ID, report_root=tmp_path)


def test_read_health_artifacts_rejects_bad_run_id_before_reading(tmp_path):
    with pytest.raises(ValueError):
        health.read_health_artifacts("../../etc/passwd", report_root=tmp_path)


def test_normalization_recomputes_and_ignores_host_claims():
    payload = _valid_payload()
    payload["overall"] = "pass"
    payload["score"] = 100
    result = health.normalize_health_payload(payload)

    assert result["status"] == "fail"
    assert result["score"] == 80
    assert result["counts"] == {"pass": 1, "warn": 1, "fail": 1, "info": 1, "skip": 1}
    assert result["confidence"] == "reduced"
    assert {check["status"] for check in result["checks"]} == {
        "pass",
        "warn",
        "fail",
        "info",
        "skip",
    }
    assert result["inventory"] == payload["inventory"]
    assert result["events"] == payload["events"]
    assert result["reliability"] == payload["reliability"]


def test_normalization_high_confidence_for_all_pass_with_reliability():
    payload = {
        "checks": [
            {"area": "System", "name": "OS", "status": "PASS", "detail": "ok"},
            {"area": "Disk", "name": "FreeSpaceC", "status": "PASS", "detail": "ok"},
        ],
        "reliability": {"available": True, "summary": {}},
        "events": {"available": True, "recent": []},
        "inventory": {"computer": {"name": "TEST-PC"}},
    }
    result = health.normalize_health_payload(payload)
    assert result["status"] == "pass"
    assert result["score"] == 100
    assert result["counts"] == {"pass": 2, "warn": 0, "fail": 0, "info": 0, "skip": 0}
    assert result["confidence"] == "high"


def test_normalization_skips_never_become_pass():
    payload = {
        "checks": [
            {"area": "Security", "name": "BitLocker", "status": "SKIP", "detail": "restricted"},
            {"area": "System", "name": "FaultyDevices", "status": "SKIP", "detail": "unavailable"},
        ],
        "reliability": {"available": True},
        "events": {"available": False},
        "inventory": {},
    }
    result = health.normalize_health_payload(payload)
    assert result["status"] == "unknown"
    assert result["counts"] == {"pass": 0, "warn": 0, "fail": 0, "info": 0, "skip": 2}
    assert result["confidence"] == "low"


def test_normalization_reliability_unavailable_is_explicit():
    payload = json.loads((FIXTURES / "missing_reliability.json").read_text(encoding="utf-8"))
    result = health.normalize_health_payload(payload)
    assert result["status"] == "pass"
    assert result["counts"]["pass"] == 1
    assert result["reliability"]["available"] is False
    assert result["confidence"] == "reduced"


@pytest.mark.parametrize(
    "payload",
    [
        {"checks": "not-a-list"},
        {"checks": [1]},
        {"checks": [{"area": "Disk", "name": "FreeSpaceC", "status": "BOGUS"}]},
        {"checks": [{"area": "Disk", "name": "FreeSpaceC"}]},
        ["not", "an", "object"],
        "not-an-object",
    ],
)
def test_normalization_rejects_malformed_types(payload):
    with pytest.raises(ValueError):
        health.normalize_health_payload(payload)


def test_normalization_drops_credentials_but_keeps_owner_approved_fields():
    payload = _valid_payload()
    payload["inventory"]["user"].update(
        {"password": "hunter2", "mfa_code": "123456", "token": "secret-token"}
    )
    payload["inventory"]["api_key"] = "secret-key"
    payload["reliability"]["credential"] = "secret-credential"
    payload["checks"][0]["password"] = "hunter2"

    result = health.normalize_health_payload(payload)
    keys = _keys(result)
    for banned in ("password", "passwd", "secret", "token", "credential", "api_key", "apikey", "mfa"):
        assert not any(banned in key for key in keys)
    rendered = json.dumps(result)
    for secret in ("hunter2", "123456", "secret-token", "secret-key", "secret-credential"):
        assert secret not in rendered

    inventory = result["inventory"]
    assert inventory["user"]["login"] == "TEST\\user"
    assert inventory["user"]["email"] == "user@example.test"
    assert inventory["computer"]["ipAddress"] == "10.0.0.10"


def test_cleanup_script_removes_only_exact_run_artifacts():
    script = health.build_cleanup_script(RUN_ID)
    assert isinstance(script, str)
    assert "Remove-Item" in script
    assert "reports" in script
    assert "-Recurse" not in script
    assert "*" not in script
    names = set(re.findall(r"[A-Za-z0-9_-]+\.(?:json|html)\b", script))
    assert names == {f"{RUN_ID}.json", f"{RUN_ID}.html"}
    with pytest.raises(ValueError):
        health.build_cleanup_script(RUN_ID + "\nRemove-Item C:\\ -Recurse")
