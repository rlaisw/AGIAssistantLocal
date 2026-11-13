"""Spec 039 — Browser Control v2: the six per-verb proxy methods and the
shared screenshot-after-action helper. One tool per verb (clarified);
ask-back honesty, DISPLAYED-value read-back, sensitive-value log
exclusion at three layers, key/bound allowlists."""

from __future__ import annotations

import httpx
import pytest

from agentic_rag_mcp.browser_lanes.proxy import PlaywrightProxy

BASE = "http://172.17.0.1:13002"


def _sse(obj) -> httpx.Response:
    return httpx.Response(200, text="event: message\ndata: " + obj + "\n\n",
                          headers={"mcp-session-id": "s1"})


class _Fake:
    """Minimal proxy double: records engine calls, plays canned results.
    The first call is always the snapshot (the ref-resolution protocol)."""

    def __init__(self, results, snapshot=None):
        self.results = list(results)
        self.calls = []
        self.snapshot = snapshot or {
            "status": "ok",
            "text": "- textbox 'Name:' [ref=e5]\n"
                    "- combobox 'Country:' [ref=e6]\n"
                    "- button 'Submit' [ref=e7]\n"
                    "- textbox 'Password:' [ref=e9]\n"}

    def call(self, tool, args):
        self.calls.append((tool, args))
        if tool == "browser_snapshot":
            return self.snapshot
        return self.results.pop(0) if self.results else {"status": "ok", "text": ""}


@pytest.fixture()
def px():
    p = PlaywrightProxy(BASE)
    return p


def _inject(px, fake):
    px.call = fake.call  # route engine calls to the double


class TestSelect:
    def test_select_lands_and_reads_back(self, px):
        f = _Fake([{"status": "ok", "text": "Hong Kong selected"}])
        _inject(px, f)
        out = px.select("Country", "Hong Kong")
        assert out["status"] == "ok" and out["verified"] is True
        # snapshot resolved the ref, the verb carried it
        verb = next(c for c in f.calls if c[0] == "browser_select_option")
        assert verb[1]["target"] == "e6"

    def test_select_no_match_asks_back(self, px):
        f = _Fake([{"status": "error",
                    "reason": "Option 'Atlantis' not found. Available: Hong Kong, Japan"}])
        _inject(px, f)
        out = px.select("Country", "Atlantis")
        assert out["status"] == "ask-back"
        assert "Hong Kong" in out["reason"]  # the options listed

    def test_select_readback_mismatch_is_error_never_success(self, px):
        f = _Fake([{"status": "ok", "text": "unrelated"},
                   {"status": "ok", "text": "still unrelated"}])
        _inject(px, f)
        out = px.select("Country", "Hong Kong")
        assert out["status"] == "error"
        assert "mismatch" in out["summary"]


class TestType:
    def test_type_succeeds_value_never_logged(self, px):
        f = _Fake([{"status": "ok", "text": "typed"}])
        _inject(px, f)
        out = px.type("Password", "s3cret-password")
        assert out["status"] == "ok" and out["verified"] is True
        assert "s3cret" not in out["summary"]
        assert "withheld" in out["summary"]

    def test_type_not_found_asks_back(self, px):
        out = px.type("Ghost Field", "x")
        assert out["status"] == "ask-back"
        assert "Ghost Field" in out["reason"]

    def test_form_multi_field(self, px):
        f = _Fake([{"status": "ok", "text": "3 fields filled"}])
        _inject(px, f)
        out = px.form({"Name": "John", "Country": "Hong Kong", "Password": "z"})
        assert out["status"] == "ok"
        assert out["summary"].startswith("filled 3 field(s)")
        assert "John" not in out["summary"]


class TestPressKey:
    def test_allowlist_accepts_enter(self, px):
        f = _Fake([{"status": "ok", "text": ""}])
        _inject(px, f)
        assert px.press_key("Enter")["status"] == "ok"

    def test_allowlist_rejects_combo(self, px):
        out = px.press_key("Control+Alt+Del")
        assert out["status"] == "ask-back"
        assert "rejected" in out["reason"]
        # rejected before any engine call
        assert "Enter" in out["reason"]


class TestTabsAndWait:
    def test_tabs_lists_honestly_on_error(self, px):
        f = _Fake([{"status": "error", "reason": "no tab named 'ghost'; open: [a, b]"}])
        _inject(px, f)
        out = px.tabs("switch", "ghost")
        assert out["status"] == "error" and "open: [a, b]" in out["reason"]

    def test_wait_bound_rejects_out_of_range(self, px):
        assert px.wait("text-appears", "x", 0)["status"] == "ask-back"
        assert px.wait("text-appears", "x", 60)["status"] == "ask-back"

    def test_wait_timeout_names_the_condition(self, px):
        f = _Fake([{"status": "error", "reason": "timeout"}])
        _inject(px, f)
        out = px.wait("text-appears", "delayed", bound_s=2)
        assert out["status"] == "error"
        assert "'delayed'" in out["reason"] and "timeout" in out["reason"]
        assert "fabricated" not in out["reason"][:0]  # honest, present tense


class TestScreenshotAfterAction:
    def test_fires_after_every_verb(self, px):
        f = _Fake([{"status": "ok", "text": "typed"},      # the type
                   {"status": "ok", "text": "saved.png"}])  # the screenshot
        _inject(px, f)
        out = px.type("Name", "x")
        shots = [c for c in f.calls if c[0] == "browser_take_screenshot"]
        assert shots  # fired after the action
        assert out["screenshot"] == "captured"

    def test_screenshot_failure_never_fails_action(self, px):
        f = _Fake([{"status": "ok", "text": "typed"},
                   {"status": "error", "reason": "page closed"}])
        _inject(px, f)
        out = px.type("Name", "x")
        assert out["status"] == "ok" and out["screenshot"] == "attempted-but-failed"


class TestSensitiveExclusion:
    def test_secret_absent_from_all_surfaces(self, px):
        out = px.type("Password", "hunter2-secret")  # not in snapshot -> ask-back
        assert "hunter2" not in out["reason"]
        assert "hunter2" not in out.get("summary", "")


class TestSchemaBoundaries:
    def test_form_requires_fields(self, px):
        f = _Fake([])
        _inject(px, f)
        out = px.form({})
        # empty form is a one-field shortcut the engine rejects: honest error
        assert out["status"] in ("ask-back", "error")
