"""Configuration loading for agentic-rag-mcp.

Config file: ~/.config/agentic-rag-mcp/config.toml
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "agentic-rag-mcp"
CONFIG_FILE = CONFIG_DIR / "config.toml"
STATE_DB = CONFIG_DIR / "state.sqlite3"
VECTOR_DIR = CONFIG_DIR / "lancedb"

DEFAULT_CONFIG = """\
# agentic-rag-mcp configuration

[embedding]
model = "all-MiniLM-L6-v2"   # local sentence-transformers model
device = "cpu"

[agent]
max_iterations = 5           # deliberative loop budget (FR-014/FR-017)

[decider]
# System 1 embedded decision node (Laya decision model, ~1.7 GB on first load)
enabled = true               # false => keyword heuristic is primary (provenance: fallback)
model_repo = "convaiinnovations/laya"
model_dir = ""               # optional local checkpoint dir (overrides download)
timeout = 12.0               # seconds; exceeded => fallback (~7.4s warm on ARM CPU)
noul_threshold = 0.5         # P(true) >= threshold => knowledge-base-sufficient

[web]
# order in which providers are tried; providers without config are skipped
fallback_order = ["searxng", "tavily", "exa"]

[web.tavily]
# api_key = ""

[web.exa]
# api_key = ""

[web.searxng]
# url = "http://127.0.0.1:8888"

[web.specialty]
# file = ""                # path to specialty_profiles.json; empty = default
                             # (~/.config/agentic-rag-mcp/specialty_profiles.json)

[web.research]
max_pages = 3                # pages scraped per research call (cap 5)
per_page_chars = 6000        # content bound per page (FR-007)
fetch_timeout_s = 15.0       # per-page fetch timeout
overall_timeout_s = 30.0     # end-to-end bound for a research call (FR-014)
max_concurrent = 4           # parallel page fetches

[features]
graphify = false             # optional graph-search layer

[logging]
# level = "INFO"             # DEBUG|INFO|WARNING|ERROR; LOG_LEVEL env overrides;
                             # invalid values fall back to INFO with a WARNING record
# log_file = ""              # default: <state_db dir>/logs/server.log (persistent,
                             # on the mounted config volume in deployment)
rotation_size_mb = 10.0       # rotate at this size (float — tests can shrink it)
rotation_count = 5           # keep N generations; total cap = size × count

[ppt]
# ppt-master bridge (spec 009): scripts root of the ppt-master clone
# (mounted into the container at /opt/ppt-master; a host path works locally)
scripts_root = "/opt/ppt-master/skills/ppt-master"
projects_root = "/opt/ppt-master/projects"
exports_url_base = "http://localhost:28080/exports"
python = ""                  # interpreter for ppt-master scripts; empty = sys.executable
max_pages = 5                # v1 bound per spec 009
script_timeout_s = 120.0      # per script invocation
retention_days = 0           # 0 = keep exports forever (v1)

