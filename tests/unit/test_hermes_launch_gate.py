"""Unit: the Hermes program-launch gate (spec 029, FR-003/004/005/011).

Failing-first: written before hermes_launch_gate exists. Covers the research
R6 matrix — name/quoted target extraction with filler stripping, the
executables-only path rule (.exe or bare name; scripts/shortcuts refused),
the no-arguments/no-shell rules, one-target-per-request ask-backs, and the
reason strings the chat relays verbatim.
"""

from __future__ import annotations

from agentic_rag_mcp.hermes_launch_gate import gate_launch


# ---------------------------------------------------------------- name targets

def test_bare_name_launches():
    v = gate_launch("open excel")
    assert v.decision == "ok", v.reason
    assert v.operation == "launch-app"
    assert v.kind == "name"
    assert v.target.lower() == "excel"


def test_name_case_and_fillers_tolerated():
    v = gate_launch("can you please launch Outlook on my Windows computer?")
    assert v.decision == "ok", v.reason
    assert v.kind == "name"
    assert v.target.lower() == "outlook"


def test_question_phrasing_launches_like_imperative():
    v = gate_launch("could you open Notepad?")
    assert v.decision == "ok", v.reason
    assert v.target.lower() == "notepad"


def test_quoted_multiword_name():
    v = gate_launch("open 'Microsoft Excel'")
    assert v.decision == "ok", v.reason
    assert v.kind == "name"
    assert v.target == "Microsoft Excel"


def test_name_with_exe_suffix_allowed():
    v = gate_launch("run notepad.exe")
    assert v.decision == "ok", v.reason
    assert v.kind == "name"


# ---------------------------------------------------------------- path targets

def test_windows_path_exe_ok():
    v = gate_launch(r"run C:\Windows\System32\notepad.exe")
    assert v.decision == "ok", v.reason
    assert v.kind == "path"
    assert v.target == "/mnt/c/windows/system32/notepad.exe"


def test_host_style_path_exe_ok():
    v = gate_launch("launch /mnt/c/tools/mytool.exe")
    assert v.decision == "ok", v.reason
    assert v.kind == "path"
    assert v.target == "/mnt/c/tools/mytool.exe"


def test_path_case_and_mixed_separators_normalize():
    v = gate_launch("run c:/TOOLS\\MyTool.EXE")
    assert v.decision == "ok", v.reason
    assert v.target == "/mnt/c/tools/mytool.exe"


def test_sanitized_task_carries_only_the_target():
    v = gate_launch("please open notepad on my computer")
    assert v.decision == "ok"
    assert "notepad" in (v.sanitized_task or "")
    assert "please" not in (v.sanitized_task or "").lower()
    assert "computer" not in (v.sanitized_task or "").lower()


# ---------------------------------------------------------------- executables-only

def test_script_and_shortcut_paths_blocked():
    for t in [r"run C:\temp\setup.bat", "launch /mnt/c/x/migrate.ps1",
              r"open C:\Users\me\Desktop\shortcut.lnk", r"run C:\temp\tool.cmd",
              r"launch C:\temp\payload.vbs"]:
        v = gate_launch(t)
        assert v.decision == "blocked", t
        assert "executable" in (v.reason or "").lower(), t


def test_non_exe_path_blocked():
    v = gate_launch(r"open C:\temp\readme.txt")
    assert v.decision == "blocked"
    assert "executable" in (v.reason or "").lower()


# ---------------------------------------------------------------- no arguments / no shell

def test_dash_and_slash_flags_blocked():
    for t in ["launch outlook --dangerous-flag", "start notepad /elevate",
              "open notepad -n", "launch chrome verbose=1"]:
        v = gate_launch(t)
        assert v.decision == "blocked", t
        assert "argument" in (v.reason or "").lower(), t


def test_explicit_argument_passing_blocked():
    v = gate_launch(r"open excel with C:\temp\book.xlsx")
    assert v.decision == "blocked"
    assert "argument" in (v.reason or "").lower()


