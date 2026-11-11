"""Docker stack operations + version detection (spec 011, R6)."""

from __future__ import annotations

import json
import subprocess
import time

import httpx

REPO_ROOT = subprocess.run(  # noqa: S603 — static path
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
).stdout.strip() or "."

MOUNTS = [
    ("~/.config/agentic-rag-mcp", "/root/.config/agentic-rag-mcp"),
    ("~/.cache/huggingface", "/root/.cache/huggingface"),
    ("~/agentic-rag-docs", "/data/rag-docs"),  # spec 023: operator documents
    # office-x1 (spec 031, 2026-11-11): read-only Windows drive so the
    # office lane's pre-existence probe can stat user-named C:\ targets
    # (the REPLACED: attestation). RO by design — the sidecar never writes
    # files itself; the agent does, host-side.
    ("/mnt/c", "/mnt/c:ro"),
]
_PPT_MOUNT = ("ppt-master", "/opt/ppt-master")  # repo-relative (spec 009)


def _run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def build_image(image: str, report) -> None:
    import os

    env = {**os.environ, "DOCKER_BUILDKIT": "0"}  # legacy builder — BuildKit hangs on this docker version
    proc = subprocess.run(
        ["docker", "build", "-f", "dify/docker/mcp-server/Dockerfile",
         "-t", image, REPO_ROOT],
        capture_output=True, text=True, timeout=1800, env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"image build failed: {(proc.stderr or proc.stdout)[-400:]}")
    report.add("build-image",
                evidence=proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else image)


def recreate_container(container: str, image: str, report) -> None:
    import os

    home = os.path.expanduser("~")
    # spec 023: the documents folder is operator-owned — pre-create it so
    # Docker's root-owned auto-create never happens (research R2)
    docs_dir = os.path.join(home, "agentic-rag-docs")
    _run(["mkdir", "-p", docs_dir])
    mounts = [
        (host.replace("~", home), dest) for host, dest in MOUNTS
    ] + [(os.path.join(REPO_ROOT, _PPT_MOUNT[0]), _PPT_MOUNT[1])]
    _run(["docker", "rm", "-f", container])
    run_cmd = [
        "docker", "run", "-d", "--name", container,
        "--network", "docker_default",
        *[
            flag
            for host, dest in mounts
            for flag in ("-v", f"{host}:{dest}")
        ],
        "-p", "28080:28080", "--restart", "always", image,
    ]
    proc = _run(run_cmd)
    if proc.returncode != 0:
        raise RuntimeError(f"container recreate failed: {(proc.stderr or proc.stdout)[-400:]}")
    _run(["docker", "network", "connect", "docker_ssrf_proxy_network", container])
    report.add("recreate-container", evidence=proc.stdout.strip()[:12])


def wait_health(url: str = "http://localhost:28080/healthz",
                timeout_s: float = 120.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=5).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(3)
    return False


def dify_version(api_container: str) -> str | None:
    """DIFY_VERSION env → api pyproject → None (probed in order)."""
    proc = _run(["docker", "exec", api_container, "printenv", "DIFY_VERSION"], timeout=60)
    if proc.stdout.strip():
        return proc.stdout.strip()
    proc = _run(
        ["docker", "exec", api_container, "sh", "-c",
         "grep -o 'version = \"[0-9.]*\"' /app/api/pyproject.toml | head -1 | cut -d'\"' -f2"],
        timeout=60,
    )
    return proc.stdout.strip() or None


def db_query(db_container: str, sql: str) -> str:
    proc = _run(["docker", "exec", db_container, "psql", "-U", "postgres",
                 "-d", "dify", "-t", "-A", "-c", sql], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"db query failed: {(proc.stderr or proc.stdout)[-300:]}")
    return proc.stdout.strip()


def cached_tools(db_container: str, name: str) -> list[str] | None:
    """Tool names from Dify's provider cache; None when the provider is absent."""
    try:
        raw = db_query(db_container,
                       f"SELECT tools FROM tool_mcp_providers WHERE name = '{name}';")
        if not raw:
            return None
        return [t.get("name") for t in json.loads(raw)]
    except (RuntimeError, json.JSONDecodeError):
        return None


def update_cached_tools(db_container: str, name: str, tools_json: str) -> None:
    escaped = tools_json.replace("'", "''")
    proc = _run(["docker", "exec", db_container, "psql", "-U", "postgres",
                 "-d", "dify", "-v", "ON_ERROR_STOP=1", "-c",
                 f"UPDATE tool_mcp_providers SET tools = '{escaped}', "
                 f"updated_at = now() WHERE name = '{name}';"], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"tool cache update failed: {(proc.stderr or proc.stdout)[-300:]}")