[storage]
# state_db / vector_dir default to ~/.config/agentic-rag-mcp/
"""


@dataclass
class Config:
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_device: str = "cpu"
    max_iterations: int = 5
    decider_enabled: bool = True
    decider_model_repo: str = "convaiinnovations/laya"
    decider_model_dir: str = ""
    decider_timeout: float = 12.0
    decider_noul_threshold: float = 0.5
    web_fallback_order: list[str] = field(default_factory=lambda: ["searxng", "tavily", "exa"])
    web_tavily_key: str = ""
    web_exa_key: str = ""
    web_searxng_url: str = ""
    specialty_profiles_file: str = ""
    research_max_pages: int = 6
    research_per_page_chars: int = 6000
    research_fetch_timeout_s: float = 15.0
    research_overall_timeout_s: float = 30.0
    research_max_concurrent: int = 4
    graphify_enabled: bool = False
    log_level: str = "INFO"
    log_file: Path | None = None
    rotation_size_mb: float = 10.0
    rotation_count: int = 5
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8811
    state_db: Path = STATE_DB
    vector_dir: Path = VECTOR_DIR
    ppt_scripts_root: Path = Path("/opt/ppt-master/skills/ppt-master")
    ppt_projects_root: Path = Path("/opt/ppt-master/projects")
    ppt_exports_url_base: str = "http://localhost:28080/exports"
    ppt_python: str = ""
    ppt_max_pages: int = 5
    ppt_script_timeout_s: float = 120.0
    ppt_retention_days: int = 0
    antv_chart_service_url: str = "https://antv-studio.alipay.com/api/gpt-vis"
    antv_chart_timeout_s: float = 30.0
    antv_max_inline_image_bytes: int = 2_097_152
    antv_infographic_max_syntax_bytes: int = 65_536
    antv_infographic_served_root: Path = Path("/opt/ppt-master/projects/infographics")
    # spec 028: Hermes Agent lane — gated Windows file tasks
    # audit_path lives under the volume-backed config tree (~/.config/agentic-rag-mcp,
    # mounted into the sidecar) so the append-only trail survives container
    # recreation / image rebuilds (convergence T022).
    hermes_api_url: str = "http://172.17.0.1:8642"
    hermes_api_key: str = ""
    hermes_timeout_s: float = 300.0
    hermes_allowed_root: Path = Path("/mnt/c/temp")
    hermes_office_root: str = "C:\\OfficeMCP"   # spec 030: gate containment root (Windows style)
    hermes_audit_path: Path = Path("~/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl")
    raw: dict[str, Any] = field(default_factory=dict)


def _get(raw: dict[str, Any], *keys: str, default: Any = None) -> Any:
    node = raw
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def load_config(path: Path | None = None) -> Config:
    path = path or CONFIG_FILE
    raw: dict[str, Any] = {}
    if path.exists():
        raw = tomllib.loads(path.read_text())
    cfg = Config(
        embedding_model=_get(raw, "embedding", "model", default="all-MiniLM-L6-v2"),
        embedding_device=_get(raw, "embedding", "device", default="cpu"),
        max_iterations=int(_get(raw, "agent", "max_iterations", default=5)),
        decider_enabled=bool(_get(raw, "decider", "enabled", default=True)),
        decider_model_repo=_get(raw, "decider", "model_repo", default="convaiinnovations/laya"),
        decider_model_dir=_get(raw, "decider", "model_dir", default=""),
        decider_timeout=float(_get(raw, "decider", "timeout", default=12.0)),
        decider_noul_threshold=float(_get(raw, "decider", "noul_threshold", default=0.5)),
        web_fallback_order=_get(
            raw, "web", "fallback_order", default=["searxng", "tavily", "exa"]
        ),
        web_tavily_key=_get(raw, "web", "tavily", "api_key", default=""),
        web_exa_key=_get(raw, "web", "exa", "api_key", default=""),
        web_searxng_url=_get(raw, "web", "searxng", "url", default=""),
        specialty_profiles_file=_get(raw, "web", "specialty", "file", default=""),
        research_max_pages=min(6, int(_get(raw, "web", "research", "max_pages", default=6))),  # cap 6
        research_per_page_chars=int(_get(raw, "web", "research", "per_page_chars", default=6000)),
        research_fetch_timeout_s=float(_get(raw, "web", "research", "fetch_timeout_s", default=15.0)),
        research_overall_timeout_s=float(_get(raw, "web", "research", "overall_timeout_s", default=30.0)),
        research_max_concurrent=int(_get(raw, "web", "research", "max_concurrent", default=4)),
        graphify_enabled=bool(_get(raw, "features", "graphify", default=False)),
        log_level=os.environ.get("LOG_LEVEL")
        or str(_get(raw, "logging", "level", default="INFO")),
        log_file=Path(str(_get(raw, "logging", "log_file", default=""))).expanduser()
        if _get(raw, "logging", "log_file") else None,
        rotation_size_mb=float(_get(raw, "logging", "rotation_size_mb", default=10.0)),
        rotation_count=int(_get(raw, "logging", "rotation_count", default=5)),
        mcp_host=_get(raw, "server", "host", default="127.0.0.1"),
        mcp_port=int(_get(raw, "server", "port", default=8811)),
        raw=raw,
    )
    cfg.state_db = Path(_get(raw, "storage", "state_db", default=str(STATE_DB))).expanduser()
    cfg.vector_dir = Path(_get(raw, "storage", "vector_dir", default=str(VECTOR_DIR))).expanduser()
    cfg.ppt_scripts_root = Path(
        str(_get(raw, "ppt", "scripts_root", default=str(cfg.ppt_scripts_root)))
    ).expanduser()
    cfg.ppt_projects_root = Path(
        str(_get(raw, "ppt", "projects_root", default=str(cfg.ppt_projects_root)))
    ).expanduser()
    cfg.ppt_exports_url_base = str(
        _get(raw, "ppt", "exports_url_base", default=cfg.ppt_exports_url_base)
    )
    cfg.ppt_python = str(_get(raw, "ppt", "python", default=""))
    cfg.ppt_max_pages = int(_get(raw, "ppt", "max_pages", default=5))
    cfg.ppt_script_timeout_s = float(_get(raw, "ppt", "script_timeout_s", default=120.0))
    cfg.ppt_retention_days = int(_get(raw, "ppt", "retention_days", default=0))
    cfg.antv_chart_service_url = str(
        os.environ.get("ANTV_CHART_SERVICE_URL")
        or _get(raw, "antv", "chart_service_url",
                default=str(cfg.antv_chart_service_url))
    )
    cfg.antv_chart_timeout_s = float(_get(raw, "antv", "chart_timeout_s", default=30.0))
    cfg.antv_max_inline_image_bytes = int(
        _get(raw, "antv", "max_inline_image_bytes", default=2_097_152)
    )
    cfg.antv_infographic_max_syntax_bytes = int(
        _get(raw, "antv", "infographic_max_syntax_bytes", default=65_536)
    )
    default_infographic_root = str(
        Path(str(cfg.ppt_scripts_root)).parent.parent / "projects" / "infographics"
    )
    cfg.antv_infographic_served_root = Path(
        str(_get(raw, "antv", "infographic_served_root", default=default_infographic_root))
    ).expanduser()
    # spec 028: [hermes] api_url / api_key / timeout_s / allowed_root / audit_path
    cfg.hermes_api_url = str(
        os.environ.get("HERMES_API_URL")
        or _get(raw, "hermes", "api_url", default=cfg.hermes_api_url)
    )
    cfg.hermes_api_key = str(
        os.environ.get("HERMES_API_KEY")
        or _get(raw, "hermes", "api_key", default=cfg.hermes_api_key)
    )
    cfg.hermes_timeout_s = float(_get(raw, "hermes", "timeout_s", default=300.0))
    cfg.hermes_allowed_root = Path(
        str(_get(raw, "hermes", "allowed_root", default=str(cfg.hermes_allowed_root)))
    ).expanduser()
    cfg.hermes_office_root = str(
        _get(raw, "hermes", "office_root", default=cfg.hermes_office_root)
    )
    cfg.hermes_audit_path = Path(
        str(_get(raw, "hermes", "audit_path", default=str(cfg.hermes_audit_path)))
    ).expanduser()
    return cfg


def init_config(path: Path | None = None, force: bool = False) -> Path:
    """Write the default config; returns the config path."""
    path = path or CONFIG_FILE
    if path.exists() and not force:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG)
    return path
