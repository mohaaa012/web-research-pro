"""Heuristics that tell *why* a page did not give us its content.

Knowing the reason is what lets the fetcher pick the right next step:
  js_shell      -> render it in a real browser
  blocked       -> try the reader service / archived copy / other sources
  login_wall    -> ask the user to log in with their own account (login.py)
  paywall_hint  -> say so, look for open sources; never try to bypass it
"""

from __future__ import annotations

import re
import urllib.parse

JS_PHRASES = (
    "enable javascript", "javascript is required", "requires javascript",
    "turn on javascript", "javascript is disabled", "javascript to run this app",
    "please enable js", "need javascript", "activa javascript", "habilita javascript",
    "javascript desactivado", "necesitas javascript", "works best with javascript",
)

# (vendor, markers). Markers are searched in the lower-cased HTML.
CHALLENGE_MARKERS = (
    ("cloudflare", ("cf-browser-verification", "cf_chl_opt", "/cdn-cgi/challenge-platform",
                    "<title>just a moment...</title>", "attention required! | cloudflare",
                    "checking your browser before accessing", "cf-error-details")),
    ("captcha", ("g-recaptcha", "h-captcha", "hcaptcha.com/1/api.js", "captcha-delivery.com",
                 "px-captcha", "are you a robot", "verify you are human", "i'm not a robot",
                 "unusual traffic from your computer", "confirma que no eres un robot")),
    ("datadome", ("datadome",)),
    ("perimeterx", ("perimeterx", "_pxhd", "px-cdn.net")),
    ("akamai", ("errors.edgesuite.net", "you don't have permission to access")),
    ("incapsula", ("_incapsula_resource", "incapsula incident id")),
    ("ddos-guard", ("ddos-guard",)),
    ("aws-waf", ("awswaf", "aws-waf-token")),
    ("generic", ("access denied", "request blocked", "bot detected", "automated requests",
                 "acceso denegado")),
)

LOGIN_URL_HINTS = (
    "/login", "/log-in", "/signin", "/sign-in", "/sign_in", "/auth/", "/sso", "/session/new",
    "/accounts/login", "/account/login", "/users/sign_in", "/iniciar-sesion", "/acceder",
    "/entrar", "returnurl=", "redirect_uri=", "continue=",
)
LOGIN_HOSTS = ("accounts.google.com", "login.microsoftonline.com", "login.live.com",
               "appleid.apple.com", "auth0.com", "okta.com")
LOGIN_PHRASES = (
    "sign in to continue", "log in to continue", "login to continue", "you must be logged in",
    "please log in", "please sign in", "inicia sesión para continuar", "debes iniciar sesión",
    "log in to see", "sign in to see", "create an account or log in",
)
PAYWALL_PHRASES = (
    "subscribe to continue reading", "to continue reading, subscribe", "this article is for subscribers",
    "subscribers only", "suscríbete para seguir leyendo", "contenido exclusivo para suscriptores",
    "para seguir leyendo", "regístrate para seguir leyendo", "unlock this article",
    "you have reached your limit of free articles", "has alcanzado el límite de artículos",
)

_PASSWORD_INPUT = re.compile(r"<input[^>]+type\s*=\s*[\"']?password", re.I)
_EMPTY_ROOT = re.compile(
    r"<div[^>]+id\s*=\s*[\"'](root|app|__next|__nuxt|svelte|main-app|ember-application|application)[\"'][^>]*>\s*</div>",
    re.I,
)


def detect_js_shell(html: str, text_chars: int) -> bool:
    """True when the HTML is an empty application shell filled in by JavaScript."""
    low = html.lower()
    if "<script" not in low:
        return False
    if text_chars < 250:
        return True
    if text_chars < 1500 and any(p in low for p in JS_PHRASES):
        return True
    if text_chars < 800 and _EMPTY_ROOT.search(html):
        return True
    return False


def detect_block(status: int | None, html: str, text_chars: int) -> str | None:
    """Return a short reason when the page is an anti-bot wall, else None."""
    low = html.lower()
    small = text_chars < 2500
    if small:
        for vendor, markers in CHALLENGE_MARKERS:
            if vendor == "generic" and text_chars > 600:
                continue
            if any(m in low for m in markers):
                return f"blocked_{vendor}" + (f"_http{status}" if status and status >= 400 else "")
    if status in (403, 429, 503) and text_chars < 3000:
        return f"blocked_http{status}"
    if status == 451:
        return "blocked_http451_legal"
    return None


def detect_login_wall(final_url: str, html: str, text: str) -> bool:
    try:
        parts = urllib.parse.urlsplit(final_url)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    target = (parts.path + "?" + parts.query).lower()
    low_text = text.lower()
    has_password = bool(_PASSWORD_INPUT.search(html))
    url_hit = any(h in target for h in LOGIN_URL_HINTS) or any(host.endswith(h) for h in LOGIN_HOSTS)
    if url_hit and (has_password or len(text) < 3000):
        return True
    if has_password and len(text) < 1500:
        return True
    if len(text) < 3000 and any(p in low_text for p in LOGIN_PHRASES):
        return True
    return False


def detect_paywall_hint(html: str, text: str) -> bool:
    low = text.lower()
    if any(p in low for p in PAYWALL_PHRASES):
        return True
    return bool(re.search(r"(class|id)\s*=\s*[\"'][^\"']*\bpaywall\b", html, re.I))
