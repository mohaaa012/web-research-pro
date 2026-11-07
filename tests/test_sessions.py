import json
import os
import stat
import time

import pytest

from wrp import sessions


def test_netscape_import_with_httponly_and_subdomains(tmp_path):
    f = tmp_path / "cookies.txt"
    f.write_text("# Netscape HTTP Cookie File\n"
                 "#HttpOnly_.example.com\tTRUE\t/\tTRUE\t1999999999\tsession\tabc\n"
                 "shop.example.com\tFALSE\t/cart\tFALSE\t0\tcart\t3\n")
    state = sessions.import_cookie_file(f)
    a, b = state["cookies"]
    assert a == {"name": "session", "value": "abc", "domain": ".example.com", "path": "/", "expires": 1999999999.0,
                 "httpOnly": True, "secure": True, "sameSite": "Lax"}
    assert b["domain"] == "shop.example.com" and b["expires"] == -1 and b["path"] == "/cart"


def test_cookie_editor_json_import(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps([
        {"domain": "example.com", "hostOnly": False, "name": "a", "value": "1", "path": "/",
         "expirationDate": 1999999999.5, "secure": False, "httpOnly": True, "sameSite": "no_restriction"},
        {"domain": ".example.com", "name": "b", "value": "2", "session": True, "sameSite": "strict", "secure": True},
    ]))
    c1, c2 = sessions.import_cookie_file(f)["cookies"]
    assert c1["domain"] == ".example.com" and c1["sameSite"] == "Lax"  # None requires Secure
    assert c2["expires"] == -1 and c2["sameSite"] == "Strict"


def test_playwright_state_import(tmp_path):
    state = {"cookies": [{"name": "x", "value": "y", "domain": "a.com", "path": "/", "expires": -1,
                          "httpOnly": False, "secure": True, "sameSite": "None"}], "origins": [{"origin": "https://a.com"}]}
    f = tmp_path / "s.json"
    f.write_text(json.dumps(state))
    imported = sessions.import_cookie_file(f)
    assert imported["cookies"][0]["sameSite"] == "None" and imported["origins"] == state["origins"]


def test_bad_files(tmp_path):
    empty = tmp_path / "e.txt"
    empty.write_text("")
    with pytest.raises(sessions.SessionError):
        sessions.import_cookie_file(empty)
    junk = tmp_path / "j.txt"
    junk.write_text("hello world")
    with pytest.raises(sessions.SessionError):
        sessions.import_cookie_file(junk)


def test_saved_file_is_private_and_listed():
    sessions.save_state("mysite", {"cookies": [{"name": "a", "value": "SECRET", "domain": ".site.com", "path": "/",
                                                "expires": time.time() + 3600}], "origins": []})
    path = sessions.session_path("mysite")
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    listing = sessions.list_states()
    assert listing[0]["name"] == "mysite" and listing[0]["domains"] == ["site.com"]
    assert "SECRET" not in json.dumps(listing)
    assert sessions.delete_state("mysite") and not path.exists()


def test_invalid_names_rejected():
    for bad in ("../evil", "a b", "", "x" * 65):
        with pytest.raises(sessions.SessionError):
            sessions.session_path(bad)


def test_cookiejar_skips_expired():
    jar = sessions.to_cookiejar({"cookies": [
        {"name": "old", "value": "1", "domain": "a.com", "path": "/", "expires": 1000},
        {"name": "new", "value": "2", "domain": ".a.com", "path": "/", "expires": time.time() + 999},
    ]})
    assert [c.name for c in jar] == ["new"]
