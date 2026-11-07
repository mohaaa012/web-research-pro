"""The plain-HTTP rung of the ladder, against the local test site (no browser needed)."""

import pytest

from wrp import sessions
from wrp.fetcher import FetchOptions, build_chain, fetch, is_private_host
from wrp.net import normalize_input_url

HTTP = FetchOptions(method="http", third_party=False, timeout=10)


def test_article_ok(site):
    r = fetch(site + "/article", HTTP)
    assert r.ok and r.method == "http" and r.status == 200
    assert "Paragraph 24" in r.content
    assert r.metadata["author"] == "Ana García"
    assert r.attempts[0]["method"] == "http"


def test_basic_bot_filter_passes_with_browser_headers(site):
    r = fetch(site + "/ua-check", HTTP)
    assert r.ok and "Paragraph 1" in r.content


def test_basic_bot_filter_blocks_python_user_agent(site, monkeypatch):
    monkeypatch.setenv("WRP_USER_AGENT", "Python-urllib/3.12")
    r = fetch(site + "/ua-check", HTTP)
    assert not r.ok and r.reason == "blocked_by_site"
    assert any("blocks automated access" in s for s in r.suggestions)


def test_challenge_page_is_reported_not_returned_as_content(site):
    r = fetch(site + "/challenge", HTTP)
    assert not r.ok and r.reason == "blocked_by_site"


def test_308_redirect_followed(site):
    r = fetch(site + "/redirect308", HTTP)
    assert r.ok and r.final_url.endswith("/article")


def test_404_is_not_found(site):
    r = fetch(site + "/missing", HTTP)
    assert not r.ok and r.status == 404 and r.reason == "not_found"


def test_pdf(site):
    r = fetch(site + "/doc.pdf", HTTP)
    assert r.ok and r.extractor == "pdf" and "Hello PDF World" in r.content
    assert r.title == "Test Document"


def test_rss_feed(site):
    r = fetch(site + "/feed.xml", HTTP)
    assert r.ok and r.extractor == "feed" and r.metadata["items"] == 2
    assert "Halloween event" in r.content


def test_json(site):
    r = fetch(site + "/data.json", HTTP)
    assert r.ok and r.extractor == "json" and '"players": 12345' in r.content


def test_gzip_and_latin1(site):
    assert "Paragraph 3" in fetch(site + "/gzip", HTTP).content
    r = fetch(site + "/latin1", HTTP)
    assert "Año de la piña" in r.content


def test_timeout_is_reported(site):
    r = fetch(site + "/slow?s=3", FetchOptions(method="http", timeout=1, third_party=False))
    assert not r.ok and "timeout" in r.reason


def test_unreachable_host():
    r = fetch("http://127.0.0.1:9/nothing", HTTP)
    assert not r.ok and r.reason.startswith(("connection_refused", "network_error"))


def test_private_page_without_session_is_login_wall(site):
    r = fetch(site + "/private", HTTP)
    assert not r.ok and r.reason == "login_required"
    assert any("login.py save" in s for s in r.suggestions)


def test_private_page_with_imported_cookies(site, tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n127.0.0.1\tFALSE\t/\tFALSE\t0\tsid\ts3cret\n")
    sessions.save_state("local", sessions.import_cookie_file(cookie_file))
    r = fetch(site + "/private", FetchOptions(method="http", session="local", timeout=10))
    assert r.ok and "1,234 Robux" in r.content


def test_missing_session_raises():
    with pytest.raises(sessions.SessionError):
        fetch("https://example.com", FetchOptions(session="does-not-exist"))


def test_chain_rules():
    assert build_chain(FetchOptions(), "https://example.com") == ["http", "browser", "reader", "archive"]
    assert build_chain(FetchOptions(), "http://127.0.0.1:8000/x") == ["http", "browser"]
    assert build_chain(FetchOptions(session="x"), "https://example.com") == ["http", "browser"]
    assert build_chain(FetchOptions(third_party=False), "https://example.com") == ["http", "browser"]
    assert build_chain(FetchOptions(scroll=2), "https://example.com")[0] == "browser"
    assert build_chain(FetchOptions(method="archive"), "https://example.com") == ["archive"]


def test_private_hosts():
    for url in ("http://localhost:3000", "http://192.168.1.10/admin", "http://intranet/", "http://nas.local/"):
        assert is_private_host(url)
    assert not is_private_host("https://example.com")


def test_url_normalisation():
    assert normalize_input_url("example.com/a b") == "https://example.com/a%20b"
    assert normalize_input_url("localhost:8000/x") == "http://localhost:8000/x"
    assert normalize_input_url("https://es.wikipedia.org/wiki/Año") == "https://es.wikipedia.org/wiki/A%C3%B1o"
    assert normalize_input_url("https://x.com/p?q=1%202") == "https://x.com/p?q=1%202"
