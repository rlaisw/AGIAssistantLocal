"""Unit: the Office task gate (spec 030, contract §2).

Failing-first: written before office_gate exists. Covers task-kind
classification, app routing, work-folder containment, prompt-borne
code-execution refusals, recipient rules, and confirmation/cancel
classification — the reason strings the chat relays verbatim.
"""

from __future__ import annotations

from agentic_rag_mcp.office_gate import (
    OP_ASK_BACK, OP_COMPOSE_EMAIL, OP_CANCEL, OP_CONTINUE, OP_DOCUMENT_READ,
    OP_DOCUMENT_WRITE, OP_SEND_CONFIRMATION, gate_office,
)

ROOT = "C:\\OfficeMCP"


# ------------------------------------------------------------- classification

def test_excel_write_classified():
    v = gate_office("open Excel and put 12345 in cell A1", ROOT)
    assert v.decision == "ok", v.reason
    assert v.kind == OP_DOCUMENT_WRITE
    assert v.app == "excel"


def test_cell_followup_infers_excel():
    v = gate_office("also write 'hello' in B2", ROOT)
    assert v.decision == "ok", v.reason
    assert v.app == "excel"
    assert v.kind == OP_DOCUMENT_WRITE


def test_word_write_classified():
    v = gate_office("create a Word document with the text 'hello world'", ROOT)
    assert v.decision == "ok", v.reason
    assert v.app == "word"


def test_powerpoint_slide_classified():
    v = gate_office("add a slide saying 'Q3 results'", ROOT)
    assert v.decision == "ok", v.reason
    assert v.app == "powerpoint"


def test_document_read_classified():
    v = gate_office("what is in cell B2 of the active workbook", ROOT)
    assert v.decision == "ok", v.reason
    assert v.kind == OP_DOCUMENT_READ
    assert v.app == "excel"


def test_outlook_compose_classified():
    v = gate_office("write an email to a@b.com with subject 'test' and body 'hi'", ROOT)
    assert v.decision == "ok", v.reason
    assert v.kind == OP_COMPOSE_EMAIL
    assert v.app == "outlook"


def test_send_with_recipient_is_compose_not_confirmation():
    """FR-009: a 'send' instruction with a recipient composes — it never
    dispatches in the same turn."""
    v = gate_office("send an email to raymond.lai@tvb.com.hk saying 'test Hello World'", ROOT)
    assert v.decision == "ok", v.reason
    assert v.kind == OP_COMPOSE_EMAIL
    assert v.app == "outlook"


def test_confirmation_phrases_classified():
    for t in ["send it", "send it now", "yes", "confirmed", "go ahead",
              "send the email"]:
        v = gate_office(t, ROOT)
        assert v.decision == "ok", t
        assert v.kind == OP_SEND_CONFIRMATION, t


def test_cancel_phrases_classified():
    for t in ["cancel that email", "cancel", "don't send it", "never mind"]:
        v = gate_office(t, ROOT)
        assert v.decision == "ok", t
        assert v.kind == OP_CANCEL, t


# ----------------------------------------------------------------- ask-backs

def test_empty_task_asks_back():
    v = gate_office("", ROOT)
    assert v.decision == "blocked"
    assert v.operation == OP_ASK_BACK
    assert "what" in (v.reason or "").lower()


def test_compose_without_address_asks_back():
    v = gate_office("write an email saying hello", ROOT)
    assert v.decision == "blocked"
    assert v.operation == OP_ASK_BACK
    assert "address" in (v.reason or "").lower()


# --------------------------------------------------------------- containment

def test_bare_filename_ok():
    v = gate_office("create notes.docx with the text 'hi'", ROOT)
    assert v.decision == "ok", v.reason


def test_inside_work_folder_ok():
    v = gate_office("update C:\\OfficeMCP\\report.xlsx cell A1 to 5", ROOT)
    assert v.decision == "ok", v.reason


def test_outside_work_folder_blocked():
    # RETIRED by spec 031: the work folder is a default, not a boundary.
    # Named locations anywhere are accepted; this test now pins that.
    v = gate_office("open C:\\Other\\book.xlsx and write A1", ROOT)
    assert v.decision == "ok", v.reason          # any named location passes (031 FR-001)


def test_named_location_any_drive_accepted():
    """Spec 031 US1: the owner's exact case — a PowerPoint at c:\\temp\\test."""
    v = gate_office("create a PowerPoint file named test1 with the text "
                    "Hello and save it to C:\\temp\\test", ROOT)
    assert v.decision == "ok", v.reason


def test_second_drive_location_accepted():
    v = gate_office("create a Word document with the text 'notes' and save "
                    "it to D:\\projects\\report.docx", ROOT)
    assert v.decision == "ok", v.reason


def test_punctuated_second_drive_path_accepted():
    """The fail-to-save-file tolerance, now location-agnostic (031 FR-007)."""
    v = gate_office("create a file named x and save it to D:\\docs.", ROOT)
    assert v.decision == "ok", v.reason


