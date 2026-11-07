#!/usr/bin/env python3
"""Read a whole section of a website (docs, blog, catalogue) into local files.

Polite by design: obeys robots.txt (including Crawl-delay), waits between
requests, stays inside the start URL's folder unless told otherwise, and stops
at --max-pages. Every page becomes a Markdown file plus an index, so Claude
can grep and read them instead of fetching again.

Examples:
  python3 crawl.py https://docs.example.com/guide/ --max-pages 40
  python3 crawl.py https://example.com --sitemap --include "/blog/" --max-pages 100
  python3 crawl.py https://app.example.com/help/ --method browser --depth 1
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wrp.config import TOOL_USER_AGENT, browser_headers, ensure_venv, reconfigure_stdout  # noqa: E402

ensure_venv()

from wrp import output  # noqa: E402
from wrp.fetcher import FetchOptions, fetch  # noqa: E402
from wrp.net import http_request, normalize_input_url  # noqa: E402

HARD_LIMIT = 500
SKIP_EXT = re.compile(r"\.(png|jpe?g|gif|webp|svg|ico|bmp|tiff?|mp[34]|m4a|wav|ogg|webm|mov|avi|zip|gz|tgz|bz2|"
                      r"xz|7z|rar|exe|dmg|pkg|deb|rpm|msi|apk|iso|woff2?|ttf|otf|eot|css|js|json|xml|rss)$", re.I)
TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|ref_src$|igshid$)")


def canonical(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if not TRACKING.match(k)]
    path = parts.path or "/"
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path,
                                    urllib.parse.urlencode(query), ""))


def registrable_domain(host: str) -> str:
    """docs.example.com -> example.com ; shop.example.co.uk -> example.co.uk (good-enough heuristic)."""
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    second, tld = labels[-2], labels[-1]
    if len(tld) == 2 and (second in ("co", "com", "org", "net", "gov", "ac", "edu", "gob", "nom") or len(second) <= 2):
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def in_scope(url: str, start: urllib.parse.SplitResult, scope: str, prefix: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return False
    if scope == "domain":
        base = registrable_domain(start.hostname or "")
        return bool(parts.hostname) and (parts.hostname == base or parts.hostname.endswith("." + base))
    if parts.hostname != start.hostname:
        return False
    if scope == "host":
        return True
    return (parts.path or "/").startswith(prefix)


class Robots:
    """robots.txt per host, cached. Unreachable robots.txt = allowed (standard behaviour)."""

    def __init__(self, timeout: float):
        self.timeout = timeout
        self.cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def parser(self, url: str):
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.cache:
            rp = urllib.robotparser.RobotFileParser()
            resp = http_request(origin + "/robots.txt", headers={"User-Agent": TOOL_USER_AGENT}, timeout=self.timeout)
            if resp.error or resp.status is None or resp.status >= 500:
                self.cache[origin] = None  # unknown -> allow, but be gentle
            elif resp.status in (401, 403):
                rp.disallow_all = True
                self.cache[origin] = rp
            elif resp.status >= 400:
                rp.allow_all = True
                self.cache[origin] = rp
            else:
                rp.parse(resp.body.decode("utf-8", "replace").splitlines())
                self.cache[origin] = rp
        return self.cache[origin]

    def allowed(self, url: str) -> bool:
        rp = self.parser(url)
        if rp is None:
            return True
        return rp.can_fetch("web-research-pro", url) and rp.can_fetch("*", url)

    def delay(self, url: str) -> float:
        rp = self.parser(url)
        if rp is None:
            return 0.0
        try:
            value = rp.crawl_delay("web-research-pro") or rp.crawl_delay("*")
        except Exception:
            value = None
        return float(value or 0)

    def sitemaps(self, url: str) -> list[str]:
        rp = self.parser(url)
        try:
            return list(rp.site_maps() or []) if rp else []
        except Exception:
            return []


def sitemap_urls(start: str, robots: Robots, limit: int, timeout: float) -> list[str]:
    parts = urllib.parse.urlsplit(start)
    queue = robots.sitemaps(start) or [f"{parts.scheme}://{parts.netloc}/sitemap.xml"]
    seen_maps, found = set(), []
    while queue and len(found) < limit * 5 and len(seen_maps) < 50:
        sm = queue.pop(0)
        if sm in seen_maps:
            continue
        seen_maps.add(sm)
        resp = http_request(sm, headers=browser_headers(), timeout=timeout)
        if resp.error or not resp.body or (resp.status or 500) >= 400:
            continue
        body = resp.body
        if body[:2] == b"\x1f\x8b":
            try:
                body = gzip.decompress(body)
            except OSError:
                continue
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            continue
        for loc in root.iter():
            if loc.tag.rsplit("}", 1)[-1] != "loc" or not loc.text:
                continue
            target = loc.text.strip()
            if root.tag.endswith("sitemapindex"):
                queue.append(target)
            else:
                found.append(target)
    return found


def main(argv: list[str] | None = None) -> int:
    reconfigure_stdout()
    p = argparse.ArgumentParser(description="Polite site crawler that saves pages as Markdown.",
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__.split("Examples:", 1)[1])
    p.add_argument("start", help="first URL (its folder is the default scope)")
    p.add_argument("--max-pages", type=int, default=25, help=f"stop after N pages (default 25, max {HARD_LIMIT})")
    p.add_argument("--depth", type=int, default=2, help="link depth from the start page (default 2)")
    p.add_argument("--scope", choices=["prefix", "host", "domain"], default="prefix",
                   help="prefix = same folder (default), host = whole site, domain = include subdomains")
    p.add_argument("--include", help="only keep URLs matching this regex")
    p.add_argument("--exclude", help="skip URLs matching this regex")
    p.add_argument("--sitemap", action="store_true", help="discover pages from sitemap.xml instead of links")
    p.add_argument("--method", choices=["auto", "http", "browser"], default="http",
                   help="http is fast (default); use auto/browser for JavaScript sites")
    p.add_argument("--session", help="saved login session to use (see login.py)")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1.0)")
    p.add_argument("--timeout", type=float, default=25)
    p.add_argument("--out-dir", help="folder for the Markdown files (default ./crawl-<host>-<time>)")
    args = p.parse_args(argv)

    start_url = normalize_input_url(args.start)
    start = urllib.parse.urlsplit(start_url)
    prefix = start.path if start.path.endswith("/") else (start.path.rsplit("/", 1)[0] + "/")
    max_pages = max(1, min(args.max_pages, HARD_LIMIT))
    include = re.compile(args.include) if args.include else None
    exclude = re.compile(args.exclude) if args.exclude else None
    out_dir = Path(args.out_dir or f"crawl-{start.hostname}-{time.strftime('%Y%m%d-%H%M%S')}")
    out_dir.mkdir(parents=True, exist_ok=True)
    robots = Robots(args.timeout)
    opts = FetchOptions(method=args.method, session=args.session, timeout=args.timeout, third_party=False)

    def wanted(url: str) -> bool:
        if SKIP_EXT.search(urllib.parse.urlsplit(url).path):
            return False
        if not in_scope(url, start, args.scope, prefix):
            return False
        if include and not include.search(url):
            return False
        if exclude and exclude.search(url):
            return False
        return True

    queue: deque[tuple[str, int]] = deque()
    seen: set[str] = set()
    if args.sitemap:
        for url in sitemap_urls(start_url, robots, max_pages, args.timeout):
            c = canonical(url)
            if c not in seen and wanted(c):
                seen.add(c)
                queue.append((c, 0))
        print(f"sitemap: {len(queue)} matching URLs found", flush=True)
    if not queue:
        seen.add(canonical(start_url))
        queue.append((canonical(start_url), 0))

    browser = None
    if args.method in ("auto", "browser"):
        from wrp.browser import Browser, playwright_installed

        if playwright_installed():
            browser = Browser()
    pages, skipped_robots, failures, duplicates = [], [], 0, 0
    content_hashes: set[str] = set()
    fetched_final: set[str] = set()
    last_request = 0.0
    try:
        while queue and len(pages) < max_pages:
            url, depth = queue.popleft()
            if not robots.allowed(url):
                skipped_robots.append(url)
                continue
            wait = max(args.delay, robots.delay(url)) - (time.monotonic() - last_request)
            if wait > 0 and last_request:
                time.sleep(min(wait, 30))
            last_request = time.monotonic()
            result = fetch(url, opts, browser=browser)
            final = canonical(result.final_url or url)
            digest = hashlib.sha1(result.content.encode("utf-8")).hexdigest() if result.ok else ""
            if (final != url and final in fetched_final) or (digest and digest in content_hashes):
                duplicates += 1  # redirect or alias of a page we already saved
                print(f"[dup] {url} (same page as one already saved)", flush=True)
                continue
            fetched_final.add(final)
            if digest:
                content_hashes.add(digest)
            index = len(pages) + 1
            name = f"{index:03d}-{output.slugify_url(result.final_url or url, 70)}.md"
            output.save(result, out_dir / name)
            pages.append({"n": index, "url": result.final_url or url, "title": result.title, "ok": result.ok,
                          "chars": result.chars, "method": result.method, "file": name, "depth": depth,
                          "reason": result.reason})
            if not result.ok:
                failures += 1
            print(f"[{index}/{max_pages}] {'ok ' if result.ok else 'ERR'} {result.chars:>7} chars  {url}", flush=True)
            if depth < args.depth and not args.sitemap:
                for link, _text in result.links:
                    c = canonical(link)
                    if c not in seen and wanted(c):
                        seen.add(c)
                        queue.append((c, depth + 1))
    except KeyboardInterrupt:
        print("interrupted: writing the index for what was saved so far", file=sys.stderr)
    finally:
        if browser is not None:
            browser.close()

    lines = [f"# Crawl of {start_url}", "",
             f"- date: {time.strftime('%Y-%m-%d %H:%M')}", f"- pages saved: {len(pages)} (failed: {failures})",
             f"- scope: {args.scope} {prefix if args.scope == 'prefix' else ''}",
             f"- skipped by robots.txt: {len(skipped_robots)}", f"- duplicates skipped: {duplicates}",
             f"- not visited (limit reached): {len(queue)}", "",
             "| # | title | chars | file |", "|---|---|---|---|"]
    for page in pages:
        title = (page["title"] or page["url"]).replace("|", "/")[:90]
        lines.append(f"| {page['n']} | [{title}]({page['url']}) | {page['chars']} | {page['file']} |")
    if skipped_robots:
        lines += ["", "## Disallowed by robots.txt (not fetched)"] + [f"- {u}" for u in skipped_robots[:50]]
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(out_dir / "pages.jsonl", "w", encoding="utf-8") as handle:
        for page in pages:
            handle.write(json.dumps(page, ensure_ascii=False) + "\n")
    print(f"\n=== crawl finished: {len(pages)} pages in {out_dir}/ (index: {out_dir / 'INDEX.md'}) ===")
    if skipped_robots:
        print(f"{len(skipped_robots)} URLs were not fetched because robots.txt disallows them")
    if queue:
        print(f"{len(queue)} more URLs were found but not visited (raise --max-pages to continue)")
    return 0 if pages and failures < len(pages) else 1


if __name__ == "__main__":
    sys.exit(main())
