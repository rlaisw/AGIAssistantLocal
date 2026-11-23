"""Stage reviewed host assets for the Windows health check (spec 048, T024).

Copies ``windows/health-check.ps1`` to the fixed host path, verifies the pinned
SHA-256 on both sides, and fails closed without touching machine policy.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ..mcp_action.health import HEALTH_SCRIPT_SHA256

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_SCRIPT = REPO_ROOT / "windows" / "health-check.ps1"
HOST_HEALTH_DIR = Path("/mnt/c/ProgramData/agentic-rag/health")
HOST_SCRIPT = HOST_HEALTH_DIR / "health-check.ps1"
HOST_REPORT_DIR = HOST_HEALTH_DIR / "reports"


class HostAssetError(RuntimeError):
    """Host staging failed; deploy must stop without changing machine policy."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_health_script(
    report,
    *,
    source: Path = SOURCE_SCRIPT,
    dest: Path = HOST_SCRIPT,
    report_dir: Path = HOST_REPORT_DIR,
    expected_sha256: str = HEALTH_SCRIPT_SHA256,
) -> str:
    """Copy the pinned script to the host path and verify both hashes."""
    try:
        source_hash = _sha256_file(source)
        if source_hash != expected_sha256:
            raise HostAssetError(
                f"source hash mismatch: {source_hash} != {expected_sha256}"
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".tmp")
        try:
            tmp.write_bytes(source.read_bytes())
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
        dest_hash = _sha256_file(dest)
        if dest_hash != expected_sha256:
            raise HostAssetError(
                f"destination hash mismatch: {dest_hash} != {expected_sha256}"
            )
    except HostAssetError as exc:
        report.add("host-assets", "failed", evidence=str(exc))
        raise
    except OSError as exc:
        report.add("host-assets", "failed", evidence=f"staging error: {exc}")
        raise HostAssetError(f"staging error: {exc}") from exc
    report.add("host-assets", "ok", evidence=f"sha256={dest_hash} status=staged")
    report.add("host-report-dir", "ok", evidence=f"created {report_dir}")
    return dest_hash
