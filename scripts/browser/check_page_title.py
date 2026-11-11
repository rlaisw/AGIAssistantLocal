# name: check_page_title
# version: 1
# params: {"url": "the page to open", "title_hint": "text the title should contain"}
# expect: ["page loaded", "title read"]
"""Open `url` in Chromium, verify the title contains `title_hint`.

Emits one JSON step line per checkpoint (research R2 stdout discipline)."""
import json
import sys

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
            title = page.title()
            ok = args["title_hint"].lower() in title.lower()
            step(2, ok, f"title read: {title!r}"
                 + ("" if ok else f" (missing {args['title_hint']!r})"))
            sys.exit(0 if ok else 1)
        finally:
            browser.close()


if __name__ == "__main__":
    main()