def test_shell_phrasing_blocked():
    for t in ["run a PowerShell command that lists processes",
              "open a command prompt", "run this in the terminal",
              "open cmd.exe"]:
        v = gate_launch(t)
        assert v.decision == "blocked", t
        low = (v.reason or "").lower()
        assert "argument" in low or "shell" in low, t


def test_chaining_characters_blocked():
    for t in ["open notepad; calc", "open notepad | count", "open notepad & calc"]:
        v = gate_launch(t)
        assert v.decision == "blocked", t


def test_smuggled_second_instruction_blocked():
    v = gate_launch("open notepad and also run powershell")
    assert v.decision == "blocked"
    low = (v.reason or "").lower()
    assert "argument" in low or "shell" in low


# ---------------------------------------------------------------- ask-backs (FR-011)

def test_no_target_asks_back():
    for t in ["open it", "launch the file I made", "open the program please", ""]:
        v = gate_launch(t)
        assert v.decision == "blocked", t
        assert v.operation == "ask-back", t
        assert "which" in (v.reason or "").lower(), t


def test_two_targets_ask_back_which_one():
    v = gate_launch("open notepad and calculator")
    assert v.decision == "blocked"
    assert v.operation == "ask-back"
    assert "which" in (v.reason or "").lower()
    assert "one" in (v.reason or "").lower()


def test_or_phrased_two_targets_ask_back():
    v = gate_launch("help to launch Outlook or Excel on my Windows computer")
    assert v.decision == "blocked"
    assert v.operation == "ask-back"
    assert "which" in (v.reason or "").lower()


def test_trailing_period_after_exe_path_tolerated():
    """Bug fail-to-save-file: 'run C:\Windows\System32\notepad.exe.' — the
    sentence period must not defeat the .exe suffix check."""
    v = gate_launch("run C:\\Windows\\System32\\notepad.exe.")
    assert v.decision == "ok", v.reason
    assert v.kind == "path"
    assert v.target.endswith(".exe")


# ------------------------------------------------- mixed launch+file prompts (spec Edge Cases)

def test_mixed_launch_and_file_prompt_launch_side_never_launches():
    """Spec Edge Cases: 'open Notepad and create notes.txt in C:\\temp' —
    the launch lane's verdict on the mixed prompt must block (the path
    target is not an executable); the file part belongs to the file lane."""
    v = gate_launch("open Notepad and create notes.txt in C:\\temp")
    assert v.decision == "blocked"
    assert "executable" in (v.reason or "").lower()
    assert v.sanitized_task is None          # nothing reaches the launcher


def test_mixed_prompt_file_part_is_owned_by_the_file_lane():
    """The file part of the mixed prompt is the file lane's job: through the
    file gate it is a normal in-root write (the node re-phrases each part
    for its own tool per its instructions; the launch gate never executes
    the file part — see the test above)."""
    from agentic_rag_mcp.hermes_gate import gate_task

    v = gate_task("write notes.txt in C:\\temp")
    assert v.decision != "blocked"
    assert "/mnt/c/temp" in (v.normalized_path or "")


def test_launch_plus_gui_followup_splits_not_two_apps():
    """blocked-more-than-one-application-named (2026-11-06): "open chrome and
    type www.google.com" names ONE application plus a desktop followup — the
    gate must not refuse it as two apps; the followup rides on the verdict
    for the agent's WindowsMCP tools, and the launch keeps all scope rules."""
    v = gate_launch("open chrome and type www.google.com")
    assert v.decision == "ok"
    assert v.target == "chrome"
    assert v.desktop_followup is not None and "www.google.com" in v.desktop_followup


def test_default_browser_is_one_compound_target():
    v = gate_launch("open default browser and type www.google.com")
    assert v.decision == "ok"
    assert v.target == "default browser"
    assert v.desktop_followup and "type" in v.desktop_followup


def test_two_real_apps_still_ask_back():
    v = gate_launch("open chrome and firefox")
    assert v.decision == "blocked"
    assert "more than one application" in v.reason
    assert v.desktop_followup is None


