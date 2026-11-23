"""Fixed reviewed Windows actions with structured, verified host outcomes."""

from __future__ import annotations

import base64
import json
import re
import uuid
from typing import Any

from ..windows_mcp.client import call_tool
from . import health

_ACTION_ID = "windows_default_printer"
_WORD_ACTION_ID = "word_printer_duplex"
_DUPLEX_MODES = {
    "long-edge": "TwoSidedLongEdge",
    "short-edge": "TwoSidedShortEdge",
}
_CONVERSATION_ID = "mcp-action-windows-default-printer"
_MARKER = "MCP_ACTION_JSON:"
_PAYLOAD_RE = re.compile(re.escape(_MARKER) + r"([A-Za-z0-9+/=]+)")
_MANAGED_CAVEAT = (
    "Windows manages the default printer; choosing a manual default may turn off "
    "'Let Windows manage my default printer'; the verified change may not persist."
)
_UNKNOWN_CAVEAT = (
    "Windows default-printer management is unknown; the verified change may not persist."
)


class _ActionError(Exception):
    """Internal failure whose details must not cross the public boundary."""


def _printer_name(printer: str) -> str:
    if not isinstance(printer, str):
        raise TypeError("printer must be a string")
    name = printer.strip()
    if not name or len(name) > 256 or any(c in name for c in "\0\r\n"):
        raise ValueError("invalid printer name")
    return name


def _encoded_name(printer: str) -> str:
    return base64.b64encode(_printer_name(printer).encode("utf-8")).decode("ascii")


def _build_printer_script(printer: str, execute: bool) -> str:
    encoded = _encoded_name(printer)
    execution_fields = """
    after = $null
    after_read = $false
    after_error = $null
    setter = @{ attempted = $false; 'return' = $null; error = $null }
""" if execute else ""
    mutation = """
        if ($exact.Count -eq 1) {
            $canonical = [string]$exact[0].Name
            $alreadyActive = ($null -ne $payload.before -and
                $payload.before -eq $canonical)
            if (-not $alreadyActive) {
                $payload.setter.attempted = $true
                try {
                    $outcome = Invoke-CimMethod -InputObject $exact[0] `
                        -MethodName 'SetDefaultPrinter'
                    $payload.setter.return = [int]$outcome.ReturnValue
                } catch {
                    $payload.setter.error = $_.Exception.GetType().FullName
                }
            }
        }
""" if execute else ""
    after_read = """
try {
    $afterPrinters = @(Get-CimInstance -ClassName Win32_Printer)
    $afterDefaults = @($afterPrinters | Where-Object { $_.Default -eq $true })
    if ($afterDefaults.Count -gt 1) {
        throw 'Multiple default printers reported'
    }
    if ($afterDefaults.Count -eq 1) {
        $payload.after = [string]$afterDefaults[0].Name
    }
    $payload.after_read = $true
} catch {
    $payload.after_error = $_.Exception.GetType().FullName
}
""" if execute else ""
    return r"""
$ErrorActionPreference = 'Stop'
$requestedName = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String('__PRINTER_NAME_BASE64__'))
$payload = @{
    matches = @()
    before = $null
    read_error = $null
    managed = @{ status = 'absent'; value = $null; error = $null }
__EXECUTION_FIELDS__
}
try {
    $beforePrinters = @(Get-CimInstance -ClassName Win32_Printer)
    $exact = @($beforePrinters | Where-Object {
        [string]$_.Name -eq $requestedName
    })
    $beforeDefaults = @($beforePrinters | Where-Object { $_.Default -eq $true })
    if ($beforeDefaults.Count -gt 1) {
        throw 'Multiple default printers reported'
    }
    $payload.matches = @($exact | ForEach-Object { [string]$_.Name })
    if ($beforeDefaults.Count -eq 1) {
        $payload.before = [string]$beforeDefaults[0].Name
    }
__MUTATION__
} catch {
    $payload.read_error = $_.Exception.GetType().FullName
}
__AFTER_READ__
try {
    $key = Get-ItemProperty -LiteralPath `
        'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Windows' -ErrorAction Stop
    $property = $key.PSObject.Properties['LegacyDefaultPrinterMode']
    if ($null -ne $property) {
        $payload.managed.status = 'ok'
        $payload.managed.value = [int]$property.Value
    }
} catch {
    $payload.managed.status = 'error'
    $payload.managed.error = $_.Exception.GetType().FullName
}
$json = $payload | ConvertTo-Json -Depth 6 -Compress
Write-Output ('MCP_ACTION_JSON:' +
    [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json)))
""".replace("__PRINTER_NAME_BASE64__", encoded).replace(
        "__EXECUTION_FIELDS__", execution_fields.rstrip("\n")
    ).replace("__MUTATION__", mutation.rstrip("\n")).replace(
        "__AFTER_READ__", after_read.rstrip("\n")
    )


