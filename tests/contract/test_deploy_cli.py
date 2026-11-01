"""Contract: deploy CLI dispatch, dry-run, battery registry, exit codes (spec 011, P03, P11-P15)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentic_rag_mcp.deploy import battery
from agentic_rag_mcp.deploy.__main__ import main
from agentic_rag_mcp.deploy.config import DeployConfig

VENV_PY = "/home/administrator/.local/share/pipx/venvs/agentic-rag-mcp/bin/python"

CONTRACT_SCENARIOS = [
    "health", "tools-surface", "deck-roundtrip", "completion-page",
    "honest-errors", "chat-ui-liveness", "stop-generation",   # spec 027
    "hermes-file-task",                                     # spec 028
    "hermes-launch-app",                                    # spec 029
    "antv-chart", "antv-infographic", "chart-in-deck", "chat-journey",
]


def run_cli(*args, env_extra=None):
    import os
    import tempfile

    env = {k: v for k, v in os.environ.items()
           if not k.startswith("DIFY_")}
    # isolate from the operator's real config.toml (may carry credentials)
    env["HOME"] = tempfile.mkdtemp(prefix="deploy-cli-test-")
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, "-m", "agentic_rag_mcp.deploy", *args],
                          capture_output=True, text=True, timeout=120, env=env)


def test_dry_run_all_commands_touch_nothing():
    for command in ("redeploy", "chatflow", "verify", "cleanup", "all"):
        proc = run_cli(command, "--dry-run")
        assert proc.returncode == 0, (command, proc.stdout, proc.stderr)
        assert "dry-run plan" in proc.stdout
        assert "config:" in proc.stdout
        assert "***" in proc.stdout or "<unset>" in proc.stdout


def test_missing_console_credentials_exit_2():
    proc = run_cli("chatflow", env_extra={"DIFY_CONSOLE_EMAIL": "",
                                          "DIFY_CONSOLE_PASSWORD": ""})
    assert proc.returncode == 2, (proc.stdout, proc.stderr)
    assert "console" in proc.stdout.lower()


def test_registry_matches_contract():
    ids = [name for name, _ in battery.registry()]
    assert ids == CONTRACT_SCENARIOS
    assert [name for name, _ in battery.registry(skip_chat=True)] == CONTRACT_SCENARIOS[:-1]


def test_battery_exit_code_counts_failures(tmp_path, monkeypatch):
    calls = []

    def fake_registry(skip_chat=False):
        return [("ok-one", lambda d: (True, "fine")),
                ("bad-one", lambda d: (False, "broken evidence"))]

    monkeypatch.setattr(battery, "registry", fake_registry)
    monkeypatch.setattr(battery, "_sweep", lambda notes: notes.append("swept"))
    dcfg = DeployConfig()
    results, cleanup = battery.run_battery(dcfg)
    assert [(n, ok) for n, ok, _ in results] == [("ok-one", True), ("bad-one", False)]
    assert cleanup == ["swept", "swept"]
    failed = [n for n, ok, _ in results if not ok]
    assert failed == ["bad-one"]  # exit-code semantics: count of failures


def test_teardown_sweeps_verify_projects(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    (root / "verify_123").mkdir(parents=True)
    (root / "verify_456").mkdir(parents=True)
    (root / "real_deck_1").mkdir(parents=True)
    monkeypatch.setattr(battery, "projects_roots", lambda: [root])
    notes = []
    battery._sweep(notes)
    assert not (root / "verify_123").exists()
    assert not (root / "verify_456").exists()
    assert (root / "real_deck_1").exists()  # non-battery projects untouched
    assert sorted(notes) == ["swept verify_123", "swept verify_456"]


def test_chat_journey_skips_honestly_without_key():
    ok, evidence = battery.scenario_chat_journey(DeployConfig())
    assert ok is True
    assert "no DIFY_API_KEY" in evidence
    assert "skipped" in evidence


def test_config_error_exit_path(monkeypatch, tmp_path):
    from agentic_rag_mcp import config as config_mod
    from agentic_rag_mcp.config import Config

    def empty_config():
        return Config(state_db=tmp_path / "s.sqlite3", vector_dir=tmp_path / "v",
                      decider_enabled=False)

    monkeypatch.setattr(config_mod, "load_config", empty_config)
    import os

    for var in ("DIFY_CONSOLE_EMAIL", "DIFY_CONSOLE_PASSWORD"):
        os.environ.pop(var, None)
    assert main(["chatflow"]) == 2  # in-process; the subprocess test covers exit-code plumbing


def test_cleanup_prunes_old_projects_keeps_recent(tmp_path, monkeypatch):
    import os
    import time

    from agentic_rag_mcp.deploy import battery

    root = tmp_path / "projects"
    old = root / "deck_old"
    recent = root / "deck_recent"
    verify = root / "verify_123"
    for d in (old, recent, verify):
        d.mkdir(parents=True)
        (d / "exports").mkdir()
        (d / "exports" / "x.pptx").write_bytes(b"PK")
    past = time.time() - 40 * 86400
    os.utime(old / "exports" / "x.pptx", (past, past))
    monkeypatch.setattr(battery, "projects_roots", lambda: [root])

    removed = battery.prune_old_projects(30)
    assert removed == ["deck_old"]
    assert not old.exists()
    assert recent.exists() and verify.exists()  # recent + battery projects untouched

    dry = battery.prune_old_projects(30, dry=True)
    assert dry == []  # nothing left to remove


def test_cleanup_zero_retention_keeps_everything(tmp_path, monkeypatch):
    from agentic_rag_mcp.deploy import battery

    root = tmp_path / "projects"
    d = root / "deck_forever"
    (d / "exports").mkdir(parents=True)
    (d / "exports" / "x.pptx").write_bytes(b"PK")
    monkeypatch.setattr(battery, "projects_roots", lambda: [root])
    assert battery.prune_old_projects(0) == []  # keep forever
    assert d.exists()


def test_cleanup_cli_dry_run(monkeypatch, tmp_path):
    from agentic_rag_mcp.deploy.__main__ import main

    out = main(["cleanup", "--dry-run", "--retention-days", "30"])
    assert out == 0
