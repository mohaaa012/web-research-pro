"""The scripts as Claude actually runs them: separate processes, real arguments."""

import json
import os
import subprocess
import sys

from conftest import SCRIPTS


def run(script, *args, env=None):
    # The scripts always write UTF-8; read it as UTF-8 (Windows would default to cp1252).
    full_env = dict(os.environ, PYTHONIOENCODING="utf-8", **(env or {}))
    proc = subprocess.run([sys.executable, str(SCRIPTS / script), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=180, env=full_env)
    return proc.returncode, proc.stdout, proc.stderr


def test_fetch_markdown_header(site):
    code, out, _ = run("fetch.py", site + "/article", "--method", "http")
    assert code == 0
    assert out.startswith("=== web-research-pro fetch ===")
    assert "ok: yes" in out and "method: http" in out and "author: Ana García" in out


def test_fetch_json_and_pagination(site):
    code, out, _ = run("fetch.py", site + "/article", "--method", "http", "--json", "--max-chars", "100")
    data = json.loads(out)
    assert code == 0 and data["ok"] and len(data["content"]) == 100 and data["next_offset"] == 100
    code, out, _ = run("fetch.py", site + "/article", "--method", "http", "--offset", "100", "--max-chars", "50")
    assert "showing 100-150" in out


def test_fetch_out_dir_with_many_urls(site, tmp_path):
    code, out, _ = run("fetch.py", site + "/article", site + "/doc.pdf", site + "/missing",
                       "--method", "http", "--out-dir", str(tmp_path))
    assert code == 1  # one URL failed
    files = sorted(p.name for p in tmp_path.iterdir())
    assert len(files) == 3 and files[1].endswith(".md")
    assert "[FAIL]" in out and "not_found" in out


def test_fetch_failure_shows_reason_and_suggestions(site):
    code, out, _ = run("fetch.py", site + "/private", "--method", "http")
    assert code == 1 and "ok: NO" in out and "login_required" in out and "suggestion:" in out


def test_fetch_unknown_session_is_a_clean_error(site):
    code, _, err = run("fetch.py", site + "/article", "--session", "nope")
    assert code == 2 and "no saved session called 'nope'" in err


def test_login_import_list_and_delete(tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("example.com\tFALSE\t/\tTRUE\t1999999999\tsid\tTOPSECRET\n")
    code, out, _ = run("login.py", "import", "ex", str(cookies))
    assert code == 0 and "imported session 'ex'" in out
    code, out, _ = run("login.py", "list")
    assert "ex: 1 cookies" in out and "TOPSECRET" not in out
    code, out, _ = run("login.py", "delete", "ex")
    assert code == 0


def test_login_save_without_display_explains_alternative():
    if sys.platform != "linux":
        return
    env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
    proc = subprocess.run([sys.executable, str(SCRIPTS / "login.py"), "save", "x", "--url", "https://example.com"],
                          capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
    assert proc.returncode == 2 and "login.py import" in proc.stderr


def test_search_rejects_unknown_engine():
    code, _, err = run("search.py", "hello", "--engine", "altavista")
    assert code == 2 and "unknown engine" in err


def test_doctor_runs_offline():
    code, out, _ = run("doctor.py", "--offline", "--json")
    names = {c["check"] for c in json.loads(out)}
    assert {"python", "playwright", "chromium", "sessions"} <= names


def test_help_texts():
    for script in ("fetch.py", "search.py", "login.py", "crawl.py", "monitor.py", "doctor.py"):
        code, out, _ = run(script, "--help")
        assert code == 0 and "usage:" in out
