from server import ARTICLE, ATOM, LISTING, RSS, make_pdf
from wrp import extract


def test_markdown_structure_and_absolute_links():
    page, full, info, links = extract.html_to_markdown(ARTICLE, "https://example.com/blog/post")
    assert "# How progression systems keep players" in page
    assert "## Key numbers" in page
    assert "| D1 retention | 42% |" in page
    assert "- Pets" in page and "- Trading" in page
    assert "[full guide](https://example.com/guide?utm_source=x)" in page
    assert "var tracking" not in full and "color:red" not in full
    assert info.title == "How progression systems keep players"
    assert info.author == "Ana García"
    assert info.published == "2026-03-14"
    assert info.feeds == ["https://example.com/feed.xml"]
    assert ("https://example.com/about", "About") in links


def test_nav_and_footer_only_dropped_from_page_version():
    page, full, *_ = extract.html_to_markdown(ARTICLE, "https://example.com/")
    assert "Privacy" not in page and "Contact" not in page
    assert "Privacy" in full and "Contact" in full


def test_code_blocks_keep_indentation():
    page, *_ = extract.html_to_markdown(ARTICLE, "https://example.com/")
    assert "```\ndef reward(player):\n    player.coins += 10\n```" in page


def test_missing_head_end_tag_does_not_hide_body():
    html = "<html><head><title>T</title><meta charset=utf-8><p>Body text that matters</p></html>"
    page, *_ = extract.html_to_markdown(html, "")
    assert "Body text that matters" in page


def test_svg_title_does_not_replace_page_title():
    html = "<html><head><title>Real title</title></head><body><svg><title>icon</title></svg><p>x</p></body></html>"
    _, _, info, _ = extract.html_to_markdown(html, "")
    assert info.title == "Real title"


def test_listing_page_keeps_every_item_in_auto_mode():
    ex = extract.extract_html(LISTING, "https://shop.example.com/", "auto")
    for i in (1, 10, 20):
        assert f"Book number {i}" in ex.content
        assert f"£{10 + i}.99" in ex.content


def test_full_mode_keeps_menus():
    ex = extract.extract_html(ARTICLE, "https://example.com/", "full")
    assert ex.extractor == "builtin-full"
    assert "Contact" in ex.content


def test_decode_uses_meta_charset():
    body = "<meta charset='iso-8859-1'><p>Año piña</p>".encode("iso-8859-1")
    assert "Año piña" in extract.decode_html(body)


def test_decode_prefers_header_charset_and_survives_garbage():
    assert extract.decode_html("héllo".encode("utf-8"), "utf-8") == "héllo"
    assert extract.decode_html(b"\xff\xfe\xfa", None)  # never raises


def test_rss_and_atom_feeds():
    title, items = extract.parse_feed(RSS.encode())
    assert title == "Dev blog" and len(items) == 2
    assert items[0]["title"] == "Update 1.2 released"
    assert items[0]["summary"] == "New pets and a trading plaza."
    md = extract.feed_to_markdown(title, items)
    assert "1. [Update 1.2 released](https://example.com/u12)" in md
    title, items = extract.parse_feed(ATOM.encode())
    assert title == "Atom news" and items[0]["link"] == "https://example.com/first"
    assert extract.parse_feed(b"<html><body>no</body></html>") is None


def test_pdf_text_and_metadata():
    title, text, meta = extract.pdf_to_text(make_pdf("Quarterly revenue grew 12 percent"))
    assert "Quarterly revenue grew 12 percent" in text
    assert "--- Page 1/1 ---" in text
    assert title == "Test Document"
    assert meta["pages"] == 1
    assert extract.looks_like_pdf(make_pdf())
    assert not extract.looks_like_pdf(b"<html>")


def test_json_pretty_print():
    assert '"a": 1' in extract.json_to_text(b'{"a":1}')
    assert extract.json_to_text(b"not json") is None


def test_visible_text_length_ignores_markup():
    assert extract.visible_text_length("[hello](https://x.y/very/long/url) ## **") == 5


DOCS_PAGE = ("<html><head><title>Docs</title></head><body><nav>Menu</nav><main><article><h1>Install</h1>"
             + "<p>Long explanation about installing the tool and why each step matters. </p>" * 30
             + '<pre class="shiki"><code><span class="line"><span>claude</span><span> plugin install</span>'
             '<span> demo@market</span></span>\n</code></pre>'
             + "<p>More prose after the command so it looks like an article. </p>" * 30
             + "</article></main><footer>Foot</footer></body></html>")


def test_auto_mode_never_drops_code_blocks():
    ex = extract.extract_html(DOCS_PAGE, "https://docs.example.com/install", "auto")
    assert "claude plugin install demo@market" in ex.content
    assert "```\nclaude plugin install demo@market\n```" in ex.content


def test_fragment_links_point_at_the_page():
    md = "see [the walkthrough](https://docs.example.com#create) and [x](https://docs.example.com/#y)"
    fixed = extract._fix_fragment_links(md, "https://docs.example.com/guide/page")
    assert "(https://docs.example.com/guide/page#create)" in fixed
    assert "(https://docs.example.com/guide/page#y)" in fixed
