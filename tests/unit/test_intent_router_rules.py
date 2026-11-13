"""Routing rules pins (2026-11-13): the browser-action precedence and the
screenshot-preservation requirement live in the intent_router topic."""

from pathlib import Path

YML = Path(__file__).resolve().parents[2] / "dify" / "AGIAssistant" / "AGI_Assistant.yml"


def _hermes_topic() -> str:
    s = YML.read_text(encoding="utf-8")
    i = s.index("The user asks to create, write, read, or list files")
    return s[i:i + 20000]


def test_browser_action_beats_search_rule():
    topic = _hermes_topic()
    assert "ACTION-IN-BROWSER BEATS SEARCH-FOR-INFORMATION" in topic
    assert "current chrome session" in topic
    assert "create a new api key in current chrome session" in topic


def test_screenshot_step_capture_preserved():
    # owner requirement 2026-11-13: the step-by-step screen capture during
    # browser actions must never be removed
    topic = _hermes_topic()
    assert "SCREENSHOTS step by step" in topic
    assert "always keep that step-by-step screen capture" in topic
