"""Turn raw bytes (HTML, PDF, RSS/Atom, JSON, text) into clean, readable text.

HTML goes through trafilatura when it is installed (excellent at keeping the
article and dropping menus, cookie banners and footers). A built-in converter
based on the standard library handles everything else and is also used for
listing pages (search results, product grids) where "main content"
extraction would throw away exactly what the user wants.
"""

from __future__ import annotations

import html as html_lib
import io
import json
import re
import shutil
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------

_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_\-:.]+)""", re.I)


def decode_html(body: bytes, header_charset: str | None = None) -> str:
    candidates = []
    if header_charset:
        candidates.append(header_charset)
    match = _META_CHARSET.search(body[:8192])
    if match:
        candidates.append(match.group(1).decode("ascii", "ignore"))
    candidates.append("utf-8")
    for enc in candidates:
        try:
            return body.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("cp1252", errors="replace")


# ---------------------------------------------------------------------------
# Built-in HTML -> Markdown converter (standard library only)
# ---------------------------------------------------------------------------

_SKIP = {"script", "style", "noscript", "template", "svg", "canvas", "iframe", "object",
         "embed", "select", "button", "map"}
_BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "nav", "aside",
          "ul", "ol", "table", "thead", "tbody", "tfoot", "blockquote", "figure",
          "figcaption", "dl", "dt", "dd", "form", "fieldset", "details", "summary",
          "address", "hgroup", "center"}
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_VOID = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed",
         "source", "track", "wbr", "param"}
_HEAD_TAGS = {"meta", "link", "title", "script", "style", "base", "noscript", "template"}


@dataclass
class PageInfo:
    title: str = ""
    description: str = ""
    author: str = ""
    published: str = ""
    site_name: str = ""
    canonical: str = ""
    lang: str = ""
    feeds: list = field(default_factory=list)


_BOILERPLATE = {"nav", "footer"}


class _MarkdownParser(HTMLParser):
    """One pass, two outputs: the whole page (out_full) and the page without
    site menus and footers (out_page). Links are collected from everything."""

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.out_full: list[str] = []
        self.out_page: list[str] = []
        self.skip_depth = 0
        self.boiler_depth = 0
        self.in_head = False
        self.in_title = False
        self.title_parts: list[str] = []
        self.pre_depth = 0
        self.link_stack: list[tuple[str | None, list[str]]] = []
        self.links: list[tuple[str, str]] = []
        self.info = PageInfo()

    # -- helpers -----------------------------------------------------------
    def _emit(self, text: str) -> None:
        if self.link_stack:
            self.link_stack[-1][1].append(text)
            return
        self.out_full.append(text)
        if not self.boiler_depth:
            self.out_page.append(text)

    def _absolute(self, href: str | None) -> str | None:
        if not href:
            return None
        href = href.strip()
        if href.startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
            return None
        try:
            absolute = urllib.parse.urljoin(self.base_url, href)
        except ValueError:
            return None
        if not absolute.startswith(("http://", "https://")):
            return None
        return absolute.split("#")[0] or None

    # -- parser callbacks ----------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and a.get("lang"):
            self.info.lang = a["lang"]
        if tag == "head":
            self.in_head = True
        elif self.in_head and (tag == "body" or tag not in _HEAD_TAGS):
            # </head> is optional in HTML5: the first body-level tag ends the head.
            self.in_head = False
        if tag == "meta":
            self._meta(a)
            return
        if tag == "link":
            rel = a.get("rel", "").lower()
            if "canonical" in rel and a.get("href"):
                self.info.canonical = self._absolute(a["href"]) or ""
            if "alternate" in rel and ("rss" in a.get("type", "") or "atom" in a.get("type", "")):
                feed = self._absolute(a.get("href"))
                if feed:
                    self.info.feeds.append(feed)
            return
        if tag == "title" and not self.skip_depth:
            # only the first <title> counts (SVG icons carry their own <title>)
            self.in_title = not self.title_parts
            return
        if tag in _SKIP:
            if tag not in _VOID:
                self.skip_depth += 1
            return
        if self.skip_depth or self.in_head:
            return
        if tag in _BOILERPLATE:
            self.boiler_depth += 1
        if tag in _HEADINGS:
            self._emit("\n\n" + "#" * _HEADINGS[tag] + " ")
        elif tag == "li":
            self._emit("\n- ")
        elif tag in ("br",):
            self._emit("\n")
        elif tag == "hr":
            self._emit("\n\n---\n\n")
        elif tag == "tr":
            self._emit("\n| ")
        elif tag in ("td", "th"):
            pass
        elif tag == "pre":
            self.pre_depth += 1
            self._emit("\n\n```\n")
        elif tag == "a":
            self.link_stack.append((self._absolute(a.get("href")), []))
        elif tag == "img":
            alt = a.get("alt", "").strip()
            if alt and len(alt) > 3 and self.link_stack:
                self._emit(alt)
        elif tag in _BLOCK:
            self._emit("\n\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False
            return
        if tag == "title":
            self.in_title = False
            return
        if tag in _SKIP:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth or self.in_head:
            return
        if tag in _HEADINGS:
            self._emit("\n\n")
        elif tag in ("td", "th"):
            self._emit(" | ")
        elif tag == "pre":
            if self.pre_depth:
                self.pre_depth -= 1
            self._emit("\n```\n\n")
        elif tag == "a":
            if not self.link_stack:
                return
            href, parts = self.link_stack.pop()
            text = re.sub(r"\s+", " ", "".join(parts)).strip()
            if href and text:
                self.links.append((href, text[:200]))
                self._emit(f"[{text[:200]}]({href})")
            elif text:
                self._emit(text)
        elif tag in _BLOCK or tag == "li":
            self._emit("\n\n" if tag != "li" else "")
        if tag in _BOILERPLATE and self.boiler_depth:
            self.boiler_depth -= 1

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
            return
        if self.skip_depth or self.in_head:
            return
        if self.pre_depth:
            self._emit(data)
        else:
            self._emit(re.sub(r"\s+", " ", data))

    def _meta(self, a: dict) -> None:
        key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
        content = a.get("content", "").strip()
        if not content:
            return
        if key in ("og:title", "twitter:title") and not self.info.title:
            self.info.title = content
        elif key in ("description", "og:description") and not self.info.description:
            self.info.description = content
        elif key in ("author", "article:author", "parsely-author") and not self.info.author:
            self.info.author = content
        elif key in ("article:published_time", "datepublished", "date", "dc.date",
                     "parsely-pub-date", "pubdate", "publish-date") and not self.info.published:
            self.info.published = content
        elif key == "og:site_name" and not self.info.site_name:
            self.info.site_name = content


def _tidy(text: str) -> str:
    cleaned = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_fence:
                while cleaned and not cleaned[-1].strip():
                    cleaned.pop()  # no blank lines before a closing fence
            in_fence = not in_fence
            cleaned.append(stripped)
            continue
        if in_fence:  # keep code exactly as written (indentation matters)
            cleaned.append(line.rstrip())
            continue
        if stripped in ("-", "|", "| |", "||", "- |"):
            continue
        cleaned.append(stripped)
    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"```\n\n```\n?", "", text)  # empty code blocks
    return text.strip()


def html_to_markdown(html: str, base_url: str = "") -> tuple[str, str, PageInfo, list[tuple[str, str]]]:
    """Convert a whole page. Returns (page_md, full_md, page_info, links):
    page_md drops <nav>/<footer> blocks, full_md keeps absolutely everything."""
    parser = _MarkdownParser(base_url)
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # HTMLParser is lenient, but never let a page crash us
        pass
    while parser.link_stack:  # flush links that were never closed
        _href, parts = parser.link_stack.pop()
        parser._emit("".join(parts))
    info = parser.info
    page_title = html_lib.unescape(re.sub(r"\s+", " ", "".join(parser.title_parts))).strip()
    if page_title:
        info.title = page_title if not info.title or len(page_title) >= 4 else info.title
    return (_tidy("".join(parser.out_page)), _tidy("".join(parser.out_full)), info,
            _dedupe_links(parser.links))


def _dedupe_links(links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen = set()
    out = []
    for href, text in links:
        if href in seen:
            continue
        seen.add(href)
        out.append((href, text))
    return out


def visible_text_length(markdown: str) -> int:
    """Length of the text a human would read (links collapsed to their text)."""
    plain = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", markdown)
    plain = re.sub(r"[#>*`|\-]+", " ", plain)
    return len(re.sub(r"\s+", " ", plain).strip())


# ---------------------------------------------------------------------------
# trafilatura (optional) for article-style pages
# ---------------------------------------------------------------------------

def trafilatura_available() -> bool:
    try:
        import trafilatura  # noqa: F401

        return True
    except ImportError:
        return False


def extract_main_content(html: str, url: str = "") -> tuple[str | None, dict]:
    try:
        import trafilatura
    except ImportError:
        return None, {}
    meta: dict = {}
    try:
        text = trafilatura.extract(
            html,
            url=url or None,
            output_format="markdown",
            include_links=True,
            include_tables=True,
            include_formatting=True,
            include_comments=False,
            favor_recall=True,
        )
    except Exception:
        text = None
    try:
        doc = trafilatura.extract_metadata(html, default_url=url or None)
        if doc is not None:
            for key in ("title", "author", "date", "sitename", "description"):
                value = getattr(doc, key, None)
                if value:
                    meta[key] = str(value)
    except Exception:
        pass
    return (text.strip() if text else None), meta


def _code_blocks(md: str) -> int:
    return md.count("```") // 2


def _table_rows(md: str) -> int:
    return sum(1 for line in md.splitlines() if line.lstrip().startswith("|"))


def _fix_fragment_links(md: str, url: str) -> str:
    """trafilatura turns '#section' links into 'https://host#section'; point them at the page."""
    if not url:
        return md
    page = url.split("#")[0]
    host = re.match(r"^(https?://[^/?#]+)", page)
    if not host:
        return md
    return re.sub(r"\]\(" + re.escape(host.group(1)) + r"/?#([^)\s]*)\)", lambda m: f"]({page}#{m.group(1)})", md)


@dataclass
class Extracted:
    title: str
    content: str
    extractor: str
    info: PageInfo
    links: list
    full_text_chars: int


def extract_html(html: str, url: str = "", mode: str = "auto") -> Extracted:
    """mode:
    full  - every piece of text on the page (menus and footers included)
    main  - only the article body (trafilatura), when it can find one
    auto  - the article body for real articles; otherwise the page without
            menus/footers, so data in sidebars, tables and grids is kept.
            Losing a price or a download count is worse than a few extra lines.
    """
    page_md, full_md, info, links = html_to_markdown(html, url)
    full_len = visible_text_length(full_md)
    page_len = visible_text_length(page_md)
    if mode == "full" or page_len < 0.3 * full_len or page_len < 200 <= full_len:
        # nothing but menus left (or the user asked for everything): keep it all
        base_md, base_len, base_name = full_md, full_len, "builtin-full"
    else:
        base_md, base_len, base_name = page_md, page_len, "builtin-page"
    main_md, meta = (None, {})
    if mode in ("auto", "main"):
        main_md, meta = extract_main_content(html, url)
    if meta:
        info.title = info.title or meta.get("title", "")
        info.author = info.author or meta.get("author", "")
        info.published = info.published or meta.get("date", "")
        info.site_name = info.site_name or meta.get("sitename", "")
        info.description = info.description or meta.get("description", "")
    chosen, extractor = base_md, base_name
    if main_md and mode != "full":
        main_md = _fix_fragment_links(main_md, url)
        main_len = visible_text_length(main_md)
        # Code samples and tables are often the very thing the user needs
        # (docs, specs, prices); article extractors tend to drop them.
        lost_code = _code_blocks(base_md) > _code_blocks(main_md)
        lost_tables = _table_rows(base_md) > max(2, 2 * _table_rows(main_md))
        if mode == "main":
            chosen, extractor = main_md, "trafilatura-main"
        elif lost_code or lost_tables:
            pass
        elif main_len >= 0.7 * base_len or (main_len >= 4000 and main_len >= 0.5 * base_len):
            # trafilatura kept nearly everything that matters: use its cleaner text
            chosen, extractor = main_md, "trafilatura-main"
    return Extracted(title=info.title, content=chosen, extractor=extractor, info=info,
                     links=links, full_text_chars=full_len)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def looks_like_pdf(body: bytes) -> bool:
    # Trust the bytes, not the Content-Type: servers mislabel PDFs both ways.
    return b"%PDF-" in body[:1024]


def pdf_to_text(data: bytes, max_pages: int | None = None) -> tuple[str, str, dict]:
    """Return (title, text_with_page_markers, metadata). Raises RuntimeError on failure."""
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return _pdf_with_pdftotext(data)
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise RuntimeError("pdf_encrypted: the PDF is password-protected") from exc
        meta = {}
        title = ""
        try:
            md = reader.metadata
            if md:
                title = (md.title or "").strip()
                if md.author:
                    meta["author"] = str(md.author)
                if getattr(md, "creation_date", None):
                    meta["date"] = str(md.creation_date)
        except Exception:
            pass
        total = len(reader.pages)
        meta["pages"] = total
        parts = []
        for index, page in enumerate(reader.pages, start=1):
            if max_pages and index > max_pages:
                parts.append(f"\n\n[... {total - max_pages} more pages not extracted ...]")
                break
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            parts.append(f"\n\n--- Page {index}/{total} ---\n\n{text.strip()}")
        body = "".join(parts).strip()
        if not re.sub(r"--- Page \d+/\d+ ---|\s", "", body):
            meta["warning"] = ("No text layer found: this PDF is probably scanned images. "
                               "Take a screenshot/OCR or look for a text version.")
        return title, body, meta
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"pdf_error: could not read the PDF ({type(exc).__name__}: {exc})") from exc


def _pdf_with_pdftotext(data: bytes) -> tuple[str, str, dict]:
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("pdf_support_missing: install pypdf (run doctor.py --setup) to read PDFs")
    proc = subprocess.run([exe, "-layout", "-", "-"], input=data, capture_output=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError("pdf_error: pdftotext failed")
    pages = proc.stdout.decode("utf-8", "replace").split("\f")
    text = "".join(f"\n\n--- Page {i}/{len(pages)} ---\n\n{p.strip()}" for i, p in enumerate(pages, 1) if p.strip())
    return "", text.strip(), {"pages": len(pages)}


# ---------------------------------------------------------------------------
# RSS / Atom feeds
# ---------------------------------------------------------------------------

def _strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_feed(body: bytes) -> tuple[str, list[dict]] | None:
    """Parse RSS 2.0, RSS 1.0 (RDF) or Atom. Returns None if it is not a feed."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    root_name = _local(root.tag)
    if root_name not in ("rss", "feed", "rdf"):
        return None
    title = ""
    items: list[dict] = []
    if root_name == "feed":  # Atom
        for child in root:
            if _local(child.tag) == "title":
                title = (child.text or "").strip()
        entries = [e for e in root if _local(e.tag) == "entry"]
        for entry in entries:
            item = {"title": "", "link": "", "date": "", "summary": ""}
            for child in entry:
                name = _local(child.tag)
                if name == "title":
                    item["title"] = _strip_tags(child.text or "")
                elif name == "link":
                    rel = child.get("rel", "alternate")
                    if rel == "alternate" or not item["link"]:
                        item["link"] = child.get("href", "")
                elif name in ("updated", "published") and not item["date"]:
                    item["date"] = (child.text or "").strip()
                elif name in ("summary", "content") and not item["summary"]:
                    item["summary"] = _strip_tags("".join(child.itertext()))
            items.append(item)
    else:  # RSS 2.0 / RDF
        channel = None
        for child in root.iter():
            if _local(child.tag) == "channel":
                channel = child
                break
        if channel is not None:
            for child in channel:
                if _local(child.tag) == "title":
                    title = (child.text or "").strip()
        for node in root.iter():
            if _local(node.tag) != "item":
                continue
            item = {"title": "", "link": "", "date": "", "summary": ""}
            for child in node:
                name = _local(child.tag)
                if name == "title":
                    item["title"] = _strip_tags(child.text or "")
                elif name == "link":
                    item["link"] = (child.text or child.get("href") or "").strip()
                elif name in ("pubdate", "date", "updated") and not item["date"]:
                    item["date"] = (child.text or "").strip()
                elif name in ("description", "encoded", "summary") and not item["summary"]:
                    item["summary"] = _strip_tags(child.text or "")
            items.append(item)
    return title, items


def feed_to_markdown(title: str, items: list[dict], summary_chars: int = 300) -> str:
    lines = [f"Feed: {title or '(untitled)'} — {len(items)} items", ""]
    for i, item in enumerate(items, 1):
        head = f"{i}. [{item['title'] or item['link']}]({item['link']})" if item["link"] else f"{i}. {item['title']}"
        if item["date"]:
            head += f" — {item['date']}"
        lines.append(head)
        if item["summary"]:
            summary = item["summary"]
            if len(summary) > summary_chars:
                summary = summary[:summary_chars].rstrip() + "…"
            lines.append(f"   {summary}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON / plain text
# ---------------------------------------------------------------------------

def json_to_text(body: bytes, charset: str | None = None) -> str | None:
    try:
        data = json.loads(body.decode(charset or "utf-8", errors="replace"))
    except ValueError:
        return None
    return json.dumps(data, indent=2, ensure_ascii=False)


TEXT_TYPES = ("text/plain", "text/markdown", "text/csv", "text/x-markdown", "text/tab-separated-values")


def is_feed_type(content_type: str) -> bool:
    return any(k in content_type for k in ("rss", "atom", "rdf")) or content_type in ("application/xml", "text/xml")
