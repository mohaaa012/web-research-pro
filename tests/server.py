"""A local website that reproduces every hard case the skill must handle.

Started once per test session by conftest.py on a random free port.
"""

from __future__ import annotations

import gzip
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

STATE = {"price": "19,99 €", "counter": 0}

NAV = '<nav><a href="/">Home</a> <a href="/about">About</a> <a href="/contact">Contact</a></nav>'
FOOTER = "<footer><p>© 2026 Example Corp · <a href='/privacy'>Privacy</a></p></footer>"

ARTICLE_BODY = " ".join(
    f"Paragraph {i}: Roblox creators keep players engaged with collectibles, daily rewards and social events."
    for i in range(1, 25)
)

ARTICLE = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>How progression systems keep players</title>
<meta name="author" content="Ana García"><meta property="article:published_time" content="2026-03-14">
<link rel="alternate" type="application/rss+xml" href="/feed.xml">
<style>body{{color:red}}</style><script>var tracking = 1;</script></head>
<body>{NAV}<main><article><h1>How progression systems keep players</h1>
<p>{ARTICLE_BODY}</p>
<h2>Key numbers</h2>
<table><tr><th>Metric</th><th>Value</th></tr><tr><td>D1 retention</td><td>42%</td></tr></table>
<ul><li>Pets</li><li>Eggs</li><li>Trading</li></ul>
<pre>def reward(player):
    player.coins += 10</pre>
<p>Read the <a href="/guide?utm_source=x">full guide</a>.</p></article></main>{FOOTER}</body></html>"""

LISTING = "<html><head><title>Book shop</title></head><body>" + NAV + "<h1>All books</h1><ol>" + "".join(
    f"<li><article><h3><a href='/book/{i}'>Book number {i}</a></h3><p class='price'>£{10 + i}.99</p>"
    f"<p>In stock</p></article></li>" for i in range(1, 21)
) + "</ol>" + FOOTER + "</body></html>"

SPA = """<!doctype html><html><head><title>Loading…</title></head><body>
<div id="root"></div>
<noscript>You need to enable JavaScript to run this app.</noscript>
<script>
setTimeout(function(){
  document.title = 'Rendered app';
  document.getElementById('root').innerHTML =
    '<h1>Rendered by JavaScript</h1><p>The secret number is 4242.</p>' +
    '<p>Downloads all time: 1,665,332,828</p>';
}, 150);
</script></body></html>"""

SCROLL = """<!doctype html><html><head><title>Infinite</title></head><body><h1>Feed</h1><div id="list"></div>
<script>
var n = 0;
function more(){ for (var i=0;i<5;i++){ n++; var p=document.createElement('p');
  p.textContent='Item number '+n+' with enough words to count as content'; document.getElementById('list').appendChild(p);}
  var s=document.createElement('div'); s.style.height='1500px'; document.getElementById('list').appendChild(s);}
more();
window.addEventListener('scroll', function(){ if (n < 30 && window.innerHeight + window.scrollY >= document.body.scrollHeight - 50) more(); });
</script></body></html>"""

CHALLENGE = """<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>
<div id="cf-browser-verification">Checking your browser before accessing the site.</div>
<script src="/cdn-cgi/challenge-platform/h/b/orchestrate/jsch/v1"></script></body></html>"""

LOGIN = """<html><head><title>Sign in</title></head><body><h1>Sign in</h1>
<form method="post" action="/login"><input name="user"><input type="password" name="pw"><button>Log in</button></form>
</body></html>"""

PRIVATE = "<html><head><title>My dashboard</title></head><body><h1>Welcome back, Mo</h1>" \
          "<p>Your balance is 1,234 Robux. Private order history: #A1, #A2, #A3.</p>" + "<p>Details.</p>" * 30 + \
          "</body></html>"

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Dev blog</title>
<item><title>Update 1.2 released</title><link>https://example.com/u12</link><pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate>
<description>&lt;p&gt;New pets and a trading plaza.&lt;/p&gt;</description></item>
<item><title>Halloween event</title><link>https://example.com/halloween</link><description>Spooky eggs.</description></item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Atom news</title>
<entry><title>First entry</title><link rel="alternate" href="https://example.com/first"/><updated>2026-10-01T00:00:00Z</updated>
<summary>Hello atom</summary></entry></feed>"""

ROBOTS = "User-agent: *\nDisallow: /site/secret/\nSitemap: {base}/sitemap.xml\n"

