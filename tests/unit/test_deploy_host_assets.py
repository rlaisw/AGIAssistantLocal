"""Unit: deploy stages the reviewed Windows health script (spec 048, T024).

Red-first: host_assets.py did not exist. Every host path is a tmp_path, so no
Windows host or machine policy is touched.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agentic_rag_mcp.deploy import host_assets


class _Report:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, str]] = []

    def add(self, name: str, status: str = "ok", evidence: str = "") -> None:
        self.events.append((name, status, evidence))


def _source(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "windows" / "health-check.ps1"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"# reviewed read-only health script\n")
    return source, hashlib.sha256(source.read_bytes()).hexdigest()


def _stage(tmp_path: Path, source: Path, digest: str, report: _Report):
    return host_assets.stage_health_script(
        report,
        source=source,
        dest=tmp_path / "host" / "health-check.ps1",
        report_dir=tmp_path / "host" / "reports",
        expected_sha256=digest,
    )


def test_stage_copies_verifies_and_creates_report_dir(tmp_path):
    source, digest = _source(tmp_path)
    report = _Report()

    returned = _stage(tmp_path, source, digest, report)

    dest = tmp_path / "host" / "health-check.ps1"
    assert returned == digest
    assert dest.read_bytes() == source.read_bytes()
    assert (tmp_path / "host" / "reports").is_dir()
    assert not list(dest.parent.glob("*.tmp"))
    names = [name for name, _, _ in report.events]
    assert "host-assets" in names and "host-report-dir" in names
    evidence = " ".join(e for _, _, e in report.events)
    statuses = " ".join(s for _, s, _ in report.events)
    assert digest in evidence and "ok" in statuses


def test_stage_uses_the_pinned_sha_for_the_repo_script(tmp_path):
    report = _Report()

    returned = host_assets.stage_health_script(
        report,
        dest=tmp_path / "health-check.ps1",
        report_dir=tmp_path / "reports",
    )

    assert returned == host_assets.HEALTH_SCRIPT_SHA256


def test_stage_fails_closed_on_source_hash_mismatch(tmp_path):
    source, _ = _source(tmp_path)
    report = _Report()

    with pytest.raises(host_assets.HostAssetError):
        _stage(tmp_path, source, "0" * 64, report)

    assert not (tmp_path / "host").exists()
    assert report.events[-1][0] == "host-assets"
    assert report.events[-1][1] == "failed"


def test_stage_fails_closed_on_write_error(tmp_path, monkeypatch):
    source, digest = _source(tmp_path)
    report = _Report()

    def denied(self, data):
        raise OSError("access denied")

    monkeypatch.setattr(Path, "write_bytes", denied)
    with pytest.raises(host_assets.HostAssetError):
        _stage(tmp_path, source, digest, report)

    assert not (tmp_path / "host" / "health-check.ps1").exists()
    assert not list((tmp_path / "host").glob("*.tmp"))
    assert report.events[-1][1] == "failed"


def test_stage_fails_closed_on_destination_hash_mismatch(tmp_path, monkeypatch):
    source, digest = _source(tmp_path)
    report = _Report()
    calls: list[Path] = []

    def fake_sha(path: Path) -> str:
        calls.append(path)
        return digest if len(calls) == 1 else "0" * 64

    monkeypatch.setattr(host_assets, "_sha256_file", fake_sha)
    with pytest.raises(host_assets.HostAssetError):
        _stage(tmp_path, source, digest, report)

    assert len(calls) == 2
    assert report.events[-1][1] == "failed"


def test_redeploy_stages_before_building_and_fails_closed(monkeypatch):
    from agentic_rag_mcp.deploy import __main__ as cli
    from agentic_rag_mcp.deploy import docker_ops
    from agentic_rag_mcp.deploy.config import DeployConfig

    calls: list[str] = []
    monkeypatch.setattr(
        host_assets, "stage_health_script", lambda report: calls.append("stage")
    )
    monkeypatch.setattr(docker_ops, "build_image", lambda *a, **k: calls.append("build"))
    monkeypatch.setattr(
        docker_ops, "recreate_container", lambda *a, **k: calls.append("run")
    )
    monkeypatch.setattr(docker_ops, "wait_health", lambda: calls.append("wait") or True)
    monkeypatch.setattr(
        cli.tool_sync, "sync_provider", lambda dcfg, report: calls.append("sync")
    )

    assert cli.cmd_redeploy(DeployConfig(), False) == 0
    assert calls == ["stage", "build", "run", "wait", "sync"]

    def fail(report):
        raise host_assets.HostAssetError("boom")

    monkeypatch.setattr(host_assets, "stage_health_script", fail)
    calls.clear()
    assert cli.cmd_redeploy(DeployConfig(), False) == 1
    assert calls == []
