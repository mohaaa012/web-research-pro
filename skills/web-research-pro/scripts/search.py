#!/usr/bin/env python3
"""Search the web and specialised sources, optionally reading the top results.

Engines (comma-separated, default "web"):
  web            best available: Brave/Tavily/SearXNG if you set a key, else DuckDuckGo
  duckduckgo     keyless, supports regions such as es-es, us-en, mx-es
  brave, tavily, searxng   need BRAVE_API_KEY / TAVILY_API_KEY / SEARXNG_URL
  wikipedia, hn, reddit, github, arxiv, stackoverflow   official public APIs

Examples:
  python3 search.py "mejores juegos roblox 2026" --region es-es
  python3 search.py "rust async runtime" --engine web,hn,reddit -n 5
  python3 search.py "transformer architecture" --engine arxiv,wikipedia
  python3 search.py "python packaging" --time m --fetch 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wrp.config import accept_language, ensure_venv, reconfigure_stdout  # noqa: E402

ensure_venv()

from wrp.engines import ALL_ENGINES, SearchError, run_engine  # noqa: E402


def default_region() -> str:
    """'es-ES,es;q=0.9' -> 'es-es' (DuckDuckGo style: country-language)."""
    first = accept_language().split(",")[0]
    if "-" in first:
        lang, country = first.split("-", 1)
        return f"{country.lower()}-{lang.lower()}"
    return "wt-wt"  # DuckDuckGo "no region"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Multi-engine search with optional full-text reading of results.",
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__.split("Engines", 1)[1] if __doc__ else "")
    p.add_argument("query", help="what to search for (quotes, site:, -word work with web engines)")
    p.add_argument("--engine", "-e", default="web", help="engine list, e.g. web,wikipedia,hn")
    p.add_argument("-n", "--num", type=int, default=8, help="results per engine (default 8)")
    p.add_argument("--region", help="country-language, e.g. es-es, us-en, mx-es (default from your locale)")
    p.add_argument("--lang", help="language for Wikipedia (default from region)")
    p.add_argument("--time", choices=["d", "w", "m", "y"], help="only results from the last day/week/month/year")
    p.add_argument("--site", help="restrict web results to a domain (adds site:DOMAIN)")
    p.add_argument("--se-site", default="stackoverflow", help="Stack Exchange site for stackoverflow engine")
    p.add_argument("--fetch", type=int, default=0, metavar="K", help="also read the top K web results in full")
    p.add_argument("--fetch-chars", type=int, default=4000, help="characters to show per fetched result")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    return p


def main(argv: list[str] | None = None) -> int:
    reconfigure_stdout()
    args = build_parser().parse_args(argv)
    region = (args.region or default_region()).lower()
    lang = (args.lang or (region.split("-")[1] if "-" in region and region != "wt-wt" else "en"))[:3]
    query = args.query + (f" site:{args.site}" if args.site else "")
    engines = [e.strip().lower() for e in args.engine.split(",") if e.strip()]
    unknown = [e for e in engines if e not in ALL_ENGINES]
    if unknown:
        print(f"error: unknown engine(s): {', '.join(unknown)}. Choose from: {', '.join(ALL_ENGINES)}", file=sys.stderr)
        return 2
    groups = []
    all_errors = []
    for engine in engines:
        try:
            results, errors, used = run_engine(engine, query if engine in ("web", "duckduckgo", "ddg", "brave",
                                                                          "tavily", "searxng") else args.query,
                                               args.num, region, lang, args.time or "", args.se_site)
        except SearchError as exc:
            results, errors, used = [], [str(exc)], engine
        groups.append({"engine": engine, "used": used, "results": results, "errors": errors})
        all_errors.extend(errors)

    fetched = []
    if args.fetch:
        from wrp.fetcher import FetchOptions, fetch

        seen = set()
        urls = []
        for group in groups:
            for result in group["results"]:
                if result.url not in seen and len(urls) < args.fetch:
                    seen.add(result.url)
                    urls.append(result.url)
        browser = None
        try:
            from wrp.browser import Browser, playwright_installed

            browser = Browser() if playwright_installed() else None
            for url in urls:
                fetched.append(fetch(url, FetchOptions(timeout=25), browser=browser))
        finally:
            if browser is not None:
                browser.close()

    if args.json:
        print(json.dumps({
            "query": query, "region": region,
            "groups": [{"engine": g["engine"], "used": g["used"], "errors": g["errors"],
                        "results": [r.to_dict() for r in g["results"]]} for g in groups],
            "fetched": [f.to_dict() for f in fetched],
        }, ensure_ascii=False, indent=2))
    else:
        print(f"=== web-research-pro search ===\nquery: {query}\nregion: {region}")
        for group in groups:
            used = group["used"] if group["used"] == group["engine"] else f"{group['engine']} -> {group['used']}"
            print(f"\n## {used} ({len(group['results'])} results)")
            for err in group["errors"]:
                print(f"   ! {err}")
            for i, r in enumerate(group["results"], 1):
                date = f" [{r.date}]" if r.date else ""
                print(f"{i}. {r.title}{date}\n   {r.url}")
                if r.snippet:
                    print(f"   {r.snippet[:400]}")
        for f in fetched:
            print("\n" + "=" * 70)
            from wrp import output

            print(output.render(f, "markdown", max_chars=args.fetch_chars))
    total = sum(len(g["results"]) for g in groups)
    if total == 0:
        if not args.json:
            print("\nNo results. " + ("Errors above." if all_errors else "Try other words or another engine."))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
