"""Search parsers, tested offline against saved response samples."""

from pathlib import Path

import pytest

from wrp import engines

FIX = Path(__file__).parent / "fixtures"


def test_duckduckgo_html_parser_skips_ads_and_decodes_redirects():
    results = engines.parse_ddg_html((FIX / "ddg_html.html").read_text(encoding="utf-8"))
    assert [r.url for r in results] == ["https://www.roblox.com/charts", "https://en.wikipedia.org/wiki/Roblox"]
    assert results[0].title == "Roblox Charts - Top experiences"
    assert results[0].snippet.startswith("Discover the top experiences")
    assert results[1].snippet == "Roblox is an online game platform and game creation system."


def test_duckduckgo_lite_parser():
    results = engines.parse_ddg_lite((FIX / "ddg_lite.html").read_text(encoding="utf-8"))
    assert [(r.title, r.url) for r in results] == [("Roblox Charts", "https://www.roblox.com/charts"),
                                                    ("Roblox - Wikipedia", "https://en.wikipedia.org/wiki/Roblox")]
    assert results[0].snippet == "Discover the top experiences on Roblox."


def test_ddg_redirect_decoding():
    assert engines._ddg_target("//duckduckgo.com/l/?uddg=https%3A%2F%2Fa.com%2Fx%3Fy%3D1&rut=z") == "https://a.com/x?y=1"
    assert engines._ddg_target("https://b.com/") == "https://b.com/"


def test_api_parsers():
    brave = engines.parse_brave({"web": {"results": [{"title": "<strong>A</strong>", "url": "https://a.com",
                                                       "description": "desc &amp; more", "page_age": "2026-01-01"}]}})
    assert (brave[0].title, brave[0].snippet, brave[0].date) == ("A", "desc & more", "2026-01-01")
    tavily = engines.parse_tavily({"results": [{"title": "T", "url": "https://t.com", "content": "c", "score": 0.9}]})
    assert tavily[0].extra["score"] == 0.9
    searx = engines.parse_searxng({"results": [{"title": "S", "url": "https://s.com", "content": "x", "engine": "bing"}]})
    assert searx[0].source == "searxng:bing"


def test_source_parsers():
    wiki = engines.parse_wikipedia({"query": {"search": [{"title": "Pet Simulator X", "snippet":
                                    '<span class="searchmatch">Pet</span> game', "timestamp": "2026-05-01T10:00:00Z",
                                    "wordcount": 900}]}}, "es")
    assert wiki[0].url == "https://es.wikipedia.org/wiki/Pet_Simulator_X" and wiki[0].snippet == "Pet game"
    hn = engines.parse_hn({"hits": [{"title": "Show HN: X", "url": None, "objectID": "42", "points": 10,
                                     "num_comments": 3, "created_at": "2026-02-02T00:00:00Z"}]})
    assert hn[0].url == "https://news.ycombinator.com/item?id=42" and hn[0].date == "2026-02-02"
    reddit = engines.parse_reddit({"data": {"children": [{"data": {"title": "Best pets?", "permalink": "/r/x/c/1/",
                                   "subreddit": "x", "score": 5, "num_comments": 2, "selftext": "hi",
                                   "created_utc": 1767225600}}]}})
    assert reddit[0].url == "https://www.reddit.com/r/x/c/1/" and "r/x" in reddit[0].snippet
    gh = engines.parse_github({"items": [{"full_name": "a/b", "html_url": "https://github.com/a/b",
                                          "stargazers_count": 7, "language": "Lua", "description": "Roblox tools",
                                          "pushed_at": "2026-09-09T00:00:00Z"}]})
    assert gh[0].snippet.startswith("★ 7 · Lua")
    se = engines.parse_stackexchange({"items": [{"title": "How &amp; why", "link": "https://so.com/q/1", "score": 3,
                                                 "answer_count": 1, "is_answered": True, "tags": ["lua"],
                                                 "creation_date": 1767225600}]}, "stackoverflow")
    assert se[0].title == "How & why" and "✔ answered" in se[0].snippet


def test_arxiv_parser():
    results = engines.parse_arxiv((FIX / "arxiv.xml").read_bytes())
    assert results[0].title == "Attention Is All You Need"
    assert results[0].extra["pdf"] == "http://arxiv.org/pdf/1706.03762v7"
    assert results[0].snippet.startswith("Ashish Vaswani, Noam Shazeer")
    with pytest.raises(engines.SearchError):
        engines.parse_arxiv(b"not xml")


def test_web_order_prefers_configured_keys(monkeypatch):
    for key in ("BRAVE_API_KEY", "TAVILY_API_KEY", "SEARXNG_URL"):
        monkeypatch.delenv(key, raising=False)
    assert engines.default_web_order() == ["duckduckgo"]
    monkeypatch.setenv("TAVILY_API_KEY", "x")
    assert engines.default_web_order() == ["tavily", "duckduckgo"]


def test_missing_keys_give_helpful_errors(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    with pytest.raises(engines.SearchError, match="BRAVE_API_KEY"):
        engines.search_brave("x")


def test_unknown_engine():
    with pytest.raises(engines.SearchError):
        engines.run_engine("altavista", "x", 5, "es-es", "es", "")