SITE = {
    "/site/": "<h1>Site home</h1><a href='/site/a'>A</a> <a href='/site/b?utm_source=news'>B</a> "
              "<a href='/site/secret/x'>Secret</a> <a href='/other/page'>Other</a> "
              "<a href='https://external.example.org/'>External</a> <a href='/site/logo.png'>logo</a>",
    "/site/a": "<h1>Page A</h1><p>Alpha content.</p><a href='/site/c'>C</a>",
    "/site/b": "<h1>Page B</h1><p>Beta content.</p>",
    "/site/c": "<h1>Page C</h1><p>Gamma content.</p>",
    "/site/secret/x": "<h1>Secret</h1>",
    "/other/page": "<h1>Out of scope</h1>",
}


def make_pdf(text: str = "Hello PDF World", title: str = "Test Document") -> bytes:
    stream = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Title (" + title.encode() + b") /Author (Test Author) >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 6 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "TestSite/1.0"

    def log_message(self, *args):  # keep test output clean
        pass

    def _send(self, status: int, body, ctype: str = "text/html; charset=utf-8", headers: dict | None = None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_POST(self):  # noqa: N802
        self.do_GET()

    def do_GET(self):  # noqa: N802
        parts = urlsplit(self.path)
        path, query = parts.path, parse_qs(parts.query)
        base = f"http://{self.headers.get('Host')}"
        ua = self.headers.get("User-Agent", "")
        cookies = self.headers.get("Cookie", "")
        if path in ("/", "/article"):
            return self._send(200, ARTICLE)
        if path == "/listing":
            return self._send(200, LISTING)
        if path == "/spa":
            return self._send(200, SPA)
        if path == "/scroll":
            return self._send(200, SCROLL)
        if path == "/ua-check":
            if "Mozilla" not in ua:
                return self._send(403, CHALLENGE)
            return self._send(200, ARTICLE)
        if path == "/challenge":
            return self._send(403, CHALLENGE)
        if path == "/login":
            return self._send(200, LOGIN)
        if path == "/private":
            if "sid=s3cret" in cookies:
                return self._send(200, PRIVATE)
            return self._send(302, "", headers={"Location": "/login?next=/private"})
        if path == "/doc.pdf":
            return self._send(200, make_pdf(), "application/pdf")
        if path == "/feed.xml":
            return self._send(200, RSS, "application/rss+xml")
        if path == "/atom.xml":
            return self._send(200, ATOM, "application/atom+xml")
        if path == "/data.json":
            return self._send(200, json.dumps({"game": "Pet Sim", "players": 12345, "tags": ["pets", "eggs"]}),
                              "application/json")
        if path == "/redirect308":
            return self._send(308, "", headers={"Location": "/article"})
        if path == "/missing":
            return self._send(404, "<html><head><title>Not found</title></head><body><h1>404</h1></body></html>")
        if path == "/gzip":
            return self._send(200, gzip.compress(ARTICLE.encode()), headers={"Content-Encoding": "gzip"})
        if path == "/latin1":
            html = "<html><head><meta charset='iso-8859-1'><title>Español</title></head><body>" \
                   "<p>Año de la piña: señal clara.</p>" + "<p>Texto en español con eñes.</p>" * 20 + "</body></html>"
            return self._send(200, html.encode("iso-8859-1"), "text/html")
        if path == "/slow":
            time.sleep(float(query.get("s", ["5"])[0]))
            return self._send(200, ARTICLE)
        if path == "/price":
            return self._send(200, f"<html><head><title>Product</title></head><body><h1>Gaming chair</h1>"
                                   f"<p>Precio: {STATE['price']}</p>" + "<p>Comfortable.</p>" * 10 + "</body></html>")
        if path == "/counter":
            STATE["counter"] += 1
            return self._send(200, f"<html><body><p>Visits: {STATE['counter']}</p></body></html>")
        if path == "/robots.txt":
            return self._send(200, ROBOTS.format(base=base), "text/plain")
        if path == "/sitemap.xml":
            xml = ('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                   f"<url><loc>{base}/site/a</loc></url><url><loc>{base}/site/b</loc></url>"
                   f"<url><loc>{base}/site/secret/x</loc></url></urlset>")
            return self._send(200, xml, "application/xml")
        if path in SITE:
            return self._send(200, f"<html><head><title>{path}</title></head><body>{SITE[path]}</body></html>")
        if path == "/headers":
            return self._send(200, json.dumps(dict(self.headers)), "application/json")
        return self._send(404, "<html><body><h1>Not found</h1></body></html>")


def start() -> tuple[ThreadingHTTPServer, str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"
