# name: search_and_report
# version: 1
# params: {"query": "the search text to look up"}
# expect: ["search page loaded", "results read"]
"""Search a search engine for `query` and extract the results-page text.

The fast path for 'search X and report' flows (browsing-is-working-but-
very-slow, 2026-11-11): deterministic, ~10-25s, no LLM steering — direct
URL navigation, one read, structured JSON step lines."""
import json
import sys
import urllib.parse

from playwright.sync_api import sync_playwright


def step(n, ok, summary):
    print(json.dumps({"step": n, "ok": ok, "summary": summary}))


def main():
    # plain positional arg (PowerShell mangles JSON-on-the-command-line;
    # the query is one quoted string — the common case for every lane)
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        step(0, False, "no query given — nothing to search")
        sys.exit(2)
    url = "https://www.bing.com/search?q=" + urllib.parse.quote_plus(query)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            step(1, True, f"search page loaded: {query!r}")
            # give JS-rendered results a moment, then read the main text
            page.wait_for_timeout(1500)
            body = page.inner_text("body")[:3000]
            ok = len(body.strip()) > 100
            summary = (f"results read ({len(body)} chars); asked for {hint}: "
                       + " ".join(body.split())[:400])
            step(2, ok, summary if ok else "results read: page appeared empty")
            sys.exit(0 if ok else 1)
        finally:
            browser.close()


if __name__ == "__main__":
    main()