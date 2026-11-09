"""Unit: the run-command gate (spec 033, FR-001/002/003 + tool contract).

Failing-first: written before hermes_run_gate exists. The allowlist is the
ONLY route from user text to a shell command — this matrix pins every intent
mapping, every refusal class (with the allowlist shown), the one-command rule,
and the single-simple-target charset.
"""

from __future__ import annotations

from agentic_rag_mcp.hermes_run_gate import gate_run_command

ALLOW = ("ipconfig, systeminfo, tasklist, whoami, hostname, "
         "ping <host>, nslookup <host>, tracert <host>")


def ok(v, command=None, target=None):
    return (v.decision == "ok" and v.command == command
            and v.target == target and v.reason is None)


# ------------------------------------------------------------------ mapping

def test_ip_address_phrases_map_to_ipconfig():
    for t in ["show my windows current ip address", "what is my ip",
              "run ipconfig", "ip config", "show my ip address for me"]:
        v = gate_run_command(t)
        assert ok(v, "ipconfig"), (t, v)


def test_powershell_framing_still_maps_when_a_listed_intent_exists():
    # FR-009: "powershell"-phrased requests that map to a listed command
    # route here — the framing word must not refuse the request
    v = gate_run_command("use windows-mcp powershell, show my windows current ip address")
    assert ok(v, "ipconfig"), v


def test_systeminfo_phrases():
    for t in ["show system info", "system information please", "run systeminfo"]:
        assert ok(gate_run_command(t), "systeminfo"), t


def test_tasklist_phrases():
    for t in ["list the running processes", "task list", "what's running on my pc",
              "show the running tasks", "run tasklist"]:
        assert ok(gate_run_command(t), "tasklist"), t


def test_identity_phrases():
    assert ok(gate_run_command("who am i"), "whoami")
    assert ok(gate_run_command("what's my computer name"), "hostname")
    assert ok(gate_run_command("run hostname"), "hostname")


def test_targeted_with_one_simple_target():
    assert ok(gate_run_command("ping 8.8.8.8"), "ping", "8.8.8.8")
    assert ok(gate_run_command("can you ping google.com"), "ping", "google.com")
    assert ok(gate_run_command("nslookup google.com"), "nslookup", "google.com")
    assert ok(gate_run_command("dns lookup for example.com"), "nslookup", "example.com")
    assert ok(gate_run_command("tracert to bbc.co.uk"), "tracert", "bbc.co.uk")
    assert ok(gate_run_command("ping my-host.example-1.com for me"), "ping",
              "my-host.example-1.com")


# ------------------------------------------------------------------ refusals

def _blocked(v):
    return v.decision == "blocked" and v.reason is not None


def test_cmdlets_refused_with_list():
    v = gate_run_command("run Get-NetIPAddress")
    assert _blocked(v) and v.command is None
    assert "not on the run-command allowlist" in v.reason
    assert ALLOW in v.reason


def test_destructive_and_state_changing_verbs_refused():
    for t in ["execute del C:\\temp\\*.txt", "shutdown the computer",
              "add a registry key with reg add", "run netsh interface ip set address",
              "format D:", "taskkill /im chrome.exe", "remove-item C:\\temp\\x",
              "run cmd", "copy a.txt b.txt"]:
        v = gate_run_command(t)
        assert _blocked(v) and v.command is None, (t, v)
        assert "not on the run-command allowlist" in v.reason, t


def test_flags_refused():
    v = gate_run_command("run tasklist /v")
    assert _blocked(v) and v.command is None
    assert "flags" in v.reason.lower() and ALLOW in v.reason


def test_pipes_redirects_separators_chains_refused():
    for t in ["ipconfig | clip", "ping 8.8.8.8 && shutdown",
              "ipconfig > out.txt", "ping 8.8.8.8; nslookup a.com",
              "ipconfig >> log.txt", "run %PATH%", "ping $(host)"]:
        v = gate_run_command(t)
        assert _blocked(v) and v.command is None, (t, v)


def test_quoting_smuggles_refused():
    for t in ['run "ipconfig -all"', "ping '8.8.8.8'", "run `ipconfig`"]:
        assert _blocked(gate_run_command(t)), t


def test_bare_command_with_dotted_argument_refused():
    v = gate_run_command("ipconfig example.com")
    assert _blocked(v) and v.command is None
    assert "no arguments" in v.reason.lower()


def test_mixed_allowed_plus_refused_is_blocked_wholesale():
    # spec US2 scenario 3: the refused part never executes and its refusal is
    # reported — v1 refuses the whole mixed prompt with the element named
    v = gate_run_command("ipconfig and run format D:")
    assert _blocked(v) and v.command is None
    assert "format" in v.reason and "not on the run-command allowlist" in v.reason


def test_extra_token_after_target_refused():
    v = gate_run_command("nslookup a b")
    assert _blocked(v)
    assert "exactly one" in v.reason.lower()


# ------------------------------------------------------------------ ask-backs

def test_two_commands_ask_back():
    for t in ["ipconfig and tasklist", "what's my ip and my hostname"]:
        v = gate_run_command(t)
        assert v.decision == "ask-back", (t, v)
        assert "one command per request" in v.reason and ALLOW in v.reason


def test_unmapped_request_asks_back_offering_the_list():
    v = gate_run_command("check my network health")
    assert v.decision == "ask-back"
    assert ALLOW in v.reason


def test_targeted_without_target_asks_back():
    v = gate_run_command("ping")
    assert v.decision == "ask-back"
    assert "host" in v.reason.lower()


def test_empty_task_asks_back():
    assert gate_run_command("").decision == "ask-back"
    assert gate_run_command("   ").decision == "ask-back"