def build_default_printer_script(printer: str) -> str:
    """Return the fixed execution template with only an encoded name delta."""
    return _build_printer_script(printer, execute=True)


def _duplex_mode(orientation: str) -> str:
    if not isinstance(orientation, str) or orientation not in _DUPLEX_MODES:
        raise ValueError("orientation must be exactly long-edge or short-edge")
    return _DUPLEX_MODES[orientation]


def _build_word_duplex_script(printer: str, orientation: str, execute: bool) -> str:
    encoded = _encoded_name(printer)
    mode = _duplex_mode(orientation)
    execution_fields = """
    after = $null
    after_read = $false
    after_error = $null
    setter = @{ attempted = $false; 'return' = $null; error = $null }
""" if execute else ""
    mutation = """
        if ($exact.Count -eq 1) {
            $alreadyActive = ($payload.before -eq $requestedMode)
            if (-not $alreadyActive) {
                $payload.setter.attempted = $true
                try {
                    Set-PrintConfiguration -PrinterObject $exact[0] `
                        -DuplexingMode $requestedMode -Confirm:$false -ErrorAction Stop
                    $payload.setter.return = 0
                } catch {
                    $payload.setter.error = $_.Exception.GetType().FullName
                }
            }
        }
""" if execute else ""
    after_read = """
if ($exact.Count -eq 1) {
    try {
        $afterPrinters = @(Get-Printer -ErrorAction Stop)
        $afterExact = @($afterPrinters | Where-Object {
            [string]$_.Name -eq $requestedName
        })
        if ($afterExact.Count -ne 1) {
            throw 'Exact printer match changed during execution'
        }
        $afterConfiguration = Get-PrintConfiguration -PrinterObject $afterExact[0] `
            -ErrorAction Stop
        $payload.after = [string]$afterConfiguration.DuplexingMode
        $payload.after_read = $true
    } catch {
        $payload.after_error = $_.Exception.GetType().FullName
    }
}
""" if execute else ""
    return r"""
$ErrorActionPreference = 'Stop'
$requestedName = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String('__PRINTER_NAME_BASE64__'))
$requestedMode = '__DUPLEX_MODE__'
$payload = @{
    matches = @()
    before = $null
    read_error = $null
__EXECUTION_FIELDS__
}
$exact = @()
try {
    $printModule = @(Get-Module -ListAvailable -Name PrintManagement `
        -ErrorAction Stop)
    if ($printModule.Count -eq 0) {
        throw 'PrintManagement module is unavailable'
    }
    $beforePrinters = @(Get-Printer -ErrorAction Stop)
    $exact = @($beforePrinters | Where-Object {
        [string]$_.Name -eq $requestedName
    })
    $payload.matches = @($exact | ForEach-Object { [string]$_.Name })
    if ($exact.Count -eq 1) {
        $beforeConfiguration = Get-PrintConfiguration -PrinterObject $exact[0] `
            -ErrorAction Stop
        $payload.before = [string]$beforeConfiguration.DuplexingMode
        $capabilityExact = @(Get-CimInstance -ClassName Win32_Printer |
            Where-Object { [string]$_.Name -eq $requestedName })
        $payload.duplex_capable = (
            $capabilityExact.Count -eq 1 -and
            @($capabilityExact[0].Capabilities) -contains 3
        )
    }
__MUTATION__
} catch {
    $payload.read_error = $_.Exception.GetType().FullName
}
__AFTER_READ__
$json = $payload | ConvertTo-Json -Depth 6 -Compress
Write-Output ('MCP_ACTION_JSON:' +
    [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json)))
""".replace("__PRINTER_NAME_BASE64__", encoded).replace(
        "__DUPLEX_MODE__", mode
    ).replace("__EXECUTION_FIELDS__", execution_fields.rstrip("\n")).replace(
        "__MUTATION__", mutation.rstrip("\n")
    ).replace("__AFTER_READ__", after_read.rstrip("\n"))


