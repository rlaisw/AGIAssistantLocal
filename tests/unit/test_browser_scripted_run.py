"""Spec 037 — scripted run suite (task T004): registry validation, ask-back
honesty, checkpoint verification, abort naming the failed step."""

from __future__ import annotations

import pytest

from agentic_rag_mcp.browser_lanes.scripted_run import (
    ScriptNotFound,
    ScriptRegistry,
    validate_script_file,
    verify_steps,
)


def _write(tmp_path, name, body, headers=""):
    f = tmp_path / f"{name}.py"
    f.write_text(f"""# name: {name}
# version: 1
# params: {{"url": "the page to open"}}
# expect: ["page loaded", "title read"]
{headers}
{body}
""")
    return f


class TestRegistryValidation:
    def test_ok_script_loads(self, tmp_path):
        f = _write(tmp_path, "check_page_title", "print('body')")
        script = validate_script_file(f)
        assert script["name"] == "check_page_title"
        assert script["version"] == 1
        assert script["params"] == {"url": "the page to open"}
        assert script["expect"] == ["page loaded", "title read"]

    def test_name_mismatch_rejected(self, tmp_path):
        f = _write(tmp_path, "mismatch", "print('x')")
        f2 = f.with_name("renamed.py")
        f.rename(f2)  # filename says 'renamed', header says 'mismatch'
        with pytest.raises(ValueError, match="name"):
            validate_script_file(f2)

    def test_missing_expect_rejected(self, tmp_path):
        f = tmp_path / "no_expect.py"
        f.write_text("# name: no_expect\n# version: 1\n# params: {}\nprint(1)\n")
        with pytest.raises(ValueError, match="expect"):
            validate_script_file(f)

    def test_credential_literal_rejected(self, tmp_path):
        f = _write(tmp_path, "creds_inside",
                   'PASSWORD = "hunter2-secret"\nprint(1)')
        with pytest.raises(ValueError, match="credential"):
            validate_script_file(f)

    def test_machine_path_rejected(self, tmp_path):
        f = _write(tmp_path, "machiney",
                   'OUT = "C:\\\\Users\\\\rlwc145\\\\shots"\nprint(1)')
        with pytest.raises(ValueError, match="machine-specific"):
            validate_script_file(f)

    def test_registry_loads_only_valid(self, tmp_path):
        _write(tmp_path, "good_one", "print(1)")
        bad = tmp_path / "bad_name.py"
        bad.write_text("# name: bad-name!\n# version: 1\n# params: {}\n")
        reg = ScriptRegistry(tmp_path)
        assert "good_one" in reg.names()
        with pytest.raises(ScriptNotFound):
            reg.get("bad_name")


class TestArgsValidation:
    def _registry(self, tmp_path):
        _write(tmp_path, "check_page_title", "print(1)")
        return ScriptRegistry(tmp_path)

    def test_missing_slot_ask_back(self, tmp_path):
        reg = self._registry(tmp_path)
        out = reg.resolve_args("check_page_title", {})
        assert out["status"] == "ask-back"
        assert "{{url}}" in out["reason"]

    def test_extra_arg_named(self, tmp_path):
        reg = self._registry(tmp_path)
        out = reg.resolve_args("check_page_title",
                               {"url": "http://x", "extra": 1})
        assert out["status"] == "ask-back" and "extra" in out["reason"]

    def test_ok_args(self, tmp_path):
        reg = self._registry(tmp_path)
        out = reg.resolve_args("check_page_title", {"url": "http://x"})
        assert out["status"] == "ok" and out["args"]["url"] == "http://x"

    def test_unknown_script_not_found(self, tmp_path):
        reg = self._registry(tmp_path)
        with pytest.raises(ScriptNotFound):
            reg.get("ghost")


class TestCheckpointVerify:
    def test_all_pass(self):
        steps = [{"step": 1, "ok": True, "summary": "page loaded"},
                 {"step": 2, "ok": True, "summary": "title read: Home"}]
        out = verify_steps(steps, ["page loaded", "title read"])
        assert out["status"] == "completed" and out["completed_steps"] == 2

    def test_failed_checkpoint_aborts_naming_step(self):
        steps = [{"step": 1, "ok": True, "summary": "page loaded"},
                 {"step": 2, "ok": False, "summary": "no such title"}]
        out = verify_steps(steps, ["page loaded", "title read"])
        assert out["status"] == "aborted"
        assert "2" in out["reason"] and "title read" in out["reason"]

    def test_count_mismatch_aborts(self):
        steps = [{"step": 1, "ok": True, "summary": "page loaded"}]
        out = verify_steps(steps, ["page loaded", "title read"])
        assert out["status"] == "aborted"

    def test_error_step_never_passes(self):
        steps = [{"step": 1, "ok": False, "summary": "crashed"}]
        out = verify_steps(steps, ["crashed"])
        assert out["status"] == "aborted"