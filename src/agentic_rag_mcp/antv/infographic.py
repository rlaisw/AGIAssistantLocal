"""antv_infographic tool body: browser-rendered infographics (spec 012, R3).

Stores the declarative syntax on the sidecar; serves an HTML page that loads
the @antv/infographic engine from CDN and renders client-side — no
server-side DOM, no puppeteer (Constitution III).
"""

from __future__ import annotations

import re
import uuid

from ..config import Config
from .errors import AntvInvalidInput

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

# spec 044: the chatflow's stepwise-default templates below are pinned to this
# @antv/infographic version — if the CDN version in _PAGE_TEMPLATE ever changes,
# re-verify that sequence-roadmap-vertical-pill-badge, sequence-timeline-done-list,
# and list-row-horizontal-icon-arrow still exist in the new bundle before the
# chatflow's stepwise default keeps applying them (FR-006).
_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Infographic</title>
<style>
html,body{margin:0;padding:0;height:100%}
body{background:#fafafa;font-family:system-ui,sans-serif}
#container{width:100%;min-height:100vh;box-sizing:border-box;padding:24px 16px}
#fallback{display:none;padding:48px 16px;text-align:center;color:#b3261e;white-space:pre-wrap}
</style>
</head>
<body>
<div id="container"><div id="fallback">loading…</div></div>
<script src="https://cdn.jsdelivr.net/npm/@antv/infographic@0.2.20/dist/infographic.min.js"></script>
<script>
const syntax = {syntax_json};
const container = document.getElementById('container');
const fallback = document.getElementById('fallback');
try {
  const Engine = window.AntVInfographic && window.AntVInfographic.Infographic
    ? window.AntVInfographic.Infographic
    : window.Infographic;
  if (!Engine) throw new Error('engine failed to load (CDN unreachable?)');
  fallback.remove();
  const width = Math.min(Math.max(container.clientWidth || 960, 480), 1200);
  const height = Math.max(window.innerHeight - 48, 600);
  const ig = new Engine({ container: container, width: width, height: height });
  ig.render(syntax);
  setTimeout(() => {
    const svg = container.querySelector('svg');
    if (!svg) {
      container.innerHTML = '<div style="padding:48px 16px;text-align:center;color:#b3261e">'
        + 'The engine produced no content for this syntax. '
        + 'Ask the agent to regenerate with a standard template.</div>';
    }
  }, 2000);
} catch (e) {
  container.innerHTML = '<div style="padding:48px 16px;text-align:center;color:#b3261e">'
    + 'Infographic error: ' + (e && e.message ? e.message : 'unknown') + '</div>';
}
</script>
</body>
</html>
<!-- page-version: 6 -->
"""


def served_dir(cfg: Config):
    path = cfg.antv_infographic_served_root
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_id(infographic_id: str) -> None:
    if not infographic_id or not _ID_RE.match(infographic_id):
        raise AntvInvalidInput(f"invalid infographic id: {infographic_id!r}")


def create_infographic(cfg: Config, description: str) -> dict:
    if not description or not description.strip():
        raise AntvInvalidInput("description (the infographic syntax) must be non-empty")
    if len(description.encode("utf-8")) > cfg.antv_infographic_max_syntax_bytes:
        raise AntvInvalidInput(
            f"description too large (cap {cfg.antv_infographic_max_syntax_bytes} bytes)"
        )
    infographic_id = uuid.uuid4().hex[:12]
    (served_dir(cfg) / f"{infographic_id}.txt").write_text(description, encoding="utf-8")
    base = cfg.ppt_exports_url_base.rsplit("/exports", 1)[0].rstrip("/")
    return {
        "id": infographic_id,
        "url": f"{base}/infographics/{infographic_id}/",
        "usage": (
            "Give the user the url as a markdown link — it opens the rendered "
            "infographic in a browser."
        ),
    }


def render_infographic_page(cfg: Config, infographic_id: str) -> str:
    validate_id(infographic_id)
    path = cfg.antv_infographic_served_root / f"{infographic_id}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"no infographic {infographic_id}")
    syntax = path.read_text(encoding="utf-8")
    return _PAGE_TEMPLATE.replace("{syntax_json}", json_dump(syntax))


def json_dump(text: str) -> str:
    import json

    return json.dumps(text)