def build_word_duplex_script(printer: str, orientation: str) -> str:
    """Return the fixed duplex template with encoded-name and reviewed-mode deltas."""
    return _build_word_duplex_script(printer, orientation, execute=True)


def parse_marked_json(text: str) -> dict[str, Any]:
    """Decode only a marked, bounded MCP-action JSON payload."""
    match = _PAYLOAD_RE.search(text)
    if not match:
        raise _ActionError("structured marker missing")
    try:
        raw = base64.b64decode(match.group(1), validate=True)
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _ActionError("structured payload malformed") from exc
    if not isinstance(payload, dict):
        raise _ActionError("structured payload is not an object")
    return payload


async def _invoke(script: str, timeout: int) -> dict[str, Any]:
    """Invoke one reviewed script and decode only its marked JSON payload."""
    out = await call_tool(
        "PowerShell",
        {"command": script, "timeout": timeout},
        _CONVERSATION_ID,
        audit=None,
    )
    if out.get("status") != "ok" or out.get("truncated"):
        raise _ActionError("host transport failed")
    return parse_marked_json(out.get("text", ""))


def _matches(payload: dict[str, Any]) -> list[str]:
    matches = payload.get("matches")
    if not isinstance(matches, list) or not all(
        isinstance(name, str) and name for name in matches
    ):
        raise _ActionError("invalid exact-match payload")
    return matches


def _optional_name(value: Any) -> str | None:
    if value is not None and not isinstance(value, str):
        raise _ActionError("invalid default-printer payload")
    return value


def _same_printer(left: str | None, right: str | None) -> bool:
    return left is not None and right is not None and left.casefold() == right.casefold()


def _managed_details(managed: Any) -> tuple[str, list[str]]:
    if not isinstance(managed, dict):
        return "unknown", [_UNKNOWN_CAVEAT]
    status = managed.get("status")
    value = managed.get("value")
    if status == "absent" or (status == "ok" and type(value) is int and value == 0):
        return "managed", [_MANAGED_CAVEAT]
    if status == "ok" and type(value) is int and value == 1:
        return "disabled", []
    return "unknown", [_UNKNOWN_CAVEAT]


def _bounded(reason: str) -> str:
    return reason[:450]


def _validation_failure(reason: str) -> dict[str, Any]:
    return {
        "status": "error",
        "current_default": None,
        "match_count": 0,
        "managed_default": "unknown",
        "caveats": [],
        "reason": _bounded(reason),
    }


def _validation_result(payload: dict[str, Any]) -> dict[str, Any]:
    matches = _matches(payload)
    before = _optional_name(payload.get("before"))
    managed, caveats = _managed_details(payload.get("managed"))
    result: dict[str, Any] = {
        "status": "ok",
        "current_default": before,
        "match_count": len(matches),
        "managed_default": managed,
        "caveats": caveats,
    }
    if payload.get("read_error"):
        result["status"] = "error"
        result["reason"] = "Windows printer state could not be read safely."
        return result
    if len(matches) != 1:
        result["status"] = "error"
        result["reason"] = (
            f"Expected exactly one case-insensitive exact printer match; found {len(matches)}."
        )
        return result
    result["printer"] = matches[0]
    return result


def _execution_failure(reason: str) -> dict[str, Any]:
    return {
        "status": "error",
        "action_id": _ACTION_ID,
        "changed": False,
        "before": {"default_printer": None},
        "after": {"default_printer": None},
        "verification": "unavailable",
        "caveats": [],
        "match_count": 0,
        "managed_default": "unknown",
        "reason": _bounded(reason),
    }


