"""Small, dependency-free HTTP client built on urllib.

Why not `requests`? The scripts must work even before the installer has run,
with nothing but the Python standard library. This module adds what urllib
lacks out of the box: decompression, size limits, 308 redirects, cookie jars
for logged-in sessions and friendly error messages.
"""

from __future__ import annotations

import gzip
import http.client
import http.cookiejar
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field

MAX_BYTES_DEFAULT = 30 * 1024 * 1024  # 30 MB is plenty for pages and PDFs

try:  # optional: only advertise brotli when we can decode it
    import brotli  # type: ignore

    _HAS_BROTLI = True
except ImportError:  # pragma: no cover - depends on environment
    _HAS_BROTLI = False


@dataclass
class HttpResponse:
    url: str
    final_url: str
    status: int | None
    headers: dict = field(default_factory=dict)
    body: bytes = b""
    elapsed_ms: int = 0
    error: str | None = None
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and self.status is not None and 200 <= self.status < 300

    @property
    def content_type(self) -> str:
        return (self.headers.get("content-type") or "").split(";")[0].strip().lower()

    @property
    def charset(self) -> str | None:
        ctype = self.headers.get("content-type") or ""
        for part in ctype.split(";")[1:]:
            key, _, value = part.strip().partition("=")
            if key.lower() == "charset" and value:
                return value.strip().strip('"').strip("'")
        return None


def ssl_context() -> ssl.SSLContext:
    """Default TLS context, honouring custom CA bundles (corporate proxies)."""
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if cafile and os.path.isfile(cafile):
        return ssl.create_default_context(cafile=cafile)
    ctx = ssl.create_default_context()
    if sys.platform == "darwin":
        # python.org builds on macOS often ship without any CA certificates.
        try:
            if ctx.cert_store_stats().get("x509_ca", 0) == 0:
                import certifi  # type: ignore

                ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:  # pragma: no cover - best effort only
            pass
    return ctx


class _RedirectHandler(urllib.request.HTTPRedirectHandler):
    """urllib before Python 3.11 refuses 308 redirects; treat them like 307."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        if code == 308:
            code = 307
        return super().redirect_request(req, fp, code, msg, headers, newurl)

    http_error_308 = urllib.request.HTTPRedirectHandler.http_error_302


def build_opener(cookiejar: http.cookiejar.CookieJar | None = None) -> urllib.request.OpenerDirector:
    jar = cookiejar if cookiejar is not None else http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.ProxyHandler(),  # honours HTTPS_PROXY / NO_PROXY
        urllib.request.HTTPSHandler(context=ssl_context()),
        urllib.request.HTTPCookieProcessor(jar),
        _RedirectHandler(),
    )


def _decompress(body: bytes, encoding: str | None) -> bytes:
    if not body or not encoding:
        return body
    encoding = encoding.lower().strip()
    try:
        if encoding in ("gzip", "x-gzip"):
            return gzip.decompress(body)
        if encoding == "deflate":
            try:
                return zlib.decompress(body)
            except zlib.error:
                return zlib.decompress(body, -zlib.MAX_WBITS)
        if encoding == "br" and _HAS_BROTLI:
            return brotli.decompress(body)
    except Exception:
        return body
    return body


def describe_error(exc: BaseException) -> str:
    """Turn low-level exceptions into short, actionable reasons."""
    if isinstance(exc, urllib.error.URLError) and exc.reason is not None:
        reason = exc.reason
        if isinstance(reason, socket.gaierror):
            return "dns_error: the host name could not be resolved (typo, or the site no longer exists)"
        if isinstance(reason, ssl.SSLCertVerificationError):
            return f"tls_error: certificate verification failed ({reason.verify_message})"
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return "timeout: the server did not answer in time"
        if isinstance(reason, ConnectionRefusedError):
            return "connection_refused: nothing is listening at that address"
        text = str(reason)
        if "Tunnel connection failed" in text or ("403" in text and "Forbidden" in text):
            return f"proxy_blocked: the network proxy refused the connection ({text})"
        return f"network_error: {text}"
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "timeout: the server did not answer in time"
    if isinstance(exc, ssl.SSLError):
        return f"tls_error: {exc}"
    if isinstance(exc, http.client.IncompleteRead):
        return "network_error: the connection closed before the whole page arrived"
    return f"network_error: {type(exc).__name__}: {exc}"


def http_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict | None = None,
    data: bytes | None = None,
    timeout: float = 30,
    cookiejar: http.cookiejar.CookieJar | None = None,
    max_bytes: int = MAX_BYTES_DEFAULT,
) -> HttpResponse:
    hdrs = dict(headers or {})
    hdrs.setdefault("Accept-Encoding", "gzip, deflate, br" if _HAS_BROTLI else "gzip, deflate")
    request = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    opener = build_opener(cookiejar)
    started = time.monotonic()
    status: int | None = None
    final_url = url
    resp_headers: dict = {}
    body = b""
    truncated = False
    try:
        with opener.open(request, timeout=timeout) as resp:
            status = resp.status
            final_url = resp.geturl()
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            body = resp.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:  # 4xx / 5xx still carry a useful body
        status = exc.code
        final_url = exc.geturl() or url
        resp_headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
        try:
            body = exc.read(max_bytes + 1)
        except Exception:
            body = b""
    except Exception as exc:  # network-level failure
        return HttpResponse(
            url=url,
            final_url=url,
            status=None,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            error=describe_error(exc),
        )
    if len(body) > max_bytes:
        body = body[:max_bytes]
        truncated = True
    body = _decompress(body, resp_headers.get("content-encoding"))
    return HttpResponse(
        url=url,
        final_url=final_url,
        status=status,
        headers=resp_headers,
        body=body,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        truncated=truncated,
    )


def get_json(url: str, *, headers: dict | None = None, timeout: float = 20, data: bytes | None = None,
             method: str | None = None) -> tuple[object | None, HttpResponse]:
    """GET (or POST) a JSON endpoint. Returns (parsed_or_None, response)."""
    import json

    resp = http_request(url, method=method or ("POST" if data else "GET"), headers=headers,
                        data=data, timeout=timeout)
    if resp.error or not resp.body:
        return None, resp
    try:
        return json.loads(resp.body.decode(resp.charset or "utf-8", errors="replace")), resp
    except ValueError:
        return None, resp


def quote_url(url: str) -> str:
    """Percent-encode spaces and unicode in a URL without touching its structure."""
    parts = urllib.parse.urlsplit(url.strip())
    path = urllib.parse.quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
    query = urllib.parse.quote(parts.query, safe="=&%:@!$'()*+,;/?-._~")
    netloc = parts.netloc
    try:
        host = parts.hostname or ""
        if host and any(ord(c) > 127 for c in host):
            netloc = netloc.replace(host, host.encode("idna").decode("ascii"))
    except UnicodeError:
        pass
    return urllib.parse.urlunsplit((parts.scheme, netloc, path, query, parts.fragment))


def normalize_input_url(raw: str) -> str:
    """Accept 'example.com/page' and turn it into 'https://example.com/page'."""
    import re

    raw = raw.strip()
    if not raw:
        return raw
    if raw.startswith("//"):
        raw = "https:" + raw
    if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", raw):
        host = raw.split("/")[0].split(":")[0].lower()
        local = host in ("localhost", "127.0.0.1", "0.0.0.0") or host.endswith(".local")
        raw = ("http://" if local else "https://") + raw
    return quote_url(raw)
