from server import ARTICLE, CHALLENGE, LOGIN, SPA
from wrp import detect


def test_js_shell_detected():
    assert detect.detect_js_shell(SPA, text_chars=40)
    assert not detect.detect_js_shell("<html><body><p>plain page</p></body></html>", text_chars=10)
    assert not detect.detect_js_shell(ARTICLE, text_chars=3000)


def test_cloudflare_challenge_is_blocked():
    assert detect.detect_block(403, CHALLENGE, 60).startswith("blocked_cloudflare")
    assert detect.detect_block(200, CHALLENGE, 60).startswith("blocked_cloudflare")


def test_plain_403_and_429_are_blocked():
    assert detect.detect_block(429, "<html>slow down</html>", 10) == "blocked_http429"
    assert detect.detect_block(403, "<html>nope</html>", 4) == "blocked_http403"


def test_long_article_mentioning_captcha_is_not_a_block():
    html = "<p>" + "How a captcha (g-recaptcha) works. " * 200 + "</p>"
    assert detect.detect_block(200, html, 7000) is None


def test_login_wall():
    assert detect.detect_login_wall("https://site.com/login?next=/x", LOGIN, "Sign in Log in")
    assert detect.detect_login_wall("https://site.com/whatever", LOGIN, "Sign in")
    assert not detect.detect_login_wall("https://site.com/blog", ARTICLE, "long article " * 300)


def test_paywall_hint():
    assert detect.detect_paywall_hint("", "Subscribe to continue reading this story")
    assert detect.detect_paywall_hint('<div class="article paywall">', "text")
    assert not detect.detect_paywall_hint(ARTICLE, "normal text")
