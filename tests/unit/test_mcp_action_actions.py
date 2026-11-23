"""Default-printer and Word-duplex reviewed-action tests (spec 047, T013/T035).

The Windows host is always mocked. The fixed PowerShell templates return one
``MCP_ACTION_JSON:<base64-utf8-json>`` payload with this test protocol:

* default-printer reads: ``matches``, ``before``, and ``managed``;
* duplex reads: ``matches``, ``before``, and ``read_error``;
* execution adds ``after``/``after_read``/``after_error`` and ``setter``
  (``attempted``, ``return``, ``error``).

Default-printer ``managed`` is ``{status: absent|ok|error, value: ...}``. Duplex
``before``/``after`` values are effective ``DuplexingMode`` strings. Keeping host
data separate from ActionResult makes these tests prove that Python derives
success from the setter result and fresh after-state instead of trusting a host
claim.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agentic_rag_mcp.mcp_action import actions as actions_module
from agentic_rag_mcp.mcp_action import health as health_module
from agentic_rag_mcp.windows_mcp import client as windows_client

FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "mcp_action" / "malicious_printers.json"
)
PRINTER_NAMES = json.loads(FIXTURE.read_text(encoding="utf-8"))["printer_names"]
LITERAL_NAMES = [name for name in PRINTER_NAMES if not any(c in name for c in "\0\r\n")]
MARKER = "MCP_ACTION_JSON:"
CLIXML = (
    "#< CLIXML\n"
    '<Objs Version="1.1.0.1"><Obj S="progress">Sanitized synthetic noise</Obj></Objs>'
)
SECRET = "HUNTER2-do-not-relay"
SECRET_PATH = r"C:\Users\private\secret.ps1"


@pytest.fixture
def reviewed_actions():
    return actions_module.ReviewedActions()


@pytest.fixture
def host(monkeypatch):
    """Block both module and direct-import styles from reaching live Windows."""
    mock = AsyncMock()
    monkeypatch.setattr(windows_client, "call_tool", mock)
    monkeypatch.setattr(actions_module, "call_tool", mock, raising=False)
    return mock


def _managed(status="absent", value=None, error=None):
    result = {"status": status, "value": value}
    if error is not None:
        result["error"] = error
    return result


def _read_payload(matches="Printer", before="Old Printer", managed=None):
    if isinstance(matches, str):
        matches = [matches]
    return {
        "matches": matches,
        "before": before,
        "managed": managed if managed is not None else _managed(),
    }


def _write_payload(
    matches="Printer",
    before="Old Printer",
    after="Printer",
    setter=None,
    managed=None,
):
    result = _read_payload(matches, before, managed)
    result.update(
        {
            "after": after,
            "setter": setter
            if setter is not None
            else {"attempted": True, "return": 0, "error": None},
        }
    )
    return result


def _duplex_read_payload(matches="Printer", before="OneSided", read_error=None):
    if isinstance(matches, str):
        matches = [matches]
    return {"matches": matches, "before": before, "read_error": read_error}


def _duplex_write_payload(
    matches="Printer",
    before="OneSided",
    after="TwoSidedLongEdge",
    setter=None,
    read_error=None,
    after_read=True,
    after_error=None,
):
    result = _duplex_read_payload(matches, before, read_error)
    result.update(
        {
            "after": after,
            "after_read": after_read,
            "after_error": after_error,
            "setter": setter
            if setter is not None
            else {"attempted": True, "return": 0, "error": None},
        }
    )
    return result


def _marked(payload, prefix="", suffix=""):
    encoded = base64.b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return {
        "status": "ok",
        "tool": "PowerShell",
        "text": f"{prefix}{MARKER}{encoded}{suffix}",
        "truncated": False,
    }


def _run(awaitable):
    return asyncio.run(awaitable)


def _name_base64(name):
    return base64.b64encode(name.encode("utf-8")).decode("ascii")


def _host_script(host, call_index=-1):
    call = host.await_args_list[call_index]
    assert call.args[0] == "PowerShell"
    arguments = call.args[1]
    assert set(arguments) <= {"command", "timeout"}
    assert isinstance(arguments["command"], str)
    return arguments["command"]


def _assert_no_registry_writes_or_escape_hatches(script):
    lowered = script.lower()
    for forbidden in (
        "rundll32",
        "printui.dll",
        "set-itemproperty",
        "new-itemproperty",
        "remove-itemproperty",
        ".setvalue(",
        "reg add",
        "reg.exe",
        "start-process",
        "runas.exe",
        "-verb runas",
        "rollback",
    ):
        assert forbidden not in lowered


def _assert_no_duplex_elevation_test_page_or_rollback(script):
    _assert_no_registry_writes_or_escape_hatches(script)
    lowered = script.lower()
    for forbidden in ("printtestpage", "printout", "out-printer", "test page"):
        assert forbidden not in lowered


def _assert_sanitized_error(result, *sensitive):
    assert result["status"] == "error"
    assert isinstance(result.get("reason"), str) and result["reason"]
    assert len(result["reason"]) <= 500
    serialized = json.dumps(result, ensure_ascii=False)
    assert "CLIXML" not in serialized
    for value in (SECRET, SECRET_PATH, *sensitive):
        assert value not in serialized


@pytest.mark.parametrize("printer", LITERAL_NAMES)
def test_script_transports_fixture_names_as_utf8_base64_literals(printer):
    script = actions_module.build_default_printer_script(printer)
    encoded = _name_base64(printer)

    assert encoded in script
    assert base64.b64decode(encoded).decode("utf-8") == printer
    assert "FromBase64String" in script
    assert "UTF8" in script or "UTF-8" in script
    if printer not in {"Printer", "Printer Copy"}:
        # ``Win32_Printer`` naturally contains the ordinary word Printer.
        assert printer not in script
    _assert_no_registry_writes_or_escape_hatches(script)


def test_script_is_one_fixed_template_with_only_the_encoded_name_delta():
    first_name = "Quote ' Printer"
    second_name = "Printer “Smart”"
    first = actions_module.build_default_printer_script(first_name)
    second = actions_module.build_default_printer_script(second_name)

    assert first.replace(_name_base64(first_name), "<PRINTER_NAME>") == second.replace(
        _name_base64(second_name), "<PRINTER_NAME>"
    )


def test_script_uses_exact_cim_matching_and_the_reviewed_per_user_setter():
    script = actions_module.build_default_printer_script("Office * Test")

    assert "Get-CimInstance" in script
    assert "Win32_Printer" in script
    assert "Invoke-CimMethod" in script
    assert script.count("SetDefaultPrinter") == 1
    assert "ReturnValue" in script
    assert "-eq" in script
    assert "LegacyDefaultPrinterMode" in script
    assert "Get-ItemProperty" in script
    assert MARKER in script
    assert "ToBase64String" in script
    assert "ConvertTo-Json" in script


def test_script_has_no_wildcard_wql_interpolation_elevation_or_rollback():
    script = actions_module.build_default_printer_script("$(whoami) Printer")
    lowered = script.lower()

    for forbidden in ("-like", "-match", "get-printer", "-filter", "-query", "select "):
        assert forbidden not in lowered
    assert "whoami" not in lowered
    assert "$(whoami) Printer" not in script
    _assert_no_registry_writes_or_escape_hatches(script)


def test_validation_dispatches_only_a_read_only_powershell_template(
    reviewed_actions, host
):
    printer = "Imprimante café"
    host.return_value = _marked(_read_payload(printer))

    result = _run(reviewed_actions.validate_default_printer(printer))

    assert result["status"] == "ok"
    script = _host_script(host)
    assert _name_base64(printer) in script
    assert "Get-CimInstance" in script
    assert "SetDefaultPrinter" not in script
    _assert_no_registry_writes_or_escape_hatches(script)


def test_validation_retries_one_transient_read_error_without_touching_execution(reviewed_actions, host):
    good = _read_payload(
        matches=["HP LaserJet M610 TCPIP"],
        before="HP",
        managed={"status": "ok", "value": 1},
    )
    host.side_effect = [
        {"status": "error", "reason": "host returned malformed structured output."},
        _marked(good),
    ]

    validated = _run(reviewed_actions.validate_default_printer("HP LaserJet M610 TCPIP"))

    assert validated["status"] == "ok"
    assert host.call_count == 2

    host.reset_mock()
    host.return_value = {"status": "error", "reason": "host returned malformed structured output."}
    executed = _run(reviewed_actions.execute_default_printer("HP LaserJet M610 TCPIP"))
    assert executed["status"] == "error"
    assert host.call_count == 1


def test_validation_returns_the_single_canonical_case_insensitive_match(
    reviewed_actions, host
):
    host.return_value = _marked(_read_payload("Imprimante café", before="Old Printer"))

    result = _run(reviewed_actions.validate_default_printer("imprimante CAFÉ"))

    assert result["status"] == "ok"
    assert result["printer"] == "Imprimante café"
    assert result["current_default"] == "Old Printer"
    assert result["match_count"] == 1
    assert result["managed_default"] == "managed"
    assert result["caveats"] == [
        (
            "Windows manages the default printer; choosing a manual default may turn off "
            "'Let Windows manage my default printer'; the verified change may not persist."
        )
    ]


def test_validation_allows_no_current_default(reviewed_actions, host):
    host.return_value = _marked(_read_payload("Printer", before=None))

    result = _run(reviewed_actions.validate_default_printer("Printer"))

    assert result["status"] == "ok"
    assert result["current_default"] is None


@pytest.mark.parametrize("matches", [[], ["Printer", "PRINTER"]])
def test_validation_requires_exactly_one_match(reviewed_actions, host, matches):
    host.return_value = _marked(_read_payload(matches))

    result = _run(reviewed_actions.validate_default_printer("Printer"))

    assert result["status"] == "error"
    assert result["match_count"] == len(matches)
    assert "exactly one" in result["reason"].lower()
    assert "SetDefaultPrinter" not in _host_script(host)


@pytest.mark.parametrize(
    ("managed", "diagnostic", "caveat_text"),
    [
        # Absent/0 enables Windows management; 1 selects legacy/manual behavior.
        (_managed("absent"), "managed", "let windows manage"),
        (_managed("ok", 0), "managed", "let windows manage"),
        (_managed("ok", 1), "disabled", None),
        (_managed("ok", 7), "unknown", "unknown"),
        (_managed("error", error=f"{SECRET} {SECRET_PATH}"), "unknown", "unknown"),
    ],
)
def test_managed_default_is_diagnostic_caveat_only_without_registry_writes(
    reviewed_actions, host, managed, diagnostic, caveat_text
):
    host.return_value = _marked(_read_payload("Printer", managed=managed))

    result = _run(reviewed_actions.validate_default_printer("Printer"))

    assert result["status"] == "ok"
    assert result["managed_default"] == diagnostic
    if caveat_text is None:
        assert result["caveats"] == []
    else:
        assert any(caveat_text in caveat.lower() for caveat in result["caveats"])
        assert any("may not persist" in caveat.lower() for caveat in result["caveats"])
    serialized = json.dumps({key: value for key, value in result.items() if key != "report_html"})
    assert SECRET not in serialized and SECRET_PATH not in serialized
    _assert_no_registry_writes_or_escape_hatches(_host_script(host))


def test_execute_dispatches_the_fixed_script_and_requires_zero_and_fresh_match(
    reviewed_actions, host
):
    host.return_value = _marked(_write_payload())

    result = _run(reviewed_actions.execute_default_printer("Printer"))

    assert result["status"] == "ok"
    assert result["action_id"] == "windows_default_printer"
    assert result["changed"] is True
    assert result["before"] == {"default_printer": "Old Printer"}
    assert result["after"] == {"default_printer": "Printer"}
    assert result["verification"] == "verified"
    host.assert_awaited_once()
    script = _host_script(host)
    assert script == actions_module.build_default_printer_script("Printer")
    assert 0 < host.await_args.args[1]["timeout"] <= 60


def test_execute_accepts_a_case_insensitive_fresh_after_read_match(
    reviewed_actions, host
):
    host.return_value = _marked(
        _write_payload(matches="Printer", before="Old Printer", after="PRINTER")
    )

    result = _run(reviewed_actions.execute_default_printer("printer"))

    assert result["status"] == "ok"
    assert result["changed"] is True
    assert result["after"] == {"default_printer": "PRINTER"}
    assert result["verification"] == "verified"


def test_execute_with_no_current_default_reports_the_actual_transition(
    reviewed_actions, host
):
    host.return_value = _marked(_write_payload(before=None))

    result = _run(reviewed_actions.execute_default_printer("Printer"))

    assert result["status"] == "ok"
    assert result["before"] == {"default_printer": None}
    assert result["changed"] is True


def test_already_active_is_ok_changed_false_without_calling_the_setter(
    reviewed_actions, host
):
    host.return_value = _marked(
        _write_payload(
            before="Printer",
            after="Printer",
            setter={"attempted": False, "return": None, "error": None},
        )
    )

    result = _run(reviewed_actions.execute_default_printer("printer"))

    assert result["status"] == "ok"
    assert result["changed"] is False
    assert result["verification"] == "verified"
    host.assert_awaited_once()


@pytest.mark.parametrize("after", ["Other Printer", None])
def test_zero_setter_result_still_requires_a_matching_fresh_after_read(
    reviewed_actions, host, after
):
    host.return_value = _marked(_write_payload(after=after))

    result = _run(reviewed_actions.execute_default_printer("Printer"))

    assert result["status"] == "error"
    assert result["changed"] is False
    assert result["before"] == {"default_printer": "Old Printer"}
    assert result["after"] == {"default_printer": after}
    assert result["verification"] == "mismatch"
    host.assert_awaited_once()


@pytest.mark.parametrize(
    ("after", "verification", "changed"),
    [("Printer", "verified", True), ("Old Printer", "mismatch", False)],
)
def test_nonzero_setter_is_an_error_with_after_read_even_if_state_changed(
    reviewed_actions, host, after, verification, changed
):
    host.return_value = _marked(
        _write_payload(
            after=after,
            setter={"attempted": True, "return": 5, "error": None},
        )
    )

    result = _run(reviewed_actions.execute_default_printer("Printer"))

    assert result["status"] == "error"
    assert result["verification"] == verification
    assert result["changed"] is changed
    assert result["after"] == {"default_printer": after}
    assert "5" in result["reason"]
    host.assert_awaited_once()  # no retry and no separate rollback call


@pytest.mark.parametrize(
    ("after", "verification", "changed"),
    [("Printer", "verified", True), ("Old Printer", "mismatch", False)],
)
def test_setter_exception_is_sanitized_and_reports_the_after_read(
    reviewed_actions, host, after, verification, changed
):
    host.return_value = _marked(
        _write_payload(
            after=after,
            setter={
                "attempted": True,
                "return": None,
                "error": f"{SECRET} {SECRET_PATH} {CLIXML}",
            },
        )
    )

    result = _run(reviewed_actions.execute_default_printer("Printer"))

    _assert_sanitized_error(result)
    assert result["verification"] == verification
    assert result["changed"] is changed
    assert result["after"] == {"default_printer": after}
    host.assert_awaited_once()  # no blind retry of an unknown mutation


def test_attempted_setter_without_a_return_code_is_not_success(reviewed_actions, host):
    host.return_value = _marked(
        _write_payload(
            setter={"attempted": True, "return": None, "error": None},
        )
    )

    result = _run(reviewed_actions.execute_default_printer("Printer"))

    assert result["status"] == "error"
    assert result["after"] == {"default_printer": "Printer"}
    assert result["verification"] == "verified"
    host.assert_awaited_once()


def test_printer_removed_between_validation_and_execution_is_never_substituted(
    reviewed_actions, host
):
    host.side_effect = [
        _marked(_read_payload("Printer")),
        _marked(
            _write_payload(
                matches=[],
                after="Old Printer",
                setter={"attempted": False, "return": None, "error": None},
            )
        ),
    ]

    validated = _run(reviewed_actions.validate_default_printer("Printer"))
    result = _run(reviewed_actions.execute_default_printer("Printer"))

    assert validated["status"] == "ok"
    assert result["status"] == "error"
    assert result["match_count"] == 0
    assert result["changed"] is False
    assert result["verification"] == "not-run"
    assert result.get("printer") != "Printer Copy"
    assert host.await_count == 2  # one fresh validation and one execution, no retry


@pytest.mark.parametrize(
    ("managed", "caveat_text"),
    [
        (_managed("ok", 0), "let windows manage"),
        (_managed("error", error=f"{SECRET} {SECRET_PATH}"), "unknown"),
    ],
)
def test_verified_execution_retains_managed_default_caveats_without_registry_writes(
    reviewed_actions, host, managed, caveat_text
):
    host.return_value = _marked(_write_payload(managed=managed))

    result = _run(reviewed_actions.execute_default_printer("Printer"))

    assert result["status"] == "ok"
    assert result["verification"] == "verified"
    assert any(caveat_text in caveat.lower() for caveat in result["caveats"])
    serialized = json.dumps({key: value for key, value in result.items() if key != "report_html"})
    assert SECRET not in serialized and SECRET_PATH not in serialized
    _assert_no_registry_writes_or_escape_hatches(_host_script(host))


def test_marked_base64_json_ignores_clixml_and_decoys_before_and_after(
    reviewed_actions, host
):
    decoy = json.dumps({"after": "Other Printer", "setter": {"return": 0}})
    host.return_value = _marked(
        _write_payload(),
        prefix=f"{CLIXML}\n{decoy}\n",
        suffix=f"\n{CLIXML}\n",
    )

    result = _run(reviewed_actions.execute_default_printer("Printer"))

    assert result["status"] == "ok"
    assert result["after"] == {"default_printer": "Printer"}
    assert result["verification"] == "verified"


def test_validation_also_parses_only_the_marked_base64_json(reviewed_actions, host):
    host.return_value = _marked(
        _read_payload("Printer"),
        prefix=f"{CLIXML}\n",
        suffix=f"\n{CLIXML}",
    )

    result = _run(reviewed_actions.validate_default_printer("Printer"))

    assert result["status"] == "ok"
    assert result["printer"] == "Printer"


@pytest.mark.parametrize(
    "text",
    [
        '{"matches":["Printer"],"before":null}',
        f"{MARKER}not-valid-base64!{CLIXML}",
        MARKER + base64.b64encode(b"{not-json").decode("ascii"),
        CLIXML,
        "",
    ],
)
def test_missing_malformed_or_unmarked_json_fails_closed_without_raw_noise(
    reviewed_actions, host, text
):
    host.return_value = {"status": "ok", "text": text}

    result = _run(reviewed_actions.execute_default_printer("Printer"))

    _assert_sanitized_error(result)
    assert result["verification"] == "unavailable"
    host.assert_awaited_once()


def test_transport_errors_are_bounded_and_do_not_leak_raw_host_details(
    reviewed_actions, host
):
    host.return_value = {
        "status": "error",
        "reason": f"{SECRET} {SECRET_PATH} {CLIXML} " + "x" * 5000,
    }

    result = _run(reviewed_actions.execute_default_printer("Printer"))

    _assert_sanitized_error(result, "x" * 501)
    assert result["verification"] == "unavailable"
    host.assert_awaited_once()


def test_unexpected_host_exception_becomes_a_sanitized_error(reviewed_actions, host):
    host.side_effect = RuntimeError(f"{SECRET} {SECRET_PATH}")

    result = _run(reviewed_actions.execute_default_printer("Printer"))

    _assert_sanitized_error(result)
    assert result["verification"] == "unavailable"
    host.assert_awaited_once()


@pytest.mark.parametrize("printer", LITERAL_NAMES)
def test_duplex_script_transports_fixture_names_as_utf8_base64_literals(printer):
    script = actions_module.build_word_duplex_script(printer, "long-edge")
    encoded = _name_base64(printer)

    assert encoded in script
    assert base64.b64decode(encoded).decode("utf-8") == printer
    assert "FromBase64String" in script
    assert "UTF8" in script or "UTF-8" in script
    assert "TwoSidedLongEdge" in script
    assert "TwoSidedShortEdge" not in script
    if printer not in {"Printer", "Printer Copy"}:
        # PrintManagement cmdlets naturally contain the ordinary word Printer.
        assert printer not in script
    _assert_no_duplex_elevation_test_page_or_rollback(script)


def test_duplex_script_is_one_fixed_template_with_only_name_and_mode_deltas():
    first_name = "Quote ' Printer"
    second_name = "Printer “Smart”"
    first = actions_module.build_word_duplex_script(first_name, "long-edge")
    second = actions_module.build_word_duplex_script(second_name, "long-edge")
    short = actions_module.build_word_duplex_script(first_name, "short-edge")

    assert first.replace(_name_base64(first_name), "<PRINTER_NAME>") == second.replace(
        _name_base64(second_name), "<PRINTER_NAME>"
    )
    assert first.replace(_name_base64(first_name), "<PRINTER_NAME>").replace(
        "TwoSidedLongEdge", "<DUPLEX_MODE>"
    ) == short.replace(_name_base64(first_name), "<PRINTER_NAME>").replace(
        "TwoSidedShortEdge", "<DUPLEX_MODE>"
    )


def test_duplex_script_exactly_matches_and_freshly_reads_printconfiguration():
    script = actions_module.build_word_duplex_script("Office * Test", "long-edge")
    lowered = script.lower()

    assert "Get-Printer" in script
    assert "Where-Object" in script
    assert "-eq" in script
    assert "-PrinterObject" in script
    assert script.count("Get-PrintConfiguration") == 2
    assert script.count("Set-PrintConfiguration") == 1
    assert "-Confirm:$false" in script
    assert "DuplexingMode" in script
    first_read = script.index("Get-PrintConfiguration")
    setter = script.index("Set-PrintConfiguration")
    second_read = script.index("Get-PrintConfiguration", first_read + 1)
    assert first_read < setter < second_read
    assert MARKER in script
    assert "ToBase64String" in script
    assert "ConvertTo-Json" in script
    for forbidden in (
        "-like",
        "-match",
        "-filter",
        "-query",
        "get-printer -name",
        "-printername $requestedname",
    ):
        assert forbidden not in lowered
    assert "Office * Test" not in script
    _assert_no_duplex_elevation_test_page_or_rollback(script)


@pytest.mark.parametrize(
    "orientation",
    [
        None,
        "",
        "OneSided",
        "TwoSidedLongEdge",
        "TwoSidedShortEdge",
        "LONG-EDGE",
        " long-edge ",
        "long-edge; PrintTestPage",
    ],
)
def test_duplex_script_rejects_every_unreviewed_orientation(orientation):
    with pytest.raises((TypeError, ValueError)):
        actions_module.build_word_duplex_script("Printer", orientation)


def test_duplex_script_rejects_missing_orientation_and_unknown_parameters():
    with pytest.raises(TypeError):
        actions_module.build_word_duplex_script("Printer")
    with pytest.raises(TypeError):
        actions_module.build_word_duplex_script(
            "Printer", "long-edge", mode="TwoSidedLongEdge"
        )


def test_duplex_validation_is_read_only_and_returns_the_canonical_exact_match(
    reviewed_actions, host
):
    host.return_value = _marked(
        _duplex_read_payload("Imprimante café", before="OneSided")
    )

    result = _run(
        reviewed_actions.validate_word_printer_duplex(
            "imprimante CAFÉ", "long-edge"
        )
    )

    assert result["status"] == "ok"
    assert result["printer"] == "Imprimante café"
    assert result["current_duplex"] == "OneSided"
    assert result["match_count"] == 1
    host.assert_awaited_once()
    script = _host_script(host)
    assert _name_base64("imprimante CAFÉ") in script
    assert script.count("Get-PrintConfiguration") == 1
    assert "Set-PrintConfiguration" not in script
    _assert_no_duplex_elevation_test_page_or_rollback(script)


def test_duplex_capability_false_blocks_offer_and_execution(reviewed_actions, host):
    read = _duplex_read_payload("Printer")
    read["duplex_capable"] = False
    host.return_value = _marked(read)

    validated = _run(reviewed_actions.validate_word_printer_duplex("Printer", "long-edge"))

    assert validated["status"] == "error"
    assert "duplex capability" in validated["reason"].lower()

    write = _duplex_write_payload("Printer")
    write["duplex_capable"] = False
    host.return_value = _marked(write)
    executed = _run(reviewed_actions.execute_word_printer_duplex("Printer", "long-edge"))
    assert executed["status"] == "error"
    assert executed["verification"] == "not-run"
    assert "no mutation ran" in executed["reason"].lower()


@pytest.mark.parametrize("matches", [[], ["Printer", "PRINTER"]])
def test_duplex_validation_requires_exactly_one_printer_match(
    reviewed_actions, host, matches
):
    host.return_value = _marked(_duplex_read_payload(matches))

    result = _run(
        reviewed_actions.validate_word_printer_duplex("Printer", "long-edge")
    )

    assert result["status"] == "error"
    assert result["match_count"] == len(matches)
    assert "exactly one" in result["reason"].lower()
    assert "Set-PrintConfiguration" not in _host_script(host)


@pytest.mark.parametrize(
    ("orientation", "mode"),
    [
        ("long-edge", "TwoSidedLongEdge"),
        ("short-edge", "TwoSidedShortEdge"),
    ],
)
def test_duplex_execute_maps_orientation_and_requires_a_fresh_matching_after_read(
    reviewed_actions, host, orientation, mode
):
    host.return_value = _marked(_duplex_write_payload(after=mode))

    result = _run(
        reviewed_actions.execute_word_printer_duplex("Printer", orientation)
    )

    assert result["status"] == "ok"
    assert result["action_id"] == "word_printer_duplex"
    assert result["printer"] == "Printer"
    assert result["orientation"] == orientation
    assert result["requested_duplex"] == mode
    assert result["changed"] is True
    assert result["before"] == {"duplex": "OneSided"}
    assert result["after"] == {"duplex": mode}
    assert result["verification"] == "verified"
    assert result["match_count"] == 1
    host.assert_awaited_once()
    script = _host_script(host)
    assert script == actions_module.build_word_duplex_script("Printer", orientation)
    assert script.count("Get-PrintConfiguration") == 2
    assert 0 < host.await_args.args[1]["timeout"] <= 90


def test_duplex_already_active_is_ok_changed_false_without_calling_the_setter(
    reviewed_actions, host
):
    host.return_value = _marked(
        _duplex_write_payload(
            before="TwoSidedShortEdge",
            after="TwoSidedShortEdge",
            setter={"attempted": False, "return": None, "error": None},
        )
    )

    result = _run(
        reviewed_actions.execute_word_printer_duplex("printer", "short-edge")
    )

    assert result["status"] == "ok"
    assert result["changed"] is False
    assert result["requested_duplex"] == "TwoSidedShortEdge"
    assert result["before"] == {"duplex": "TwoSidedShortEdge"}
    assert result["after"] == {"duplex": "TwoSidedShortEdge"}
    assert result["verification"] == "verified"
    host.assert_awaited_once()


def test_duplex_execute_never_substitutes_an_unknown_printer(reviewed_actions, host):
    host.return_value = _marked(
        _duplex_write_payload(
            matches=[],
            before=None,
            after=None,
            after_read=False,
            setter={"attempted": False, "return": None, "error": None},
        )
    )

    result = _run(
        reviewed_actions.execute_word_printer_duplex("Printer", "long-edge")
    )

    assert result["status"] == "error"
    assert result["match_count"] == 0
    assert result["changed"] is False
    assert result["verification"] == "not-run"
    assert result.get("printer") != "Printer Copy"
    host.assert_awaited_once()


@pytest.mark.parametrize(
    "method_name",
    ["validate_word_printer_duplex", "execute_word_printer_duplex"],
)
def test_duplex_missing_printmanagement_is_an_honest_error_without_mutation(
    reviewed_actions, host, method_name
):
    if method_name.startswith("validate"):
        host.return_value = _marked(
            _duplex_read_payload(read_error="CommandNotFoundException")
        )
    else:
        host.return_value = _marked(
            _duplex_write_payload(
                after=None,
                after_read=False,
                read_error="CommandNotFoundException",
                setter={"attempted": False, "return": None, "error": None},
            )
        )

    result = _run(getattr(reviewed_actions, method_name)("Printer", "long-edge"))

    _assert_sanitized_error(result)
    assert "printmanagement" in result["reason"].lower()
    host.assert_awaited_once()
    if method_name.startswith("execute"):
        assert result["changed"] is False
        assert result["verification"] == "not-run"
        assert result["after"] == {"duplex": None}


def test_duplex_unsupported_mode_reports_the_fresh_unchanged_after_read(
    reviewed_actions, host
):
    host.return_value = _marked(
        _duplex_write_payload(
            after="OneSided",
            setter={
                "attempted": True,
                "return": None,
                "error": "NotSupportedException",
            },
        )
    )

    result = _run(
        reviewed_actions.execute_word_printer_duplex("Printer", "long-edge")
    )

    assert result["status"] == "error"
    assert "support" in result["reason"].lower()
    assert result["changed"] is False
    assert result["after"] == {"duplex": "OneSided"}
    assert result["verification"] == "mismatch"
    host.assert_awaited_once()
    _assert_no_duplex_elevation_test_page_or_rollback(_host_script(host))


def test_duplex_access_denied_names_the_admin_permission_limit_without_elevation(
    reviewed_actions, host
):
    host.return_value = _marked(
        _duplex_write_payload(
            after="OneSided",
            setter={
                "attempted": True,
                "return": None,
                "error": "UnauthorizedAccessException",
            },
        )
    )

    result = _run(
        reviewed_actions.execute_word_printer_duplex("Printer", "long-edge")
    )

    _assert_sanitized_error(result)
    assert any(
        word in result["reason"].lower()
        for word in ("access", "permission", "admin")
    )
    assert result["changed"] is False
    assert result["after"] == {"duplex": "OneSided"}
    assert result["verification"] == "mismatch"
    host.assert_awaited_once()
    _assert_no_duplex_elevation_test_page_or_rollback(_host_script(host))


@pytest.mark.parametrize(
    ("after", "verification", "changed"),
    [
        ("TwoSidedLongEdge", "verified", True),
        ("OneSided", "mismatch", False),
    ],
)
def test_duplex_nonzero_setter_is_an_error_with_the_after_read(
    reviewed_actions, host, after, verification, changed
):
    host.return_value = _marked(
        _duplex_write_payload(
            after=after,
            setter={"attempted": True, "return": 5, "error": None},
        )
    )

    result = _run(
        reviewed_actions.execute_word_printer_duplex("Printer", "long-edge")
    )

    assert result["status"] == "error"
    assert result["verification"] == verification
    assert result["changed"] is changed
    assert result["after"] == {"duplex": after}
    assert "5" in result["reason"]
    host.assert_awaited_once()  # no retry and no separate rollback call


@pytest.mark.parametrize(
    ("after", "verification", "changed"),
    [
        ("TwoSidedLongEdge", "verified", True),
        ("OneSided", "mismatch", False),
    ],
)
def test_duplex_setter_exception_is_sanitized_and_reports_the_after_read(
    reviewed_actions, host, after, verification, changed
):
    host.return_value = _marked(
        _duplex_write_payload(
            after=after,
            setter={
                "attempted": True,
                "return": None,
                "error": f"{SECRET} {SECRET_PATH} {CLIXML}",
            },
        )
    )

    result = _run(
        reviewed_actions.execute_word_printer_duplex("Printer", "long-edge")
    )

    _assert_sanitized_error(result)
    assert result["verification"] == verification
    assert result["changed"] is changed
    assert result["after"] == {"duplex": after}
    host.assert_awaited_once()  # no blind retry or rollback of an unknown mutation
    _assert_no_duplex_elevation_test_page_or_rollback(_host_script(host))


def test_duplex_zero_setter_still_fails_when_the_fresh_after_read_is_unavailable(
    reviewed_actions, host
):
    host.return_value = _marked(
        _duplex_write_payload(
            after=None,
            after_read=False,
            after_error="TimeoutException",
        )
    )

    result = _run(
        reviewed_actions.execute_word_printer_duplex("Printer", "long-edge")
    )

    assert result["status"] == "error"
    assert result["changed"] is False
    assert result["after"] == {"duplex": None}
    assert result["verification"] == "unavailable"
    host.assert_awaited_once()


def test_duplex_marked_base64_json_ignores_clixml_and_decoys(
    reviewed_actions, host
):
    decoy = json.dumps({"after": "TwoSidedLongEdge", "setter": {"return": 0}})
    host.return_value = _marked(
        _duplex_write_payload(after="TwoSidedShortEdge"),
        prefix=f"{CLIXML}\n{decoy}\n",
        suffix=f"\n{CLIXML}\n",
    )

    result = _run(
        reviewed_actions.execute_word_printer_duplex("Printer", "short-edge")
    )

    assert result["status"] == "ok"
    assert result["after"] == {"duplex": "TwoSidedShortEdge"}
    assert result["verification"] == "verified"


@pytest.mark.parametrize(
    "text",
    [
        '{"matches":["Printer"],"before":"OneSided"}',
        f"{MARKER}not-valid-base64!{CLIXML}",
        MARKER + base64.b64encode(b"{not-json").decode("ascii"),
        MARKER + base64.b64encode(b"[]").decode("ascii"),
        CLIXML,
        "",
    ],
)
def test_duplex_malformed_or_unmarked_json_fails_closed_without_raw_noise(
    reviewed_actions, host, text
):
    host.return_value = {"status": "ok", "text": text}

    result = _run(
        reviewed_actions.execute_word_printer_duplex("Printer", "long-edge")
    )

    _assert_sanitized_error(result)
    assert result["verification"] == "unavailable"
    host.assert_awaited_once()


def test_duplex_transport_errors_are_bounded_and_sanitized(reviewed_actions, host):
    host.return_value = {
        "status": "error",
        "reason": f"{SECRET} {SECRET_PATH} {CLIXML} " + "x" * 5000,
    }

    result = _run(
        reviewed_actions.execute_word_printer_duplex("Printer", "long-edge")
    )

    _assert_sanitized_error(result, "x" * 501)
    assert result["verification"] == "unavailable"
    host.assert_awaited_once()


def test_duplex_unexpected_host_exception_becomes_a_sanitized_error(
    reviewed_actions, host
):
    host.side_effect = RuntimeError(f"{SECRET} {SECRET_PATH}")

    result = _run(
        reviewed_actions.execute_word_printer_duplex("Printer", "long-edge")
    )

    _assert_sanitized_error(result)
    assert result["verification"] == "unavailable"
    host.assert_awaited_once()


@pytest.mark.parametrize("orientation", [None, "OneSided", "long_edge"])
@pytest.mark.parametrize(
    "method_name",
    ["validate_word_printer_duplex", "execute_word_printer_duplex"],
)
def test_duplex_methods_reject_invalid_orientation_without_calling_windows(
    reviewed_actions, host, method_name, orientation
):
    result = _run(
        getattr(reviewed_actions, method_name)("Printer", orientation)
    )

    _assert_sanitized_error(result)
    host.assert_not_awaited()
    if method_name.startswith("execute"):
        assert result["changed"] is False
        assert result["verification"] == "unavailable"


@pytest.mark.parametrize(
    "method_name",
    ["validate_word_printer_duplex", "execute_word_printer_duplex"],
)
def test_duplex_methods_reject_missing_orientation_and_unknown_parameters(
    reviewed_actions, host, method_name
):
    method = getattr(reviewed_actions, method_name)

    with pytest.raises(TypeError):
        method("Printer")
    with pytest.raises(TypeError):
        method("Printer", "long-edge", mode="TwoSidedLongEdge")
    host.assert_not_awaited()


# --- Spec 048 T008: fixed read-only system-health executor -----------------

HEALTH_FIXTURES = Path(__file__).parents[1] / "fixtures" / "system_health"
VALID_HEALTH_BYTES = (HEALTH_FIXTURES / "valid_health.json").read_bytes()
MISSING_RELIABILITY_BYTES = (
    HEALTH_FIXTURES / "missing_reliability.json"
).read_bytes()
MALFORMED_HEALTH_BYTES = (HEALTH_FIXTURES / "malformed_health.json").read_bytes()
VALID_REPORT_BYTES = (HEALTH_FIXTURES / "valid_report.html").read_bytes()
MALICIOUS_REPORT_BYTES = (HEALTH_FIXTURES / "malicious_report.html").read_bytes()
BOM = b"\xef\xbb\xbf"
HEALTH_RUN_ID_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])")


@pytest.fixture
def health_root(tmp_path, monkeypatch):
    """Artifacts are read only through the fixed read-only /mnt/c location."""
    monkeypatch.setattr(
        health_module, "HOST_REPORT_DIR_WSL", str(tmp_path), raising=False
    )
    monkeypatch.setattr(
        actions_module, "HOST_REPORT_DIR_WSL", str(tmp_path), raising=False
    )
    return tmp_path


def _install_health_host(
    host,
    root,
    *,
    json_bytes=None,
    html_bytes=None,
    exec_error=None,
    exit_code=0,
    cleanup_error=None,
):
    """Mock the fixed host wrapper plus its fixed cleanup call."""
    commands = []

    def side_effect(tool, arguments, *args, **kwargs):
        commands.append((tool, dict(arguments)))
        command = arguments.get("command", "")
        if "-NoReliabilityMonitor" not in command:
            if cleanup_error is not None:
                return _marked({"status": "error", "error": cleanup_error})
            return _marked({"status": "ok", "removed": True})

        match = HEALTH_RUN_ID_RE.search(command)
        assert match, "the wrapper must carry a generated 32-hex run id"
        run_id = match.group(0)
        if json_bytes is not None:
            (root / f"{run_id}.json").write_bytes(json_bytes)
        if html_bytes is not None:
            (root / f"{run_id}.html").write_bytes(html_bytes)
        if exec_error is not None:
            return _marked(
                {
                    "status": "error",
                    "error": exec_error,
                    "reason": exec_error,
                    "run_id": run_id,
                    "exit_code": exit_code,
                }
            )
        return _marked(
            {
                "status": "ok",
                "run_id": run_id,
                "exit_code": exit_code,
                "json_exists": json_bytes is not None,
                "html_exists": html_bytes is not None,
            }
        )

    host.side_effect = side_effect
    return commands


def _execution_commands(commands):
    return [
        (tool, arguments)
        for tool, arguments in commands
        if "-NoReliabilityMonitor" in arguments.get("command", "")
    ]


def _health_result(reviewed_actions):
    return _run(reviewed_actions.execute_system_health_check())


def test_system_health_executor_takes_no_parameters(reviewed_actions):
    method = reviewed_actions.execute_system_health_check

    assert list(inspect.signature(method).parameters) == []


def test_system_health_uses_one_fixed_wrapper_without_interpolation(
    reviewed_actions, host, health_root
):
    commands = _install_health_host(
        host,
        health_root,
        json_bytes=VALID_HEALTH_BYTES,
        html_bytes=VALID_REPORT_BYTES,
    )

    first = _health_result(reviewed_actions)
    second = _health_result(reviewed_actions)

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    execution = _execution_commands(commands)
    assert len(execution) == 2
    first_tool, first_arguments = execution[0]
    second_tool, second_arguments = execution[1]
    assert first_tool == second_tool == "PowerShell"
    assert set(first_arguments) <= {"command", "timeout"}
    assert first_arguments["timeout"] == health_module.WRAPPER_TIMEOUT_S
    assert second_arguments["timeout"] == health_module.WRAPPER_TIMEOUT_S

    script = first_arguments["command"]
    assert health_module.HOST_SCRIPT_PATH in script
    assert health_module.HOST_REPORT_DIR in script
    assert health_module.HEALTH_SCRIPT_SHA256 in script
    assert "-NoReliabilityMonitor" in script
    assert HEALTH_RUN_ID_RE.search(script)
    for forbidden in (SECRET, SECRET_PATH, "user@example.test", "TEST\\user"):
        assert forbidden not in script

    normalized_first = HEALTH_RUN_ID_RE.sub("<RUN_ID>", script)
    normalized_second = HEALTH_RUN_ID_RE.sub(
        "<RUN_ID>", second_arguments["command"]
    )
    assert normalized_first == normalized_second

    with pytest.raises(TypeError):
        _run(reviewed_actions.execute_system_health_check("Printer"))


@pytest.mark.parametrize(
    "json_bytes",
    [
        pytest.param(VALID_HEALTH_BYTES, id="utf8"),
        pytest.param(BOM + VALID_HEALTH_BYTES, id="utf8-bom"),
    ],
)
def test_system_health_normalizes_and_recomputes_the_valid_report(
    reviewed_actions, host, health_root, json_bytes
):
    commands = _install_health_host(
        host, health_root, json_bytes=json_bytes, html_bytes=VALID_REPORT_BYTES
    )

    result = _health_result(reviewed_actions)

    assert result["status"] == "ok"
    assert result["action_id"] == "system_health_check"
    assert result["changed"] is False
    assert result["verification"] == "reported"
    assert result["health"]["status"] == "fail"
    assert result["health"]["score"] == 80  # recomputed; the host claimed 70
    assert result["health"]["counts"] == {
        "pass": 1,
        "warn": 1,
        "fail": 1,
        "info": 1,
        "skip": 1,
    }
    assert result["health"]["confidence"] == "reduced"
    statuses = [check["status"] for check in result["checks"]]
    assert len(statuses) == 5
    assert set(statuses) == {"pass", "warn", "fail", "skip", "info"}
    assert result["reliability"]["available"] is True
    assert result["reliability"]["summary"]["failuresLast7d"] == 3
    assert result["events"]["available"] is True
    assert result["inventory"]["computer"]["name"] == "TEST-PC"
    assert result["inventory"]["user"]["email"] == "user@example.test"
    assert isinstance(result["report_html"], bytes)
    assert b"<html" in result["report_html"].lower()
    assert result["cleanup"]["status"] == "removed"
    assert len(_execution_commands(commands)) == 1  # no blind retry
    assert len(commands) == 2  # one execution wrapper and one fixed cleanup


def test_system_health_reports_missing_reliability_honestly(
    reviewed_actions, host, health_root
):
    _install_health_host(
        host,
        health_root,
        json_bytes=MISSING_RELIABILITY_BYTES,
        html_bytes=VALID_REPORT_BYTES,
    )

    result = _health_result(reviewed_actions)

    assert result["status"] == "ok"
    assert result["reliability"]["available"] is False
    assert result["health"]["confidence"] == "reduced"
    assert "pass" in result["health"]["counts"]


@pytest.mark.parametrize(
    "json_bytes",
    [
        pytest.param(MALFORMED_HEALTH_BYTES, id="truncated"),
        pytest.param(MALFORMED_HEALTH_BYTES + b"\0", id="nul"),
        pytest.param(b"\xff\xfe\x00not-utf8", id="invalid-utf8"),
        pytest.param(b"[]", id="not-an-object"),
        pytest.param(b'{"checks": "not-a-list"}', id="bad-shape"),
        pytest.param(b"", id="empty"),
    ],
)
def test_system_health_malformed_json_fails_closed_without_retry(
    reviewed_actions, host, health_root, json_bytes
):
    commands = _install_health_host(
        host, health_root, json_bytes=json_bytes, html_bytes=VALID_REPORT_BYTES
    )

    result = _health_result(reviewed_actions)

    _assert_sanitized_error(result)
    assert "health" not in result or result.get("health") is None
    assert not isinstance(result.get("report_html"), bytes)
    assert len(_execution_commands(commands)) == 1


def test_system_health_missing_json_is_an_error(
    reviewed_actions, host, health_root
):
    _install_health_host(host, health_root, html_bytes=VALID_REPORT_BYTES)

    result = _health_result(reviewed_actions)

    _assert_sanitized_error(result)
    assert not isinstance(result.get("report_html"), bytes)


@pytest.mark.parametrize(
    "error",
    ["hash-mismatch", "script-missing", "staging-failed", "execution-policy"],
)
def test_system_health_hash_and_staging_failures_are_sanitized(
    reviewed_actions, host, health_root, error
):
    commands = _install_health_host(
        host,
        health_root,
        json_bytes=VALID_HEALTH_BYTES,
        html_bytes=VALID_REPORT_BYTES,
        exec_error=error,
    )

    result = _health_result(reviewed_actions)

    _assert_sanitized_error(result)
    assert "health" not in result or result.get("health") is None
    assert len(_execution_commands(commands)) == 1


def test_system_health_child_timeout_is_reported_without_retry(
    reviewed_actions, host, health_root
):
    commands = _install_health_host(
        host,
        health_root,
        json_bytes=VALID_HEALTH_BYTES,
        html_bytes=VALID_REPORT_BYTES,
        exec_error="timeout",
        exit_code=124,
    )

    result = _health_result(reviewed_actions)

    _assert_sanitized_error(result)
    assert "timeout" in result["reason"].lower()
    assert len(_execution_commands(commands)) == 1


@pytest.mark.parametrize(
    "host_result",
    [
        {"status": "error", "reason": f"{SECRET} {SECRET_PATH} " + "x" * 5000},
        TimeoutError(f"{SECRET} {SECRET_PATH}"),
    ],
)
def test_system_health_transport_timeout_or_exception_is_sanitized(
    reviewed_actions, host, health_root, host_result
):
    if isinstance(host_result, BaseException):
        host.side_effect = host_result
    else:
        host.return_value = host_result

    result = _health_result(reviewed_actions)

    _assert_sanitized_error(result, "x" * 501)
    if isinstance(host_result, BaseException):
        assert host.await_count == 1  # timeout/unknown outcome is never retried
    else:
        commands = [(call.args[0], call.args[1]) for call in host.await_args_list]
        assert len(_execution_commands(commands)) == 1


@pytest.mark.parametrize(
    "html_bytes",
    [
        pytest.param(None, id="missing"),
        pytest.param(MALICIOUS_REPORT_BYTES, id="active-content"),
        pytest.param(b"\xff\xfe<html>", id="invalid-utf8"),
    ],
)
def test_system_health_invalid_html_keeps_the_summary_but_fails_the_report(
    reviewed_actions, host, health_root, html_bytes
):
    _install_health_host(
        host, health_root, json_bytes=VALID_HEALTH_BYTES, html_bytes=html_bytes
    )

    result = _health_result(reviewed_actions)

    assert result["status"] == "partial"
    assert result["health"]["status"] == "fail"
    assert result["health"]["score"] == 80
    assert not isinstance(result.get("report_html"), bytes)
    assert isinstance(result.get("cleanup"), dict)
    assert result["cleanup"]["status"] in {"removed", "failed"}


def test_system_health_cleanup_failure_is_sanitized_and_does_not_undo_the_report(
    reviewed_actions, host, health_root
):
    commands = _install_health_host(
        host,
        health_root,
        json_bytes=VALID_HEALTH_BYTES,
        html_bytes=VALID_REPORT_BYTES,
        cleanup_error=f"cleanup-failed {SECRET} {SECRET_PATH}",
    )

    result = _health_result(reviewed_actions)

    assert result["status"] == "ok"
    assert isinstance(result["report_html"], bytes)
    assert result["cleanup"]["status"] == "failed"
    assert len(_execution_commands(commands)) == 1
    serialized = json.dumps({key: value for key, value in result.items() if key != "report_html"})
    assert SECRET not in serialized and SECRET_PATH not in serialized
