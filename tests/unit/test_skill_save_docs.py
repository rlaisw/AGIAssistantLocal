"""no-reusable-skill-on-file-do-not-open-word (2026-11-12): the example
record ships on BOTH skill surfaces so the agent copies the shape instead
of guessing keys (the first attempt used 'steps' for 'workflow')."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_server_docstring_has_example():
    src = (REPO / "src" / "agentic_rag_mcp" / "server.py").read_text()
    assert '"name":"launch_and_type"' in src
    assert "fix them all in the next call" in src


def test_dsl_description_has_example():
    yml = (REPO / "dify" / "AGIAssistant" / "AGI_Assistant.yml").read_text()
    assert '"name":"launch_and_type"' in yml
    assert "fix all in the next call" in yml
