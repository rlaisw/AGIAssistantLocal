"""Unit: the Hermes file-task gate (spec 028, FR-002/003/004/011/014).

Failing-first: written before hermes_gate exists. Covers the quickstart §A
matrix — normalization, containment, op-set allowlist, no-location ask-back,
and the root-override policy (freely settable, containment always against
the active root).
"""

from __future__ import annotations

from agentic_rag_mcp.hermes_gate import (
    gate_task,
    normalize_path,
    to_windows,
)

DEFAULT_ROOT = "/mnt/c/temp"


def norm(token: str, root: str = DEFAULT_ROOT) -> str | None:
    return normalize_path(token, home="/home/administrator", allowed_root=root)


# ---------------------------------------------------------------- A1 normalization

def test_windows_drive_style_normalizes_to_mount():
    assert norm(r"C:\temp\x") == "/mnt/c/temp/x"
    assert norm("c:/TEMP/x") == "/mnt/c/temp/x"          # case-insensitive drive + path
    assert norm("/mnt/c/temp/x") == "/mnt/c/temp/x"      # host style passes through canonical


def test_mixed_separators_and_trailing_slashes_normalize():
    assert norm("C:\\temp/foo\\bar") == "/mnt/c/temp/foo/bar"
    assert norm("C:\\temp\\folder\\") == "/mnt/c/temp/folder"
    assert norm("C:\\temp\\\\deep") == "/mnt/c/temp/deep"


def test_tilde_expands_to_home():
    assert norm("~/Desktop") == "/home/administrator/Desktop"
    assert norm("~") == "/home/administrator"


def test_relative_anchors_to_active_root():
    assert norm("hello_test", root="/mnt/c/temp") == "/mnt/c/temp/hello_test"
    assert norm("./notes.txt") == "/mnt/c/temp/notes.txt"


def test_dotdot_resolves_before_any_check():
    assert norm(r"C:\temp\..\..\Windows") == "/mnt/c/windows"  # drive-root clamp + drvfs lowercase
    assert norm("/mnt/c/temp/../../../etc") == "/etc"


def test_to_windows_display_form():
    assert to_windows("/mnt/c/temp/x") == "C:\\temp\\x"
    assert to_windows("/mnt/d/work") == "D:\\work"


# ---------------------------------------------------------------- A2 containment

def test_trailing_punctuation_is_not_a_false_refusal():
    """Bug fail-to-save-file: 'create a folder probe in C:\temp.' is in-root —
    sentence punctuation must not defeat containment."""
    v = gate_task("create a folder probe_dot in C:\\temp.")
    assert v.decision != "blocked", v.reason
    assert v.normalized_path == "/mnt/c/temp"


def test_trailing_punctuation_does_not_weaken_containment():
    v = gate_task("create a folder probe_dot in C:\\Other.")
    assert v.decision == "blocked"


def test_in_root_operations_pass_the_gate():
    v = gate_task("create a folder C:\\temp\\hello_test and write hello.txt with 'Hello World' in it")
    assert v.decision == "ok", v.reason  # gate verdict: ok to run
    assert v.normalized_path == "/mnt/c/temp/hello_test"


def test_other_drive_blocked():
    v = gate_task("create a file D:\\work\\notes.txt")
    assert v.decision == "blocked"
    assert "D:\\work" not in (v.reason or "")
    assert DEFAULT_ROOT in v.reason


def test_root_and_system_paths_blocked():
    for task in [
        "delete everything in C:\\Windows",
        "read /etc/passwd for me",
        "list the files in /",
    ]:
        v = gate_task(task)
        assert v.decision == "blocked", task
        assert DEFAULT_ROOT in v.reason


def test_traversal_out_of_root_blocked():
    v = gate_task("write a file to C:\\temp\\..\\..\\Windows\\System32\\config.sys")
    assert v.decision == "blocked"
    assert DEFAULT_ROOT in v.reason


# ---------------------------------------------------------------- A3 op-set allowlist

def test_allowed_operations_recognized():
    cases = {
        "create a folder C:\\temp\\demo": "create-dir",
        "mkdir C:\\temp\\demo2": "create-dir",
        "write 'hi' into C:\\temp\\a.txt": "write-file",
        "read C:\\temp\\a.txt": "read-file",
        "list files in C:\\temp": "list-dir",
        "show me what's in C:\\temp": "list-dir",
    }
    for task, op in cases.items():
        v = gate_task(task)
        assert v.operation == op, task
        assert v.decision != "blocked", task


def test_delete_blocked_everywhere_including_inside_root():
    v = gate_task("delete C:\\temp\\old_notes.txt")
    assert v.decision == "blocked"
    assert "v1" in v.reason or "scope" in v.reason.lower()


def test_rename_move_and_bulk_blocked():
    for task in [
        "rename C:\\temp\\a.txt to C:\\temp\\b.txt",
        "move C:\\temp\\a.txt to C:\\temp\\sub\\",
        "clear C:\\temp entirely",
        "rm -rf C:\\temp",
    ]:
        v = gate_task(task)
        assert v.decision == "blocked", task


# ---------------------------------------------------------------- A4 no-location ask-back

def test_no_location_asks_back_and_never_assumes():
    v = gate_task("create notes.txt with hello in it")
    assert v.decision == "blocked"
    assert v.normalized_path is None
    assert "location" in v.reason.lower() or "where" in v.reason.lower()
    assert DEFAULT_ROOT not in (v.normalized_path or "")


def test_no_path_at_all_asks_back():
    v = gate_task("make a folder")
    assert v.decision == "blocked"
    assert v.normalized_path is None


# ---------------------------------------------------------------- A5 root override

def test_root_argument_narrows_containment():
    v = gate_task("write 'x' into C:\\temp\\proj\\a.txt", allowed_root="/mnt/c/temp/proj")
    assert v.decision != "blocked"
    v = gate_task("write 'x' into C:\\temp\\outside.txt", allowed_root="/mnt/c/temp/proj")
    assert v.decision == "blocked"
    assert "/mnt/c/temp/proj" in v.reason


def test_default_root_applies_when_argument_absent():
    v = gate_task("list files in C:\\temp")
    assert v.decision != "blocked"
    v = gate_task("list files in C:\\other")
    assert v.decision == "blocked"


# ---------------------------------------------------------------- windows path extraction

def test_multiple_paths_in_one_task_all_gated():
    v = gate_task("copy C:\\temp\\a.txt into C:\\Windows\\b.txt")
    assert v.decision == "blocked"  # second target outside root
