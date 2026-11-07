"""crawl.py and monitor.py end to end, through their command-line entry points."""

import json

import crawl
import monitor
import server


def test_crawl_respects_scope_robots_and_depth(site, tmp_path, capsys):
    out = tmp_path / "crawl"
    code = crawl.main([site + "/site/", "--out-dir", str(out), "--delay", "0", "--depth", "2", "--max-pages", "20"])
    assert code == 0
    pages = [json.loads(line) for line in (out / "pages.jsonl").read_text().splitlines()]
    urls = {p["url"].replace(site, "") for p in pages}
    assert urls == {"/site/", "/site/a", "/site/b", "/site/c"}  # utm stripped, png skipped, other dir skipped
    index = (out / "INDEX.md").read_text()
    assert "Disallowed by robots.txt" in index and "/site/secret/x" in index
    assert all((out / p["file"]).exists() for p in pages)
    assert "Gamma content" in (out / [p for p in pages if p["url"].endswith("/site/c")][0]["file"]).read_text()


def test_crawl_depth_zero_and_page_limit(site, tmp_path):
    out = tmp_path / "c2"
    crawl.main([site + "/site/", "--out-dir", str(out), "--delay", "0", "--depth", "0"])
    assert len((out / "pages.jsonl").read_text().splitlines()) == 1
    out = tmp_path / "c3"
    crawl.main([site + "/site/", "--out-dir", str(out), "--delay", "0", "--max-pages", "2"])
    assert len((out / "pages.jsonl").read_text().splitlines()) == 2


def test_crawl_from_sitemap(site, tmp_path):
    out = tmp_path / "c4"
    crawl.main([site + "/site/", "--sitemap", "--out-dir", str(out), "--delay", "0"])
    urls = {json.loads(l)["url"].replace(site, "") for l in (out / "pages.jsonl").read_text().splitlines()}
    assert urls == {"/site/a", "/site/b"}  # the sitemap's /site/secret/x is disallowed


def test_registrable_domain():
    assert crawl.registrable_domain("docs.example.com") == "example.com"
    assert crawl.registrable_domain("shop.example.co.uk") == "example.co.uk"
    assert crawl.registrable_domain("example.com") == "example.com"


def test_monitor_new_unchanged_changed(site, capsys):
    url = site + "/price"
    assert monitor.main(["check", url, "--name", "chair", "--method", "http"]) == 0
    assert "STATUS: NEW" in capsys.readouterr().out
    assert monitor.main(["check", url, "--name", "chair", "--method", "http"]) == 0
    assert "STATUS: UNCHANGED" in capsys.readouterr().out
    server.STATE["price"] = "14,99 €"
    monitor.main(["check", url, "--name", "chair", "--method", "http"])
    out = capsys.readouterr().out
    assert "STATUS: CHANGED" in out and "-Precio: 19,99 €" in out and "+Precio: 14,99 €" in out
    monitor.main(["list"])
    assert "chair" in capsys.readouterr().out
    assert monitor.main(["forget", "chair"]) == 0


def test_monitor_regex_only_watches_the_value(site, capsys):
    url = site + "/price"
    monitor.main(["check", url, "--name", "p", "--method", "http", "--regex", r"Precio: ([0-9,]+ €)"])
    assert "19,99 €" in capsys.readouterr().out
    server.STATE["price"] = "9,99 €"
    monitor.main(["check", url, "--name", "p", "--method", "http", "--regex", r"Precio: ([0-9,]+ €)"])
    out = capsys.readouterr().out
    assert "STATUS: CHANGED" in out and "+9,99 €" in out


def test_monitor_reports_errors(site, capsys):
    assert monitor.main(["check", site + "/missing", "--name", "gone", "--method", "http"]) == 2
    assert "STATUS: ERROR" in capsys.readouterr().out
