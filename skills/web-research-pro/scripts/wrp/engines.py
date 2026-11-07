"""Search engines and specialised sources.

Each engine has a network function and a pure `parse_*` function, so the
parsing can be unit-tested offline with saved responses.

Keyless:   duckduckgo (html + lite), wikipedia, hn, reddit, github, arxiv, stackexchange
With keys: brave (BRAVE_API_KEY), tavily (TAVILY_API_KEY), searxng (SEARXNG_URL)
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser

from .config import api_headers, browser_headers
from .net import http_request


class SearchError(Exception):
    pass


@dataclass
class Result:
    title: str
    url: str
    snippet: str = ""
    source: str = ""
    date: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _check(resp, engine: str):
    if resp.error:
        raise SearchError(f"{engine}: {resp.error}")
    if resp.status == 429:
        raise SearchError(f"{engine}: rate limited (HTTP 429). Wait a minute or use another engine")
    if resp.status in (401, 403):
        raise SearchError(f"{engine}: access refused (HTTP {resp.status}). Check the API key or try another engine")
    if resp.status and resp.status >= 400:
        raise SearchError(f"{engine}: HTTP {resp.status}")
    return resp


def _json(resp, engine: str):
    try:
        return json.loads(resp.body.decode(resp.charset or "utf-8", errors="replace"))
    except ValueError as exc:
        raise SearchError(f"{engine}: unexpected (non-JSON) answer") from exc


# ---------------------------------------------------------------------------
# DuckDuckGo (keyless). html.duckduckgo.com is the official no-JavaScript page.
# ---------------------------------------------------------------------------

DDG_TIME = {"d": "d", "w": "w", "m": "m", "y": "y"}


def _ddg_target(href: str) -> str:
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlsplit(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
        return target
    return href


class _DDGHtmlParser(HTMLParser):
    """Parses html.duckduckgo.com result pages (div.result > .result__body)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: list[dict] = []
        self.current: dict | None = None
        self.capture: str | None = None
        self.capture_tag = ""
        self.capture_depth = 0
        self.buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "") or ""
        if tag == "div" and re.search(r"\bresult\b", cls) and ("results_links" in cls or "web-result" in cls):
            self.current = {"title": "", "url": "", "snippet": "", "ad": "result--ad" in cls}
            self.results.append(self.current)
            return
        if self.current is None:
            return
        if self.capture:
            if tag == self.capture_tag:
                self.capture_depth += 1
            return
        if tag == "a" and "result__a" in cls:
            self.current["url"] = _ddg_target(a.get("href", ""))
            self._start("title", tag)
        elif "result__snippet" in cls:
            if not self.current["url"] and a.get("href"):
                self.current["url"] = _ddg_target(a["href"])
            self._start("snippet", tag)

    def _start(self, what, tag):
        self.capture, self.capture_tag, self.capture_depth, self.buf = what, tag, 1, []

    def handle_endtag(self, tag):
        if self.capture and tag == self.capture_tag:
            self.capture_depth -= 1
            if self.capture_depth == 0:
                self.current[self.capture] = _clean("".join(self.buf))
                self.capture = None

    def handle_data(self, data):
        if self.capture:
            self.buf.append(data)


def parse_ddg_html(html: str) -> list[Result]:
    parser = _DDGHtmlParser()
    parser.feed(html)
    out = []
    for r in parser.results:
        url = r["url"]
        if r["ad"] or not url or "duckduckgo.com/y.js" in url or not r["title"]:
            continue
        out.append(Result(r["title"], url, r["snippet"], "duckduckgo"))
    return out


