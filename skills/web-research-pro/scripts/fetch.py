#!/usr/bin/env python3
"""Read any web page, PDF or feed and print clean text, escalating methods as needed.

  http -> real browser (JavaScript) -> reader service -> Wayback Machine archive

Examples:
  python3 fetch.py https://example.com/article
  python3 fetch.py https://app.example.com/dashboard --method browser --scroll 3
  python3 fetch.py https://site.com/private --session mysite
  python3 fetch.py URL1 URL2 URL3 --out-dir research/
  python3 fetch.py https://site.com --screenshot shot.png
  python3 fetch.py https://site.com/report.pdf --out report.md
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wrp.config import ensure_venv, reconfigure_stdout  # noqa: E402

ensure_venv()

from wrp import output  # noqa: E402
from wrp.fetcher import FetchOptions, fetch  # noqa: E402
from wrp.sessions import SessionError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fetch web pages with automatic fallbacks (http, browser, reader, archive).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Examples:", 1)[1] if __doc__ else "",
    )
    p.add_argument("urls", nargs="+", help="one or more URLs (https:// is added if missing)")
    p.add_argument("--method", choices=["auto", "http", "browser", "reader", "archive"], default="auto",
                   help="force one method (default: auto, escalating only when needed)")
    p.add_argument("--session", help="use a saved login session (see login.py); keeps everything local")
    p.add_argument("--format", choices=["markdown", "json", "html"], default="markdown")
    p.add_argument("--json", action="store_true", help="shortcut for --format json")
    p.add_argument("--extract", choices=["auto", "main", "full"], default="auto",
                   help="main = article only, full = whole page text (listings, tables)")
    p.add_argument("--max-chars", type=int, default=25000, help="characters to print (0 = all)")
    p.add_argument("--offset", type=int, default=0, help="start printing at this character (pagination)")
    p.add_argument("--out", help="save the full result to this file (single URL)")
    p.add_argument("--out-dir", help="save every result as a file in this folder and print a summary")
    p.add_argument("--links", action="store_true", help="also list the links found on the page")
    p.add_argument("--screenshot", help="save a full-page PNG (uses the browser)")
    p.add_argument("--scroll", type=int, default=0, help="scroll N times to load lazy/infinite content")
    p.add_argument("--wait-for", help="CSS selector to wait for before reading (uses the browser)")
    p.add_argument("--click", action="append", default=[],
                   help="CSS selector to click first, e.g. a cookie banner or 'load more' (repeatable)")
    p.add_argument("--wait", type=int, default=0, help="extra milliseconds to wait after loading")
    p.add_argument("--timeout", type=float, default=30, help="seconds per attempt (default 30)")
    p.add_argument("--headed", action="store_true", help="show the browser window (needs a display)")
    p.add_argument("--no-third-party", action="store_true",
                   help="never use r.jina.ai or the Wayback Machine as fallbacks")
    p.add_argument("--archive-date", help="with --method archive: snapshot closest to YYYYMMDD")
    p.add_argument("--max-pdf-pages", type=int, help="only extract the first N pages of a PDF")
    return p


def main(argv: list[str] | None = None) -> int:
    reconfigure_stdout()
    args = build_parser().parse_args(argv)
    fmt = "json" if args.json else args.format
    if args.out and len(args.urls) > 1:
        print("error: --out works with a single URL; use --out-dir for several", file=sys.stderr)
        return 2
    opts = FetchOptions(
        method=args.method,
        session=args.session,
        extract_mode=args.extract,
        timeout=args.timeout,
        wait_for=args.wait_for,
        clicks=tuple(args.click),
        scroll=args.scroll,
        wait_ms=args.wait,
        screenshot=args.screenshot,
        headed=args.headed,
        third_party=not args.no_third_party,
        keep_html=fmt == "html",
        archive_date=args.archive_date,
        max_pdf_pages=args.max_pdf_pages,
    )
    browser = None
    failures = 0
    summary = []
    try:
        for index, url in enumerate(args.urls):
            if args.screenshot and len(args.urls) > 1:
                stem, ext = os.path.splitext(args.screenshot)
                opts.screenshot = f"{stem}-{index + 1}{ext or '.png'}"
            try:
                if browser is None and opts.method in ("auto", "browser"):
                    from wrp.browser import Browser, playwright_installed

                    if playwright_installed():
                        browser = Browser(headed=args.headed)
                result = fetch(url, opts, browser=browser)
            except SessionError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            if not result.ok:
                failures += 1
            if args.out_dir:
                ext = {"json": ".json", "html": ".html"}.get(fmt, ".md")
                path = Path(args.out_dir) / f"{index + 1:02d}-{output.slugify_url(result.final_url or url)}{ext}"
                output.save(result, path, fmt)
                summary.append((result, path))
                continue
            if args.out:
                path = output.save(result, Path(args.out), fmt)
                print(output.render(result, "markdown", max_chars=1500))
                print(f"\n[saved full result ({result.chars} chars) to {path}]")
                continue
            if index:
                print("\n" + "=" * 70 + "\n")
            print(output.render(result, fmt, max_chars=args.max_chars, offset=args.offset,
                                show_links=args.links))
    finally:
        if browser is not None:
            browser.close()
    if summary:
        print(f"=== web-research-pro fetch: {len(summary)} pages saved to {args.out_dir} ===")
        for result, path in summary:
            state = "ok " if result.ok else "FAIL"
            note = result.archived_at and f" archived {result.archived_at}" or ""
            print(f"[{state}] {result.method or '-':8} {result.chars:>7} chars  {path}  <- {result.final_url}{note}"
                  + ("" if result.ok else f"  ({result.reason})"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