def test_no_location_uses_default():
    """Unnamed saves keep the default folder (031 FR-002) — the gate passes
    exactly as before; the directive supplies the default downstream."""
    v = gate_office("create a PowerPoint file named plain with the text hi", ROOT)
    assert v.decision == "ok", v.reason


def test_retired_refusal_class_gone():
    """031 contract §1: the out-of-folder refusal class is retired — no gate
    reason mentions it anymore."""
    for t in ["open C:\\Other\\book.xlsx and write A1",
              "edit /mnt/c/Users/me/Desktop/secret.docx",
              "update E:\\remote\\file.xlsx"]:
        v = gate_office(t, ROOT)
        assert "outside the Office work folder" not in (v.reason or ""), t


def test_content_rules_fire_wherever_the_target_lives():
    """031 FR-005: content rules are location-independent — a macro request
    with a D: path, DDE anywhere, formula content, formatting: all still
    blocked with the same reasons as pre-031."""
    assert gate_office("create a macro that formats the sheet in D:\\docs", ROOT).decision == "blocked"
    assert gate_office("enable DDE in E:\\book.xlsx", ROOT).decision == "blocked"
    assert gate_office("put =cmd|'/c calc'!A0 in cell A1 of D:\\b.xlsx", ROOT).decision == "blocked"
    assert gate_office("make A1 bold in D:\\b.xlsx", ROOT).decision == "blocked"


def test_host_style_outside_blocked():
    # RETIRED by spec 031: any named location passes; the work folder is a default
    v = gate_office("edit /mnt/c/Users/me/Desktop/secret.docx", ROOT)
    assert v.decision == "ok", v.reason


# --------------------------------------------------- code-execution refusals

def test_macro_request_blocked():
    v = gate_office("create a macro that formats the sheet", ROOT)
    assert v.decision == "blocked"
    assert "literal" in (v.reason or "").lower()


def test_dde_request_blocked():
    v = gate_office("enable DDE in the workbook", ROOT)
    assert v.decision == "blocked"


def test_external_formula_content_blocked():
    v = gate_office("put =cmd|'/c calc'!A0 in cell A1", ROOT)
    assert v.decision == "blocked"
    assert "literal" in (v.reason or "").lower()


def test_vba_script_request_blocked():
    v = gate_office("run a VBA script on the active workbook", ROOT)
    assert v.decision == "blocked"


# ------------------------------------------------------ mailbox destruction

def test_delete_emails_blocked():
    for t in ["delete my emails", "clear everything in the Inbox",
              "delete the mail folder"]:
        v = gate_office(t, ROOT)
        assert v.decision == "blocked", t
        assert "mailbox" in (v.reason or "").lower() or "scope" in (v.reason or "").lower()


def test_continue_phrases_classified():
    """FR-005: a 'continue' request resumes an interrupted sequence."""
    for t in ["continue", "resume", "keep going", "go on", "finish the rest",
              "do the rest"]:
        v = gate_office(t, ROOT)
        assert v.decision == "ok", t
        assert v.kind == OP_CONTINUE, t


# ---------------------------------------- mixed-lane prompts (spec Edge Cases)

def test_mixed_office_and_file_prompt_each_lane_owns_its_part():
    """Spec Edge Cases: a mixed prompt splits per lane — the office gate rules
    the Office part (in-folder literal write); the file lane owns the file
    part. The node passes each tool only its own part of the request."""
    v = gate_office("open Excel and put 5 in cell A1", ROOT)
    assert v.decision == "ok", v.reason
    assert v.app == "excel"
    from agentic_rag_mcp.hermes_gate import gate_task
    fv = gate_task("create a folder demo in C:\\temp")
    assert fv.decision != "blocked"
    assert "/mnt/c/temp" in (fv.normalized_path or "")


def test_work_folder_named_with_sentence_punctuation_is_accepted():
    """Bug fail-to-save-file: the user's exact retry — '…save it to
    C:\OfficeMCP.' names the work folder; the trailing period must not
    refuse it."""
    v = gate_office("create a PowerPoint file named test1 with the text "
                    "Hello and save it to C:\\OfficeMCP.", ROOT)
    assert v.decision == "ok", v.reason


def test_trailing_punctuation_does_not_weaken_office_containment():
    # RETIRED by spec 031: containment is gone; the punctuation tolerance
    # (fail-to-save-file) still applies — the punctuated path PASSES.
    v = gate_office("open C:\\Other. and write A1", ROOT)
    assert v.decision == "ok", v.reason


def test_formatting_requests_blocked():
    """Owner decision (clarify pass 2): v1 writes literal content only —
    formatting requests get an honest out-of-scope notice, not a silent
    formatting pass."""
    for t in ["make A1 bold", "color the header red",
              "set a number format on cell B2",
              "adjust the column widths", "make the title font bigger"]:
        v = gate_office(t, ROOT)
        assert v.decision == "blocked", t
        assert "formatting" in (v.reason or "").lower(), t


def test_document_destructive_inside_sandbox_allowed():
    """Spec Clarifications: document edits inside the work folder are the sandbox."""
    v = gate_office("delete row 5 in the active workbook", ROOT)
    assert v.decision == "ok", v.reason
