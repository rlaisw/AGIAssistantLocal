"""Spec 023: the deploy run-command carries the documents mount (V1).

The run-command string IS the FR-004 artifact — asserting it here makes
mount survival regression-proof without a live docker.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agentic_rag_mcp.deploy import docker_ops


class _Report:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def add(self, step: str, evidence: str = "") -> None:
        self.events.append((step, evidence))


def test_recreate_run_command_carries_documents_mount():
    report = _Report()
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=900):
        calls.append(cmd)
        class P:
            returncode = 0
            stdout = "container-id-abc"
            stderr = ""
        return P()

    with mock.patch.object(docker_ops, "_run", side_effect=fake_run):
        docker_ops.recreate_container("agentic-rag", "agentic-rag-mcp:latest", report)

    home = os.path.expanduser("~")
    run_cmd = next(c for c in calls if c[:3] == ["docker", "run", "-d"])
    volumes = [run_cmd[i + 1] for i, a in enumerate(run_cmd) if a == "-v"]

    # V1a: the documents mount (FR-001)
    assert f"{home}/agentic-rag-docs:/data/rag-docs" in volumes, volumes
    # V1b: the pre-existing mounts survive the refactor (FR-005)
    assert f"{home}/.config/agentic-rag-mcp:/root/.config/agentic-rag-mcp" in volumes
    assert f"{home}/.cache/huggingface:/root/.cache/huggingface" in volumes
    assert any(v.endswith(":/opt/ppt-master") for v in volumes)
    # exactly six mounts — no duplicates; the fifth is office-x1's
    # read-only Windows drive (the REPLACED: probe), the sixth is the
    # browser-lane scripted registry (chrome-not-desktop-automation, 2026-11-11)
    assert len(volumes) == 6, volumes
    assert "/mnt/c:/mnt/c:ro" in volumes
    assert "/usr/local/scripts/browser" in " ".join(volumes)

def test_recreate_creates_documents_folder_before_run():
    report = _Report()
    order: list[str] = []

    def fake_run(cmd, timeout=900):
        joined = " ".join(cmd)
        if joined.startswith("mkdir"):
            order.append("mkdir")
        elif joined.startswith("docker run"):
            order.append("run")
        else:
            order.append("other")
        class P:
            returncode = 0
            stdout = "ok"
            stderr = ""
        return P()

    with mock.patch.object(docker_ops, "_run", side_effect=fake_run):
        docker_ops.recreate_container("agentic-rag", "img", report)

    assert "mkdir" in order and "run" in order
    assert order.index("mkdir") < order.index("run"), order
