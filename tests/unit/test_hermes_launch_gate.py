"""Unit: the Hermes program-launch gate (spec 029, FR-003/004/005/011).

Failing-first: written before hermes_launch_gate exists. Covers the research
R6 matrix — name/quoted target extraction with filler stripping, the
executables-only path rule (.exe or bare name; scripts/shortcuts refused),
the no-arguments/no-shell rules, one-target-per-request ask-backs, and the
reason strings the chat relays verbatim.
"""

from __future__ import annotations

import pytest

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
    """Bug fail-to-save-file: 'run C:\\Windows\\System32\notepad.exe.' — the
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
    """blocked-more-than-one-application-named (2026-11-06): "open notepad and
    type www.google.com" names ONE application plus a desktop followup — the
    gate must not refuse it as two apps; the followup rides on the verdict
    for the agent's WindowsMCP tools, and the launch keeps all scope rules.
    (no-response-test-playwright 2026-11-11: chrome examples moved to
    TestBrowserFollowupRefusal — browser+followup is a web intent.)"""
    v = gate_launch("open notepad and type www.google.com")
    assert v.decision == "ok"
    assert v.target == "notepad"
    assert v.desktop_followup is not None and "www.google.com" in v.desktop_followup


def test_default_browser_is_one_compound_target():
    # compound parsing holds; browser+followup refuses per spec 037
    v = gate_launch("open default browser and type www.google.com")
    assert v.decision == "blocked"
    assert "browser" in v.reason.lower()
    # a bare default-browser launch stays a clean launch
    v2 = gate_launch("open default browser")
    assert v2.decision == "ok" and v2.target == "default browser"


def test_two_real_apps_still_ask_back():
    v = gate_launch("open chrome and firefox")
    assert v.decision == "blocked"
    assert "more than one application" in v.reason
    assert v.desktop_followup is None


def test_followup_does_not_bypass_shell_or_chaining_rules():
    assert gate_launch("open notepad and type x; rm -rf /").decision == "blocked"
    assert gate_launch("open notepad and type powershell trick").decision == "blocked"


def test_comma_list_splits_at_first_gui_verb():
    """typing-search bug (2026-11-06): real chat phrasing uses comma lists —
    'open chrome, open a new tab, type X, type Y' — must split into one
    launch plus the full desktop followup, not phantom app names."""
    v = gate_launch("open notepad, type www.google.com, "
                    "type hong kong hang seng index at search")
    assert v.decision == "ok"
    assert v.target == "notepad"
    assert v.desktop_followup and v.desktop_followup.startswith("type www.google.com")
    assert "www.google.com" in v.desktop_followup
    assert "hong kong" in v.desktop_followup


def test_comma_before_verb_splits():
    v = gate_launch("open notepad, type www.google.com")
    assert v.decision == "ok"
    assert v.target == "notepad"
    assert v.desktop_followup == "type www.google.com"


def test_two_launch_targets_comma_list_still_blocked():
    v = gate_launch("open chrome, open edge, type x")
    assert v.decision == "blocked"


def test_gui_only_with_no_app_ask_back():
    v = gate_launch("type hong kong hang seng index at search bar")
    assert v.decision == "blocked"


def test_search_verb_splits_without_conjunction():
    """blocked-…-named-20261108: search/find/look up are desktop followups,
    not second applications (notepad example; chrome+search is now the
    spec-037 browser refusal — see TestBrowserFollowupRefusal)."""
    v = gate_launch("open notepad search hong kong weather")
    assert v.decision == "ok"
    assert v.target == "notepad"
    assert v.desktop_followup == "search hong kong weather"


def test_search_tail_rides_with_observe_clause():
    v = gate_launch("open notepad search hong kong weather , "
                    "show me the temperature today")
    assert v.decision == "ok"
    assert v.target == "notepad"
    assert "show me the temperature today" in v.desktop_followup


def test_new_session_browser_context_nouns_are_fillers():
    # fillers still parse to ONE target (chrome) — but browser+search now
    # refuses per spec 037 (the refusal proves the target parsed cleanly)
    v = gate_launch("open a new session chrome browser , search hong kong weather")
    assert v.decision == "blocked"
    assert v.target == "chrome"
    assert "browser" in v.reason.lower()


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


def test_check_verb_splits_and_rides_followup():
    """the-local-agent-blocked-… (2026-11-09): "check" is the natural
    observe companion — "open chrome , check hong kong temperature" must
    split, not MULTI-block."""
    v = gate_launch("help to open notepad , check hong kong temperature today")
    assert v.decision == "ok"
    assert v.target == "notepad"
    assert v.desktop_followup == "check hong kong temperature today"


def test_read_and_tell_me_verbs_split_on_comma():
    v = gate_launch("open control panel , read me the ip address")
    assert v.decision == "ok" and v.target == "control"
    v = gate_launch("open notepad , tell me the weather")
    assert v.decision == "ok" and v.target == "notepad" and v.desktop_followup


def test_check_verb_comma_form_only_unknown_pair_still_multi():
    assert gate_launch("open chrome firefox").decision == "blocked"
    assert gate_launch("open search").decision == "blocked"  # bare-verb protection intact


class TestBrowserFollowupRefusal:
    """no-response-test-playwright (2026-11-11, spec 037): a typing/reading
    followup on a BROWSER is a web intent — the launch lane refuses with an
    honest re-route; it never rides GUI automation into a silent stall."""

    def test_chrome_plus_typing_refused_with_reroute(self):
        from agentic_rag_mcp.hermes_launch_gate import gate_launch
        v = gate_launch("open chrome, type what is hong kong weather today "
                        "at search bar, display hong kong weather")
        assert v.decision == "blocked"
        assert "browser lane" in v.reason or "browser" in v.reason
        assert "re-ask" in v.reason.lower() or "web/browser task" in v.reason

    def test_edge_plus_search_refused(self):
        from agentic_rag_mcp.hermes_launch_gate import gate_launch
        v = gate_launch("open edge and search for the news")
        assert v.decision == "blocked"
        assert v.reason.startswith("Blocked:")

    def test_bare_chrome_launch_still_ok(self):
        # launching the browser itself (no content followup) stays a launch
        from agentic_rag_mcp.hermes_launch_gate import gate_launch
        v = gate_launch("open chrome")
        assert v.decision == "ok"
        assert v.target.lower() == "chrome"
        assert v.desktop_followup is None

    def test_notepad_plus_typing_still_ok_followup(self):
        # non-browser desktop followups keep the 2026-11-06 capability
        from agentic_rag_mcp.hermes_launch_gate import gate_launch
        v = gate_launch("open notepad and type hello world")
        assert v.decision == "ok"
        assert v.desktop_followup and "type" in v.desktop_followup.lower()


class TestMicrosoftFamilyCompounds:
    """the-launch-was-blocked-by-the-local-agent (2026-11-12): 'MS Word'
    parsed as TWO applications (names ['MS','Word']) -> MULTI ask-back on
    the most natural phrasing there is. The compound map now merges the
    Microsoft family; two REAL apps still block."""

    def test_ms_word_with_typing_followup_merges_then_reroutes(self):
        # why-not-officemcp (2026-11-12): the compound merge still applies
        # ('MS Word' -> ONE name 'word'), but Office+typing now REFUSES with
        # the office-lane re-route instead of GUI typing (supersedes the
        # earlier 'launches' pin)
        v = gate_launch("open MS Word, type Hello")
        assert v.target == "word"  # the merge worked
        assert v.decision == "blocked"
        assert "hermes_office_task" in v.reason

    @pytest.mark.parametrize("task,target", [
        ("open MS Word", "word"),
        ("open Microsoft Word", "word"),
        ("open Microsoft Excel", "excel"),
        ("open MS PowerPoint", "powerpoint"),
        ("open ms outlook", "outlook"),
        ("open ms edge", "edge"),
        ("open microsoft teams", "teams"),
        ("open ms paint", "mspaint"),
    ])
    def test_family_phrasings_merge_to_one_app(self, task, target):
        v = gate_launch(task)
        assert v.decision == "ok" and v.target == target

    def test_two_real_apps_still_multi_block(self):
        v = gate_launch("open chrome and firefox")
        assert v.decision == "blocked"
        assert "more than one application" in v.reason


class TestOfficeFollowupReroute:
    """why-not-officemcp (2026-11-12): Office + typing/clicking is a DOCUMENT
    task — the office lane (OfficeMCP COM) serves it with no GUI automation
    and no consent waits (the launch+GUI path measured 196 s). The launch
    lane refuses with the re-route; bare launches and Notepad-class
    followups keep their behavior."""

    @pytest.mark.parametrize("task", [
        "open ms word and type abc hello",
        "open Word, type hello",
        "open excel and click cell A1",
        "open Microsoft PowerPoint and type title",
        "open MS Word, type Hello",
    ])
    def test_office_plus_followup_refused_with_reroute(self, task):
        v = gate_launch(task)
        assert v.decision == "blocked"
        assert "hermes_office_task" in v.reason

    def test_bare_office_launch_still_ok(self):
        v = gate_launch("open word")
        assert v.decision == "ok" and v.target == "word"
        assert v.desktop_followup is None

    def test_notepad_typing_keeps_desktop_followup(self):
        v = gate_launch("open notepad and type hello")
        assert v.decision == "ok" and v.desktop_followup


class TestPhaseScopeOneNoteAccess:
    """owner decision 2026-11-12 ('at this phase ignore OneNote and others'):
    the office lane routes ONLY Word/Excel/PowerPoint/Outlook — OneNote and
    Access stay ORDINARY desktop apps (launch + followup), never refused
    with the office re-route (which would dead-end: the office lane does
    not serve them)."""

    @pytest.mark.parametrize("task", [
        "open OneNote and type hello",
        "open MS OneNote and type notes",
        "open microsoft onenote and type x",
    ])
    def test_onenote_typing_stays_desktop(self, task):
        v = gate_launch(task)
        assert v.decision == "ok" and v.desktop_followup

    def test_access_not_office_refused(self):
        v = gate_launch("open access")
        assert v.decision == "ok" and v.target == "access"
        assert "hermes_office_task" not in (v.reason or "")