def _setter_problem(setter: Any, already_active: bool) -> str | None:
    if not isinstance(setter, dict) or type(setter.get("attempted")) is not bool:
        return "The structured printer setter outcome was missing."
    attempted = setter["attempted"]
    if not attempted:
        if already_active:
            return None
        return "The printer setter was not attempted although the target was not active."
    if setter.get("error"):
        return "The printer setter raised an exception; the fresh after-read is reported."
    code = setter.get("return")
    if type(code) is not int:
        return "The printer setter returned no valid completion code."
    if code != 0:
        return _bounded(f"SetDefaultPrinter returned {code}; zero is required.")
    return None


def _execution_result(payload: dict[str, Any]) -> dict[str, Any]:
    matches = _matches(payload)
    before = _optional_name(payload.get("before"))
    managed, caveats = _managed_details(payload.get("managed"))
    after_read = payload.get("after_read", "after" in payload) is True
    after = _optional_name(payload.get("after")) if after_read else None
    result: dict[str, Any] = {
        "status": "error",
        "action_id": _ACTION_ID,
        "changed": False,
        "before": {"default_printer": before},
        "after": {"default_printer": after},
        "verification": "unavailable",
        "caveats": caveats,
        "match_count": len(matches),
        "managed_default": managed,
    }
    if len(matches) == 1:
        result["printer"] = matches[0]
    if payload.get("read_error"):
        result["verification"] = "not-run"
        result["reason"] = "Windows printer state could not be read safely; no mutation ran."
        return result
    if len(matches) != 1:
        result["verification"] = "not-run"
        result["reason"] = (
            f"Expected exactly one case-insensitive exact printer match; found {len(matches)}."
        )
        return result

    canonical = matches[0]
    already_active = _same_printer(before, canonical)
    if after_read and not payload.get("after_error"):
        verified = _same_printer(after, canonical)
        result["verification"] = "verified" if verified else "mismatch"
        result["changed"] = verified and not already_active

    problem = _setter_problem(payload.get("setter"), already_active)
    if problem is None:
        if result["verification"] == "verified":
            result["status"] = "ok"
            return result
        if result["verification"] == "mismatch":
            problem = "The fresh default-printer read does not match the requested printer."
        else:
            problem = "The fresh default-printer read was unavailable."
    result["reason"] = _bounded(problem)
    return result


def _optional_duplex(value: Any) -> str | None:
    if value is not None and not isinstance(value, str):
        raise _ActionError("invalid duplex payload")
    return value


def _duplex_validation_failure(reason: str) -> dict[str, Any]:
    return {
        "status": "error",
        "current_duplex": None,
        "match_count": 0,
        "reason": _bounded(reason),
    }


def _duplex_validation_result(payload: dict[str, Any]) -> dict[str, Any]:
    matches = _matches(payload)
    before = _optional_duplex(payload.get("before"))
    result: dict[str, Any] = {
        "status": "ok",
        "current_duplex": before,
        "match_count": len(matches),
    }
    if payload.get("read_error"):
        result["status"] = "error"
        result["reason"] = (
            "PrintManagement printer state could not be read safely; "
            "the module may be unavailable."
        )
        return result
    if len(matches) != 1:
        result["status"] = "error"
        result["reason"] = (
            f"Expected exactly one case-insensitive exact printer match; found {len(matches)}."
        )
        return result
    result["printer"] = matches[0]
    if payload.get("duplex_capable") is False:
        result["status"] = "error"
        result["reason"] = "The selected printer does not advertise duplex capability."
    return result


def _duplex_execution_failure(reason: str, orientation: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "error",
        "action_id": _WORD_ACTION_ID,
        "changed": False,
        "before": {"duplex": None},
        "after": {"duplex": None},
        "verification": "unavailable",
        "match_count": 0,
        "reason": _bounded(reason),
    }
    if isinstance(orientation, str) and orientation in _DUPLEX_MODES:
        result["orientation"] = orientation
        result["requested_duplex"] = _DUPLEX_MODES[orientation]
    return result


