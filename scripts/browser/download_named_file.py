# name: download_named_file
# version: 1
# params: {"url": "the file URL to download", "filename": "name to save it as"}
# expect: ["page loaded", "download triggered", "file saved"]
"""Navigate to `url`, let the download complete, save it as `filename` in
the current directory (no machine paths), and verify it is non-empty."""
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
            with page.expect_download() as dl_info:
                page.get_by_text(args["filename"]).click()
            step(2, True, "download triggered")
            dl = dl_info.value
            out = Path(args["filename"])
            dl.save_as(str(out))
            step(3, out.exists() and out.stat().st_size > 0,
                 f"file saved: {out.name} ({out.stat().st_size}B)")
            sys.exit(0)
        finally:
            browser.close()


if __name__ == "__main__":
    main()