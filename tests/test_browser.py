"""The browser rung: JavaScript pages, infinite scroll, screenshots, sessions."""

import pytest

from conftest import browser_available
from wrp import sessions
from wrp.fetcher import FetchOptions, fetch

pytestmark = pytest.mark.skipif(not browser_available(), reason="Playwright/Chromium not available")


def test_auto_escalates_from_http_to_browser_for_js_apps(site):
    r = fetch(site + "/spa", FetchOptions(timeout=20))
    assert r.ok and r.method == "browser"
    assert [a["method"] for a in r.attempts] == ["http", "browser"]
    assert r.attempts[0]["reason"] == "js_shell"
    assert "The secret number is 4242" in r.content
    assert r.title == "Rendered app"


def test_scroll_loads_more_items(site):
    few = fetch(site + "/scroll", FetchOptions(method="browser", timeout=20))
    many = fetch(site + "/scroll", FetchOptions(method="browser", scroll=4, timeout=20))
    assert "Item number 5 " in few.content and "Item number 11 " not in few.content
    assert "Item number 15 " in many.content


def test_screenshot(site, tmp_path):
    shot = tmp_path / "page.png"
    r = fetch(site + "/article", FetchOptions(screenshot=str(shot), timeout=20))
    assert r.ok and r.method == "browser"
    assert shot.exists() and shot.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_wait_for_selector(site):
    r = fetch(site + "/spa", FetchOptions(method="browser", wait_for="h1", timeout=20))
    assert "Rendered by JavaScript" in r.content


def test_browser_uses_saved_session(site):
    sessions.save_state("local", {"cookies": [{"name": "sid", "value": "s3cret", "domain": "127.0.0.1", "path": "/",
                                               "expires": -1, "httpOnly": False, "secure": False, "sameSite": "Lax"}],
                                  "origins": []})
    r = fetch(site + "/private", FetchOptions(method="browser", session="local", timeout=20))
    assert r.ok and "Welcome back, Mo" in r.content


def test_login_wall_in_browser_without_session(site):
    r = fetch(site + "/private", FetchOptions(timeout=20))
    assert not r.ok and r.reason == "login_required"
    assert [a["method"] for a in r.attempts] == ["http", "browser"]


def test_blocked_everywhere_reports_cleanly(site):
    r = fetch(site + "/challenge", FetchOptions(timeout=20))
    assert not r.ok and r.reason == "blocked_by_site"
    assert len(r.attempts) == 2  # local address: no third-party fallbacks
