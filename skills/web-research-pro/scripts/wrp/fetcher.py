"""The escalation ladder: try the cheapest method first, climb only when needed.

    http  ->  browser  ->  reader (r.jina.ai)  ->  archive (Wayback Machine)

Every attempt is recorded, so the final answer can say exactly how the
content was obtained (or why it could not be), instead of guessing.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
from dataclasses import asdict, dataclass, field

from . import detect, extract
from .config import api_headers, browser_headers
from .net import HttpResponse, http_request, normalize_input_url
from .sessions import load_state, save_state, to_cookiejar

READER_ENDPOINT = os.environ.get("WRP_READER_URL", "https://r.jina.ai/")
WAYBACK_AVAILABLE = "https://archive.org/wayback/available"
WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"


@dataclass
class Attempt:
    method: str
    ok: bool
    status: int | None = None
    reason: str = ""
    elapsed_ms: int = 0
    chars: int = 0


@dataclass
class FetchOptions:
    method: str = "auto"            # auto | http | browser | reader | archive
    session: str | None = None
    extract_mode: str = "auto"      # auto | main | full
    timeout: float = 30
    wait_for: str | None = None
    clicks: tuple = ()
    scroll: int = 0
    wait_ms: int = 0
    screenshot: str | None = None
    headed: bool = False
    third_party: bool = True        # allow reader + archive fallbacks
    keep_html: bool = False
    archive_date: str | None = None  # YYYYMMDD: snapshot closest to this date
    max_pdf_pages: int | None = None


@dataclass
class FetchResult:
    url: str
    final_url: str = ""
    ok: bool = False
    method: str = ""
    status: int | None = None
    title: str = ""
    content: str = ""
    content_type: str = ""
    extractor: str = ""
    metadata: dict = field(default_factory=dict)
    links: list = field(default_factory=list)
    attempts: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)
    archived_at: str = ""
    screenshot: str = ""
    html: str = ""
    fetched_at: str = ""
    reason: str = ""

    @property
    def chars(self) -> int:
        return len(self.content)

    def to_dict(self, include_html: bool = False) -> dict:
        data = asdict(self)
        data["chars"] = self.chars
        if not include_html:
            data.pop("html", None)
        return data


# ---------------------------------------------------------------------------
# Converting a response body into a result
# ---------------------------------------------------------------------------

def _from_body(result: FetchResult, body: bytes, content_type: str, charset: str | None,
               final_url: str, status: int | None, opts: FetchOptions) -> str:
    """Fill result from bytes. Returns a verdict: ok | js_shell | blocked | login | empty | error:..."""
    result.final_url = final_url
    result.status = status
    if extract.looks_like_pdf(body):
        try:
            title, text, meta = extract.pdf_to_text(body, opts.max_pdf_pages)
        except RuntimeError as exc:
            return f"error:{exc}"
        result.content_type = "application/pdf"
        result.title = title or os.path.basename(urllib.parse.urlsplit(final_url).path) or final_url
        result.content = text
        result.extractor = "pdf"
        result.metadata.update(meta)
        if meta.get("warning"):
            result.warnings.append(meta["warning"])
        return "ok" if text.strip() else "empty"
    result.content_type = content_type or "text/html"
    if "json" in content_type:
        text = extract.json_to_text(body, charset)
        if text is not None:
            result.content, result.extractor = text, "json"
            result.title = result.title or final_url
            return "ok"
    if extract.is_feed_type(content_type) or body.lstrip()[:5] in (b"<?xml", b"<rss ", b"<feed"):
        parsed = extract.parse_feed(body)
        if parsed is not None:
            title, items = parsed
            result.title = title or final_url
            result.content = extract.feed_to_markdown(title, items)
            result.extractor = "feed"
            result.metadata["items"] = len(items)
            return "ok"
    if any(content_type.startswith(t) for t in extract.TEXT_TYPES):
        result.content = body.decode(charset or "utf-8", errors="replace")
        result.extractor = "text"
        result.title = result.title or final_url
        return "ok" if result.content.strip() else "empty"
    if content_type.startswith(("image/", "video/", "audio/", "font/")) or content_type in (
            "application/zip", "application/octet-stream"):
        result.content = ""
        return f"error:unsupported_content_type: {content_type} (binary file; download it and open it locally)"
    html = extract.decode_html(body, charset)
    if opts.keep_html:
        result.html = html
    ex = extract.extract_html(html, final_url, opts.extract_mode)
    result.title = ex.title or result.title
    result.content = ex.content
    result.extractor = ex.extractor
    result.links = ex.links
    info = ex.info
    for key in ("author", "published", "site_name", "description", "lang", "canonical"):
        value = getattr(info, key, "")
        if value:
            result.metadata[key] = value
    if info.feeds:
        result.metadata["feeds"] = info.feeds[:5]
    text_chars = ex.full_text_chars
    if detect.detect_login_wall(final_url, html, ex.content):
        return "login"
    block = detect.detect_block(status, html, text_chars)
    if block:
        result.reason = block
        return "blocked"
    if detect.detect_js_shell(html, text_chars):
        return "js_shell"
    if detect.detect_paywall_hint(html, ex.content):
        result.warnings.append("paywall_hint: part of the article may be reserved for subscribers")
    if status and status >= 400:
        return f"http_{status}"
    return "ok" if text_chars > 0 else "empty"


# ---------------------------------------------------------------------------
# Individual methods
# ---------------------------------------------------------------------------

def _try_http(url: str, opts: FetchOptions, state: dict | None) -> tuple[FetchResult, Attempt, str]:
    result = FetchResult(url=url)
    jar = to_cookiejar(state) if state else None
    resp: HttpResponse = http_request(url, headers=browser_headers(), timeout=opts.timeout, cookiejar=jar)
    if resp.error:
        return result, Attempt("http", False, None, resp.error, resp.elapsed_ms), "error:" + resp.error
    verdict = _from_body(result, resp.body, resp.content_type, resp.charset, resp.final_url, resp.status, opts)
    if resp.truncated:
        result.warnings.append("download stopped at 30 MB; content is incomplete")
    ok = verdict == "ok"
    attempt = Attempt("http", ok, resp.status, verdict if not ok else "", resp.elapsed_ms, result.chars)
    return result, attempt, verdict


def _try_browser(url: str, opts: FetchOptions, state: dict | None, browser) -> tuple[FetchResult, Attempt, str]:
    from .browser import BrowserUnavailable

    result = FetchResult(url=url)
    started = time.monotonic()
    try:
        rendered = browser.render(
            url, storage_state=state, wait_for=opts.wait_for, clicks=opts.clicks, scroll=opts.scroll,
            wait_ms=opts.wait_ms, screenshot=opts.screenshot, timeout=opts.timeout,
        )
    except BrowserUnavailable as exc:
        reason = str(exc)
        return result, Attempt("browser", False, None, reason, int((time.monotonic() - started) * 1000)), "error:" + reason
    if rendered.get("screenshot"):
        result.screenshot = rendered["screenshot"]
    for note in rendered.get("notes", []):
        result.warnings.append(f"browser: {note}")
    if rendered.get("storage_state") and opts.session:
        try:  # keep the user's session fresh (sites rotate cookies)
            save_state(opts.session, rendered["storage_state"])
        except Exception:
            pass
    html = rendered.get("html") or ""
    if rendered.get("error") and len(html) < 500:
        reason = rendered["error"]
        return result, Attempt("browser", False, rendered.get("status"), reason, rendered["elapsed_ms"]), "error:" + reason
    if rendered.get("error"):
        result.warnings.append(f"browser: {rendered['error']} (kept what had rendered)")
    result.title = rendered.get("title") or ""
    verdict = _from_body(result, html.encode("utf-8"), "text/html", "utf-8",
                         rendered.get("final_url") or url, rendered.get("status"), opts)
    if verdict == "js_shell":
        # The browser already ran the scripts; whatever is there is the page.
        verdict = "ok" if result.chars > 0 else "empty"
    ok = verdict == "ok"
    attempt = Attempt("browser", ok, rendered.get("status"), "" if ok else verdict, rendered["elapsed_ms"], result.chars)
    return result, attempt, verdict


def _try_reader(url: str, opts: FetchOptions) -> tuple[FetchResult, Attempt, str]:
    """r.jina.ai turns a URL into clean Markdown on their servers.
    Third-party: the URL (never cookies) is sent to Jina AI."""
    result = FetchResult(url=url)
    headers = api_headers({"Accept": "text/plain", "X-Return-Format": "markdown"})
    key = os.environ.get("JINA_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = http_request(READER_ENDPOINT + url, headers=headers, timeout=max(opts.timeout, 40))
    if resp.error:
        return result, Attempt("reader", False, None, resp.error, resp.elapsed_ms), "error:" + resp.error
    text = resp.body.decode(resp.charset or "utf-8", errors="replace").strip()
    if resp.status != 200 or len(text) < 80:
        reason = f"reader_http_{resp.status}" if resp.status != 200 else "reader_empty"
        return result, Attempt("reader", False, resp.status, reason, resp.elapsed_ms), reason
    title, content, source = "", text, url
    if text.startswith("Title:"):
        head, sep, rest = text.partition("Markdown Content:")
        if sep:
            content = rest.strip()
            for line in head.splitlines():
                if line.startswith("Title:"):
                    title = line[len("Title:"):].strip()
                elif line.startswith("URL Source:"):
                    source = line[len("URL Source:"):].strip() or url
                elif line.startswith("Published Time:"):
                    result.metadata["published"] = line[len("Published Time:"):].strip()
    probe = content[:3000].lower()
    if len(content) < 2500 and any(m in probe for _, ms in detect.CHALLENGE_MARKERS[:2] for m in ms):
        return result, Attempt("reader", False, resp.status, "reader_got_challenge_page", resp.elapsed_ms), "blocked"
    if "warning: target url returned error" in text.lower()[:600] and len(content) < 600:
        return result, Attempt("reader", False, resp.status, "reader_target_error", resp.elapsed_ms), "blocked"
    result.final_url = source
    result.status = 200
    result.title = title or url
    result.content = content
    result.content_type = "text/markdown"
    result.extractor = "jina-reader"
    result.warnings.append("content converted by the third-party reader service r.jina.ai")
    return result, Attempt("reader", True, 200, "", resp.elapsed_ms, len(content)), "ok"


def find_snapshot(url: str, date: str | None = None, timeout: float = 25) -> tuple[str | None, str | None, str]:
    """Return (snapshot_url, timestamp, note) for the Wayback Machine copy closest to date."""
    params = {"url": url}
    if date:
        params["timestamp"] = date
    resp = http_request(f"{WAYBACK_AVAILABLE}?{urllib.parse.urlencode(params)}", headers=api_headers(), timeout=timeout)
    if not resp.error and resp.status == 200:
        try:
            closest = json.loads(resp.body.decode("utf-8", "replace")).get("archived_snapshots", {}).get("closest")
        except ValueError:
            closest = None
        if closest and closest.get("available") and closest.get("timestamp"):
            return closest.get("url"), closest["timestamp"], "availability-api"
    # The availability API is flaky; the CDX index is the reliable backup.
    cdx = {"url": url, "output": "json", "fl": "timestamp,original,statuscode", "filter": "statuscode:200", "limit": "-1"}
    if date:
        cdx = {"url": url, "output": "json", "fl": "timestamp,original,statuscode",
               "filter": "statuscode:200", "closest": date, "sort": "closest", "limit": "1"}
    resp = http_request(f"{WAYBACK_CDX}?{urllib.parse.urlencode(cdx)}", headers=api_headers(), timeout=timeout)
    if resp.error:
        return None, None, resp.error
    try:
        rows = json.loads(resp.body.decode("utf-8", "replace") or "[]")
    except ValueError:
        return None, None, f"cdx_bad_response_http_{resp.status}"
    rows = [r for r in rows if r and r[0] != "timestamp"]
    if not rows:
        return None, None, "no_snapshot"
    timestamp, original = rows[-1][0], rows[-1][1]
    return f"https://web.archive.org/web/{timestamp}/{original}", timestamp, "cdx"


def _try_archive(url: str, opts: FetchOptions) -> tuple[FetchResult, Attempt, str]:
    result = FetchResult(url=url)
    started = time.monotonic()
    snap_url, timestamp, note = find_snapshot(url, opts.archive_date, timeout=opts.timeout)
    if not snap_url or not timestamp:
        reason = "archive_no_snapshot" if note == "no_snapshot" else f"archive_lookup_failed: {note}"
        return result, Attempt("archive", False, None, reason, int((time.monotonic() - started) * 1000)), reason
    # "id_" asks for the original bytes, without the Wayback toolbar.
    original = snap_url.split(f"/{timestamp}/", 1)[-1]
    raw_url = f"https://web.archive.org/web/{timestamp}id_/{original}"
    resp = http_request(raw_url, headers=browser_headers(), timeout=max(opts.timeout, 40))
    elapsed = int((time.monotonic() - started) * 1000)
    if resp.error:
        return result, Attempt("archive", False, None, resp.error, elapsed), "error:" + resp.error
    verdict = _from_body(result, resp.body, resp.content_type, resp.charset, url, resp.status, opts)
    pretty = f"{timestamp[0:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
    result.archived_at = pretty
    result.final_url = url
    result.metadata["archive_url"] = f"https://web.archive.org/web/{timestamp}/{original}"
    result.warnings.append(f"ARCHIVED COPY from {pretty} (Wayback Machine): it may be outdated")
    ok = verdict == "ok" and result.chars > 0
    return result, Attempt("archive", ok, resp.status, "" if ok else verdict, elapsed, result.chars), ("ok" if ok else verdict)


# ---------------------------------------------------------------------------
# The ladder
# ---------------------------------------------------------------------------

def is_private_host(url: str) -> bool:
    """Local / intranet addresses: third-party services cannot (and should not) see them."""
    import ipaddress

    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if not host or host == "localhost" or host.endswith((".local", ".localhost", ".internal", ".lan", ".home")):
        return True
    if "." not in host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


def build_chain(opts: FetchOptions, url: str = "") -> list[str]:
    if opts.method != "auto":
        return [opts.method]
    interactive = bool(opts.wait_for or opts.clicks or opts.scroll or opts.screenshot or opts.headed)
    chain = ["browser"] if interactive else ["http", "browser"]
    # Never send private pages to third parties: not with the user's session,
    # not for intranet/localhost addresses, not when the user opted out.
    if opts.third_party and not opts.session and not (url and is_private_host(url)):
        chain += ["reader", "archive"]
    return chain


def fetch(url: str, opts: FetchOptions | None = None, browser=None) -> FetchResult:
    opts = opts or FetchOptions()
    url = normalize_input_url(url)
    state = load_state(opts.session) if opts.session else None
    chain = build_chain(opts, url)
    attempts: list[Attempt] = []
    candidates: list[tuple[int, FetchResult]] = []
    own_browser = None
    verdicts: list[str] = []
    try:
        index = 0
        while index < len(chain):
            method = chain[index]
            index += 1
            if method == "http":
                result, attempt, verdict = _try_http(url, opts, state)
            elif method == "browser":
                if browser is None:
                    from .browser import Browser

                    own_browser = browser = Browser(headed=opts.headed)
                result, attempt, verdict = _try_browser(url, opts, state, browser)
            elif method == "reader":
                result, attempt, verdict = _try_reader(url, opts)
            elif method == "archive":
                result, attempt, verdict = _try_archive(url, opts)
            else:
                raise ValueError(f"unknown method: {method}")
            attempts.append(attempt)
            verdicts.append(verdict)
            if verdict == "ok":
                result.ok = True
                result.method = method
                return _finish(result, attempts)
            if result.chars:
                candidates.append((result.chars, result))
            # Smart skipping: a missing page will not appear in a browser,
            # but the archive may still remember it.
            if method == "http" and verdict in ("http_404", "http_410") and "archive" in chain:
                chain = [m for m in chain[index:] if m == "archive"]
                index = 0
            elif verdict == "login" and opts.session is None and method == "browser":
                # Without the user's session every other public route sees the same wall.
                break
    finally:
        if own_browser is not None:
            own_browser.close()
    # Nothing was fully satisfying: return the best partial result, clearly flagged.
    best = max(candidates, key=lambda pair: pair[0])[1] if candidates else FetchResult(url=url)
    best.ok = False
    best.method = attempts[-1].method if attempts else ""
    best.reason = _summarize_failure(verdicts, attempts)
    best.suggestions = _suggestions(verdicts, attempts, opts, url)
    return _finish(best, attempts)


def _finish(result: FetchResult, attempts: list[Attempt]) -> FetchResult:
    result.attempts = [asdict(a) for a in attempts]
    result.fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if not result.final_url:
        result.final_url = result.url
    return result


def _summarize_failure(verdicts: list[str], attempts: list[Attempt]) -> str:
    if "login" in verdicts:
        return "login_required"
    if any(v == "blocked" for v in verdicts):
        return "blocked_by_site"
    if any(v.startswith("http_404") or v.startswith("http_410") for v in verdicts):
        return "not_found"
    if any("playwright_not_installed" in a.reason or "browser_launch_failed" in a.reason for a in attempts):
        if any(v == "js_shell" for v in verdicts):
            return "needs_browser"
    if any(v == "js_shell" for v in verdicts):
        return "javascript_page_not_rendered"
    if attempts and all(a.reason.startswith(("dns_error", "network_error", "timeout", "proxy_blocked",
                                             "connection_refused", "tls_error")) for a in attempts):
        return attempts[0].reason
    return attempts[-1].reason if attempts else "no_attempts"


def _suggestions(verdicts: list[str], attempts: list[Attempt], opts: FetchOptions, url: str) -> list[str]:
    tips = []
    host = urllib.parse.urlsplit(url).hostname or url
    reasons = " ".join(a.reason for a in attempts)
    if "playwright_not_installed" in reasons or "browser_launch_failed" in reasons:
        tips.append("Install the browser once: python3 scripts/doctor.py --setup")
    if "login" in verdicts:
        tips.append(f"The page needs an account. If it is the user's own account: "
                    f"login.py save {host.split('.')[-2] if host.count('.') else host} --url <login page>, "
                    f"then fetch.py ... --session <name>")
        if opts.session:
            tips.append("The saved session may have expired: save it again with login.py save")
    if "blocked" in verdicts:
        tips.append("The site blocks automated access. Look for the same facts elsewhere: official API, "
                    "RSS feed, press release, cached copy, other outlets quoting it")
        tips.append("Or ask the user to open the page in their own browser and save it (PDF/HTML), then read the file")
    if not opts.third_party:
        tips.append("Third-party fallbacks are off; allow them (drop --no-third-party) to try r.jina.ai and the Wayback Machine")
    proxied = [a.method for a in attempts if "proxy_blocked" in a.reason]
    if proxied:
        tips.append(f"This machine's network proxy/firewall refused the {', '.join(proxied)} step(s): "
                    "that is the local network policy, not the website")
    if "dns_error" in reasons:
        tips.append("Check the address for typos; the domain may not exist any more")
    return tips