class _DDGLiteParser(HTMLParser):
    """lite.duckduckgo.com: a plain table, rows of link / snippet / url."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: list[dict] = []
        self.capture: str | None = None
        self.buf: list[str] = []
        self.sponsored = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "") or ""
        if tag == "tr":
            self.sponsored = "result-sponsored" in cls
        if tag == "a" and "result-link" in cls:
            self.results.append({"title": "", "url": _ddg_target(a.get("href", "")), "snippet": "",
                                 "ad": self.sponsored})
            self.capture, self.buf = "title", []
        elif tag == "td" and "result-snippet" in cls and self.results:
            self.capture, self.buf = "snippet", []

    def handle_endtag(self, tag):
        if self.capture == "title" and tag == "a" or self.capture == "snippet" and tag == "td":
            self.results[-1][self.capture] = _clean("".join(self.buf))
            self.capture = None

    def handle_data(self, data):
        if self.capture:
            self.buf.append(data)


def parse_ddg_lite(html: str) -> list[Result]:
    parser = _DDGLiteParser()
    parser.feed(html)
    return [Result(r["title"], r["url"], r["snippet"], "duckduckgo-lite") for r in parser.results
            if r["url"] and r["title"] and not r["ad"] and "duckduckgo.com/y.js" not in r["url"]]


def _ddg_blocked(body: str) -> bool:
    low = body.lower()
    return "anomaly-modal" in low or "bots use duckduckgo too" in low or "challenge-form" in low


def search_ddg(query: str, n: int = 10, region: str = "", time_range: str = "", timeout: float = 20) -> list[Result]:
    form = {"q": query, "b": ""}
    if region:
        form["kl"] = region
    if time_range in DDG_TIME:
        form["df"] = DDG_TIME[time_range]
    data = urllib.parse.urlencode(form).encode()
    errors = []
    for endpoint, parser in (("https://html.duckduckgo.com/html/", parse_ddg_html),
                             ("https://lite.duckduckgo.com/lite/", parse_ddg_lite)):
        headers = browser_headers({"Content-Type": "application/x-www-form-urlencoded",
                                   "Referer": endpoint, "Origin": endpoint.rstrip("/").rsplit("/", 1)[0]})
        resp = http_request(endpoint, method="POST", data=data, headers=headers, timeout=timeout)
        if resp.error or not resp.status or resp.status >= 400:
            errors.append(f"{endpoint}: {resp.error or 'HTTP ' + str(resp.status)}")
            continue
        body = resp.body.decode(resp.charset or "utf-8", errors="replace")
        if resp.status == 202 or _ddg_blocked(body):
            errors.append(f"{endpoint}: DuckDuckGo asked for a human check (too many automated searches)")
            continue
        results = parser(body)
        if results:
            return results[:n]
        if "no results" in body.lower() or "no se han encontrado" in body.lower():
            return []
        errors.append(f"{endpoint}: page had no parsable results (layout may have changed)")
    raise SearchError("duckduckgo: " + " | ".join(errors) +
                      ". Tip: wait a minute, or set BRAVE_API_KEY / TAVILY_API_KEY for a stable search API")


# ---------------------------------------------------------------------------
# Search APIs that need the user's own key (all have free tiers)
# ---------------------------------------------------------------------------

BRAVE_FRESHNESS = {"d": "pd", "w": "pw", "m": "pm", "y": "py"}


def parse_brave(data: dict) -> list[Result]:
    out = []
    for item in (data.get("web") or {}).get("results", []):
        out.append(Result(_clean(item.get("title", "")), item.get("url", ""), _clean(item.get("description", "")),
                          "brave", item.get("page_age") or item.get("age") or ""))
    return out


def search_brave(query: str, n: int = 10, region: str = "", time_range: str = "", timeout: float = 20) -> list[Result]:
    key = os.environ.get("BRAVE_API_KEY")
    if not key:
        raise SearchError("brave: set BRAVE_API_KEY (free tier at https://brave.com/search/api/)")
    params = {"q": query, "count": min(max(n, 1), 20)}
    if region and "-" in region:
        country, lang = region.split("-", 1)
        params["country"] = country.upper()
        params["search_lang"] = lang.lower()
    if time_range in BRAVE_FRESHNESS:
        params["freshness"] = BRAVE_FRESHNESS[time_range]
    url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode(params)
    resp = _check(http_request(url, headers=api_headers({"X-Subscription-Token": key}), timeout=timeout), "brave")
    return parse_brave(_json(resp, "brave"))[:n]


TAVILY_TIME = {"d": "day", "w": "week", "m": "month", "y": "year"}


def parse_tavily(data: dict) -> list[Result]:
    return [Result(_clean(i.get("title", "")), i.get("url", ""), _clean(i.get("content", "")), "tavily",
                   i.get("published_date", "") or "", {"score": i.get("score")}) for i in data.get("results", [])]


def search_tavily(query: str, n: int = 10, region: str = "", time_range: str = "", timeout: float = 30) -> list[Result]:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise SearchError("tavily: set TAVILY_API_KEY (free tier at https://tavily.com)")
    payload = {"query": query, "max_results": min(max(n, 1), 20), "search_depth": "basic"}
    if time_range in TAVILY_TIME:
        payload["time_range"] = TAVILY_TIME[time_range]
    headers = api_headers({"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    resp = _check(http_request("https://api.tavily.com/search", method="POST", headers=headers,
                               data=json.dumps(payload).encode(), timeout=timeout), "tavily")
    return parse_tavily(_json(resp, "tavily"))[:n]


SEARX_TIME = {"d": "day", "w": "week", "m": "month", "y": "year"}


def parse_searxng(data: dict) -> list[Result]:
    return [Result(_clean(i.get("title", "")), i.get("url", ""), _clean(i.get("content", "")),
                   "searxng:" + str(i.get("engine", "")), i.get("publishedDate") or "")
            for i in data.get("results", [])]


def search_searxng(query: str, n: int = 10, region: str = "", time_range: str = "", timeout: float = 20) -> list[Result]:
    base = os.environ.get("SEARXNG_URL")
    if not base:
        raise SearchError("searxng: set SEARXNG_URL to your instance, e.g. http://localhost:8080")
    params = {"q": query, "format": "json"}
    if region and "-" in region:
        params["language"] = region.split("-", 1)[1]
    if time_range in SEARX_TIME:
        params["time_range"] = SEARX_TIME[time_range]
    resp = _check(http_request(base.rstrip("/") + "/search?" + urllib.parse.urlencode(params),
                               headers=api_headers(), timeout=timeout), "searxng")
    return parse_searxng(_json(resp, "searxng"))[:n]


# ---------------------------------------------------------------------------
# Specialised public sources (official, keyless APIs)
# ---------------------------------------------------------------------------

def parse_wikipedia(data: dict, lang: str) -> list[Result]:
    out = []
    for item in (data.get("query") or {}).get("search", []):
        title = item.get("title", "")
        url = f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        out.append(Result(title, url, _clean(item.get("snippet", "")), f"wikipedia-{lang}",
                          (item.get("timestamp") or "")[:10], {"words": item.get("wordcount")}))
    return out


def search_wikipedia(query: str, n: int = 10, lang: str = "en", timeout: float = 20, **_) -> list[Result]:
    params = {"action": "query", "list": "search", "srsearch": query, "format": "json",
              "srlimit": min(max(n, 1), 50), "utf8": 1}
    url = f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    resp = _check(http_request(url, headers=api_headers(), timeout=timeout), "wikipedia")
    return parse_wikipedia(_json(resp, "wikipedia"), lang)[:n]


def parse_hn(data: dict) -> list[Result]:
    out = []
    for hit in data.get("hits", []):
        item = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        url = hit.get("url") or item
        snippet = f"{hit.get('points', 0)} points, {hit.get('num_comments', 0)} comments — discussion: {item}"
        out.append(Result(_clean(hit.get("title") or hit.get("story_title") or ""), url, snippet, "hackernews",
                          (hit.get("created_at") or "")[:10]))
    return out


def search_hn(query: str, n: int = 10, time_range: str = "", timeout: float = 20, **_) -> list[Result]:
    params = {"query": query, "tags": "story", "hitsPerPage": min(max(n, 1), 50)}
    if time_range in ("d", "w", "m", "y"):
        seconds = {"d": 86400, "w": 7 * 86400, "m": 31 * 86400, "y": 366 * 86400}[time_range]
        params["numericFilters"] = f"created_at_i>{int(time.time()) - seconds}"
    url = "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(params)
    resp = _check(http_request(url, headers=api_headers(), timeout=timeout), "hackernews")
    return parse_hn(_json(resp, "hackernews"))[:n]


def parse_reddit(data: dict) -> list[Result]:
    out = []
    for child in (data.get("data") or {}).get("children", []):
        d = child.get("data", {})
        link = "https://www.reddit.com" + d.get("permalink", "")
        body = _clean(d.get("selftext", ""))[:300]
        snippet = f"r/{d.get('subreddit', '?')} · {d.get('score', 0)} points · {d.get('num_comments', 0)} comments"
        if body:
            snippet += f" — {body}"
        date = time.strftime("%Y-%m-%d", time.gmtime(d["created_utc"])) if d.get("created_utc") else ""
        out.append(Result(_clean(d.get("title", "")), link, snippet, "reddit", date))
    return out


def search_reddit(query: str, n: int = 10, time_range: str = "", timeout: float = 20, **_) -> list[Result]:
    params = {"q": query, "limit": min(max(n, 1), 50), "sort": "relevance", "raw_json": 1}
    if time_range in ("d", "w", "m", "y"):
        params["t"] = {"d": "day", "w": "week", "m": "month", "y": "year"}[time_range]
    url = "https://www.reddit.com/search.json?" + urllib.parse.urlencode(params)
    resp = http_request(url, headers=api_headers(), timeout=timeout)
    if resp.status in (403, 429):
        raise SearchError("reddit: Reddit refused anonymous API access from this network. "
                          "Try: search.py 'QUERY site:reddit.com' (web engine)")
    return parse_reddit(_json(_check(resp, "reddit"), "reddit"))[:n]


def parse_github(data: dict) -> list[Result]:
    out = []
    for item in data.get("items", []):
        snippet = f"★ {item.get('stargazers_count', 0)} · {item.get('language') or '-'} — {item.get('description') or ''}"
        out.append(Result(item.get("full_name", ""), item.get("html_url", ""), snippet.strip(), "github",
                          (item.get("pushed_at") or "")[:10]))
    return out


def search_github(query: str, n: int = 10, timeout: float = 20, **_) -> list[Result]:
    params = {"q": query, "per_page": min(max(n, 1), 50)}
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(params)
    headers = api_headers({"Accept": "application/vnd.github+json"})
    token = os.environ.get("WRP_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    resp = http_request(url, headers=dict(headers, Authorization=f"Bearer {token}") if token else headers,
                        timeout=timeout)
    if token and resp.status == 401:  # bad token: retry anonymously
        resp = http_request(url, headers=headers, timeout=timeout)
    if resp.status == 403:
        raise SearchError("github: rate limit reached (10 searches/minute without a token). Set GITHUB_TOKEN")
    return parse_github(_json(_check(resp, "github"), "github"))[:n]


ATOM = "{http://www.w3.org/2005/Atom}"


def parse_arxiv(body: bytes) -> list[Result]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise SearchError("arxiv: invalid response") from exc
    out = []
    for entry in root.findall(f"{ATOM}entry"):
        title = _clean(entry.findtext(f"{ATOM}title") or "")
        link = entry.findtext(f"{ATOM}id") or ""
        pdf = ""
        for l in entry.findall(f"{ATOM}link"):
            if l.get("title") == "pdf":
                pdf = l.get("href", "")
        authors = [a.findtext(f"{ATOM}name") or "" for a in entry.findall(f"{ATOM}author")]
        summary = _clean(entry.findtext(f"{ATOM}summary") or "")
        snippet = f"{', '.join(authors[:4])}{' et al.' if len(authors) > 4 else ''} — {summary[:300]}"
        out.append(Result(title, link, snippet, "arxiv", (entry.findtext(f"{ATOM}published") or "")[:10],
                          {"pdf": pdf}))
    return out


def search_arxiv(query: str, n: int = 10, timeout: float = 30, **_) -> list[Result]:
    params = {"search_query": f"all:{query}", "start": 0, "max_results": min(max(n, 1), 50),
              "sortBy": "relevance"}
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
    resp = _check(http_request(url, headers=api_headers({"Accept": "application/atom+xml"}), timeout=timeout), "arxiv")
    return parse_arxiv(resp.body)[:n]


def parse_stackexchange(data: dict, site: str) -> list[Result]:
    out = []
    for item in data.get("items", []):
        answered = "✔ answered" if item.get("is_answered") else "unanswered"
        snippet = (f"{item.get('score', 0)} votes · {item.get('answer_count', 0)} answers · {answered} · "
                   f"tags: {', '.join(item.get('tags', [])[:5])}")
        date = time.strftime("%Y-%m-%d", time.gmtime(item["creation_date"])) if item.get("creation_date") else ""
        out.append(Result(_clean(item.get("title", "")), item.get("link", ""), snippet, f"stackexchange-{site}", date))
    return out


def search_stackexchange(query: str, n: int = 10, site: str = "stackoverflow", timeout: float = 20, **_) -> list[Result]:
    params = {"order": "desc", "sort": "relevance", "q": query, "site": site, "pagesize": min(max(n, 1), 50)}
    key = os.environ.get("STACKEXCHANGE_KEY")
    if key:
        params["key"] = key
    url = "https://api.stackexchange.com/2.3/search/advanced?" + urllib.parse.urlencode(params)
    resp = _check(http_request(url, headers=api_headers(), timeout=timeout), "stackexchange")
    return parse_stackexchange(_json(resp, "stackexchange"), site)[:n]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

WEB_ENGINES = {"duckduckgo": search_ddg, "ddg": search_ddg, "brave": search_brave,
               "tavily": search_tavily, "searxng": search_searxng}
SOURCE_ENGINES = {"wikipedia": search_wikipedia, "hn": search_hn, "hackernews": search_hn,
                  "reddit": search_reddit, "github": search_github, "arxiv": search_arxiv,
                  "stackoverflow": search_stackexchange, "stackexchange": search_stackexchange}
ALL_ENGINES = ["web", *WEB_ENGINES, *SOURCE_ENGINES]


def default_web_order() -> list[str]:
    order = []
    if os.environ.get("BRAVE_API_KEY"):
        order.append("brave")
    if os.environ.get("TAVILY_API_KEY"):
        order.append("tavily")
    if os.environ.get("SEARXNG_URL"):
        order.append("searxng")
    order.append("duckduckgo")
    return order


def run_engine(name: str, query: str, n: int, region: str, lang: str, time_range: str,
               se_site: str = "stackoverflow") -> tuple[list[Result], list[str], str]:
    """Returns (results, errors, engine_used). 'web' tries each web engine in turn."""
    errors: list[str] = []
    if name == "web":
        for engine in default_web_order():
            try:
                return WEB_ENGINES[engine](query, n, region, time_range), errors, engine
            except SearchError as exc:
                errors.append(str(exc))
        return [], errors, "web"
    if name in WEB_ENGINES:
        try:
            return WEB_ENGINES[name](query, n, region, time_range), errors, name
        except SearchError as exc:
            return [], [str(exc)], name
    if name in SOURCE_ENGINES:
        fn = SOURCE_ENGINES[name]
        kwargs = {"time_range": time_range}
        if name == "wikipedia":
            kwargs["lang"] = lang
        if name in ("stackoverflow", "stackexchange"):
            kwargs["site"] = se_site
        try:
            return fn(query, n, **kwargs), errors, name
        except SearchError as exc:
            return [], [str(exc)], name
    raise SearchError(f"unknown engine '{name}'. Choose from: {', '.join(ALL_ENGINES)}")