def _duplex_setter_problem(setter: Any, already_active: bool) -> str | None:
    if not isinstance(setter, dict) or type(setter.get("attempted")) is not bool:
        return "The structured duplex setter outcome was missing."
    attempted = setter["attempted"]
    if not attempted:
        if already_active:
            return None
        return "The duplex setter was not attempted although the requested mode was not active."
    error = setter.get("error")
    if error:
        detail = str(error).casefold()
        if any(
            marker in detail
            for marker in ("unauthorizedaccess", "accessdenied", "permission")
        ):
            return (
                "Access denied: Set-PrintConfiguration requires administrator "
                "permission; the fresh after-read outcome is reported."
            )
        if "notsupported" in detail or "unsupported" in detail:
            return (
                "The printer or requested duplex mode is not supported; "
                "the fresh after-read outcome is reported."
            )
        return "The duplex setter raised an exception; the fresh after-read is reported."
    code = setter.get("return")
    if type(code) is not int:
        return "The duplex setter returned no valid completion code."
    if code != 0:
        return _bounded(f"Set-PrintConfiguration returned {code}; zero is required.")
    return None


def _duplex_execution_result(
    payload: dict[str, Any], orientation: str
) -> dict[str, Any]:
    requested = _duplex_mode(orientation)
    matches = _matches(payload)
    before = _optional_duplex(payload.get("before"))
    after_read = payload.get("after_read", "after" in payload) is True
    after = _optional_duplex(payload.get("after")) if after_read else None
    result: dict[str, Any] = {
        "status": "error",
        "action_id": _WORD_ACTION_ID,
        "orientation": orientation,
        "requested_duplex": requested,
        "changed": False,
        "before": {"duplex": before},
        "after": {"duplex": after},
        "verification": "unavailable",
        "match_count": len(matches),
    }
    if len(matches) == 1:
        result["printer"] = matches[0]
    if payload.get("read_error"):
        result["verification"] = "not-run"
        result["reason"] = (
            "PrintManagement printer state could not be read safely; "
            "the module may be unavailable; no mutation ran."
        )
        return result
    if len(matches) != 1:
        result["verification"] = "not-run"
        result["reason"] = (
            f"Expected exactly one case-insensitive exact printer match; found {len(matches)}."
        )
        return result
    if payload.get("duplex_capable") is False:
        result["verification"] = "not-run"
        result["reason"] = "The selected printer does not advertise duplex capability; no mutation ran."
        return result

    already_active = before == requested
    if after_read and not payload.get("after_error"):
        verified = after == requested
        result["verification"] = "verified" if verified else "mismatch"
        result["changed"] = verified and not already_active

    problem = _duplex_setter_problem(payload.get("setter"), already_active)
    if problem is None:
        if result["verification"] == "verified":
            result["status"] = "ok"
            return result
        if result["verification"] == "mismatch":
            problem = "The fresh duplex read does not match the requested mode."
        else:
            problem = "The fresh duplex read was unavailable."
    result["reason"] = _bounded(problem)
    return result



def _health_error(reason: str) -> dict[str, Any]:
    return {
        "status": "error",
        "action_id": health.HEALTH_ACTION_ID,
        "changed": False,
        "reason": reason[:500],
    }


async def _cleanup_health_artifacts(run_id: str) -> dict[str, str]:
    try:
        out = await call_tool(
            "PowerShell",
            {"command": health.build_cleanup_script(run_id), "timeout": 20},
            "mcp-action-system-health-check",
            audit=None,
            consent_attempts=2,
        )
        if isinstance(out, dict) and out.get("status") == "ok":
            marker = parse_marked_json(out.get("text", ""))
            if isinstance(marker, dict) and marker.get("status") == "ok":
                return {"status": "removed"}
    except Exception:  # noqa: BLE001 - cleanup is best-effort and sanitized
        return {"status": "failed"}
    return {"status": "failed"}


