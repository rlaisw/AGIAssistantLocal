# name: open_and_screenshot
# version: 1
# params: {"url": "the page to open"}
# expect: ["page loaded", "screenshot saved"]
"""Open `url` headless and save a full-page screenshot to the current
directory (no machine paths — the caller's cwd decides where files land)."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def step(n, ok, summary):
    print(json.dumps({"step": n, "ok": ok, "summary": summary}))


def main():
    args = json.loads(sys.argv[1])
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(args["url"], timeout=20000)
            step(1, True, f"page loaded: {args['url']}")
            out = Path("screenshot.png").resolve()
            page.screenshot(path=str(out), full_page=True)
            step(2, out.exists() and out.stat().st_size > 0,
                 f"screenshot saved: {out.name} ({out.stat().st_size}B)")
            sys.exit(0)
        finally:
            browser.close()


if __name__ == "__main__":
    main()