def test_followup_does_not_bypass_shell_or_chaining_rules():
    assert gate_launch("open chrome and type x; rm -rf /").decision == "blocked"
    assert gate_launch("open chrome and type powershell trick").decision == "blocked"


def test_comma_list_splits_at_first_gui_verb():
    """typing-search bug (2026-11-06): real chat phrasing uses comma lists —
    'open chrome, open a new tab, type X, type Y' — must split into one
    launch plus the full desktop followup, not phantom app names."""
    v = gate_launch("open chrome, open a new tab, type www.google.com, "
                    "type hong kong hang seng index at search")
    assert v.decision == "ok"
    assert v.target == "chrome"
    assert v.desktop_followup and v.desktop_followup.startswith("open a new tab")
    assert "www.google.com" in v.desktop_followup
    assert "hong kong" in v.desktop_followup


def test_comma_before_verb_splits():
    v = gate_launch("open chrome, type www.google.com")
    assert v.decision == "ok"
    assert v.target == "chrome"
    assert v.desktop_followup == "type www.google.com"


def test_two_launch_targets_comma_list_still_blocked():
    v = gate_launch("open chrome, open edge, type x")
    assert v.decision == "blocked"


def test_gui_only_with_no_app_ask_back():
    v = gate_launch("type hong kong hang seng index at search bar")
    assert v.decision == "blocked"


def test_search_verb_splits_without_conjunction():
    """blocked-…-named-20261108: 'open chrome search hong kong weather' —
    search/find/look up are desktop followups, not second applications."""
    v = gate_launch("open chrome search hong kong weather")
    assert v.decision == "ok"
    assert v.target == "chrome"
    assert v.desktop_followup == "search hong kong weather"


def test_search_tail_rides_with_observe_clause():
    v = gate_launch("open chrome search hong kong weather , "
                    "show me the temperature today")
    assert v.decision == "ok"
    assert v.target == "chrome"
    assert "show me the temperature today" in v.desktop_followup


def test_new_session_browser_context_nouns_are_fillers():
    v = gate_launch("open a new session chrome browser , search hong kong weather")
    assert v.decision == "ok"
    assert v.target == "chrome"


def test_open_search_alone_is_askback_not_phantom_launch():
    v = gate_launch("open search")
    assert v.decision == "blocked"   # bare verb with no launch head -> ask-back
    assert "no application" in (v.reason or "") or "more than one" in (v.reason or "")


def test_search_followup_cannot_bypass_chaining_rule():
    assert gate_launch("open chrome and search x; rm -rf /").decision == "blocked"


def test_control_panel_compound_name_launches():
    """the-launcher-…-at-a-time (2026-11-08): "control panel" is ONE app —
    multiword names must map to their launch target, not MULTI-block."""
    v = gate_launch("open control panel")
    assert v.decision == "ok"
    assert v.target == "control"


def test_compound_app_with_show_me_followup():
    v = gate_launch("open windows control panel , show me network adapter "
                    "configuration, e.g. ip address setting")
    assert v.decision == "ok"
    assert v.target == "control"
    assert v.desktop_followup and v.desktop_followup.startswith("show me")
    assert "ip address setting" in v.desktop_followup


def test_canonical_compound_set_maps():
    for phrase, target in [("file explorer", "explorer"), ("task manager", "taskmgr"),
                           ("device manager", "devmgmt"), ("registry editor", "regedit")]:
        v = gate_launch(f"open {phrase}")
        assert v.decision == "ok" and v.target == target, phrase


def test_unknown_pair_still_multi_asks_back():
    v = gate_launch("open chrome firefox")
    assert v.decision == "blocked"
    assert "more than one application" in v.reason


def test_show_me_verb_splits_on_comma():
    v = gate_launch("open control , show me network adapter configuration")
    assert v.decision == "ok"
    assert v.target == "control"
    assert v.desktop_followup == "show me network adapter configuration"