class ReviewedActions:
    """The confirmed Windows handlers; no arbitrary caller script is accepted."""

    async def validate_default_printer(self, printer: str) -> dict[str, Any]:
        """Read-only validation with one retry for transient CLIXML noise."""
        result: dict[str, Any] = {}
        for _ in range(2):
            try:
                script = _build_printer_script(printer, execute=False)
                payload = await _invoke(script, timeout=30)
                result = _validation_result(payload)
            except Exception:  # noqa: BLE001 - public boundary returns sanitized outcomes
                result = _validation_failure(
                    "Windows printer validation failed or returned malformed structured output."
                )
            reason = str(result.get("reason", "")).casefold()
            if result.get("status") != "error" or not any(
                token in reason for token in ("malformed structured output", "clixml", "transport")
            ):
                break
        return result

    async def execute_default_printer(self, printer: str) -> dict[str, Any]:
        """Execute once, then report setter and independent after-read outcomes."""
        try:
            payload = await _invoke(build_default_printer_script(printer), timeout=60)
            return _execution_result(payload)
        except Exception:  # noqa: BLE001 - never relay host text or executable payloads
            return _execution_failure(
                "Windows printer execution failed or returned malformed structured output; "
                "the mutation outcome is unknown and was not retried."
            )

    async def validate_word_printer_duplex(
        self, printer: str, orientation: str
    ) -> dict[str, Any]:
        """Read the exact printer's effective duplex mode without mutating it."""
        result: dict[str, Any] = {}
        for _ in range(2):
            try:
                script = _build_word_duplex_script(printer, orientation, execute=False)
                payload = await _invoke(script, timeout=30)
                result = _duplex_validation_result(payload)
            except Exception:  # noqa: BLE001 - public boundary returns sanitized outcomes
                result = _duplex_validation_failure(
                    "Word duplex validation failed or returned malformed structured output."
                )
            reason = str(result.get("reason", "")).casefold()
            if result.get("status") != "error" or not any(
                token in reason for token in ("malformed structured output", "clixml", "transport")
            ):
                break
        return result

    async def execute_word_printer_duplex(
        self, printer: str, orientation: str
    ) -> dict[str, Any]:
        """Set one reviewed duplex mode once and report the fresh after-read."""
        try:
            payload = await _invoke(
                build_word_duplex_script(printer, orientation), timeout=60
            )
            return _duplex_execution_result(payload, orientation)
        except Exception:  # noqa: BLE001 - never relay host text or executable payloads
            return _duplex_execution_failure(
                "Word duplex execution failed or returned malformed structured output; "
                "the mutation outcome is unknown and was not retried.",
                orientation,
            )


    async def execute_system_health_check(self) -> dict[str, Any]:
        """Run the fixed read-only health check once and retain only bounded evidence."""
        run_id = uuid.uuid4().hex
        out = None
        try:
            out = await call_tool(
                "PowerShell",
                {"command": health.build_health_wrapper(run_id), "timeout": health.WRAPPER_TIMEOUT_S},
                "mcp-action-system-health-check",
                audit=None,
                consent_attempts=4,
            )
            if not isinstance(out, dict) or out.get("status") != "ok":
                raise _ActionError("health host transport failed")
            marker = parse_marked_json(out.get("text", ""))
        except Exception:  # noqa: BLE001 - no host text crosses the boundary
            return _health_error("The system health check failed or returned malformed structured output; it was not retried.")

        if not isinstance(marker, dict) or marker.get("status") != "ok":
            detail = str(marker.get("reason") or marker.get("error") or "") if isinstance(marker, dict) else ""
            if "timeout" in detail.casefold():
                return _health_error("The system health check timeout occurred and was not retried.")
            return _health_error("The system health check failed before producing valid artifacts.")

        try:
            payload = health.read_health_json(run_id)
            summary = health.normalize_health_payload(payload)
        except Exception:  # noqa: BLE001 - malformed host data is untrusted
            return _health_error("The system health check returned malformed health data.")

        try:
            html_bytes = health.read_health_html(run_id)
        except Exception:  # noqa: BLE001 - report failure must not discard summary
            html_bytes = None
        cleanup = await _cleanup_health_artifacts(run_id)

        result: dict[str, Any] = {
            "status": "ok" if html_bytes is not None else "partial",
            "action_id": health.HEALTH_ACTION_ID,
            "changed": False,
            "verification": "reported",
            "health": {
                "status": summary["status"],
                "score": summary["score"],
                "counts": summary["counts"],
                "confidence": summary["confidence"],
            },
            "checks": summary["checks"],
            "reliability": summary["reliability"],
            "events": summary["events"],
            "inventory": summary["inventory"],
            "cleanup": cleanup,
        }
        if html_bytes is not None:
            result["report_html"] = html_bytes
            result["report_file"] = {
                "path": marker.get("userHtmlPath") or health.HOST_USER_REPORT_PATH,
                "status": "written" if marker.get("userHtml") is True else "unverified",
            }
        else:
            result["reason"] = "The health summary is available, but the report could not be published."
        return result
