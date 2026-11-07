"""The user's own logged-in sessions, stored only on their machine.

A session is a Playwright "storage state" JSON file (cookies + localStorage)
in ~/.web-research-pro/sessions/<name>.json, readable only by the user
(chmod 600). It is created either by logging in by hand in a visible browser
window (login.py save) or by importing cookies exported from the user's own
browser (login.py import). Cookie values are never printed.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import re
import time
from pathlib import Path

from .config import ensure_private_dir, sessions_dir

_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class SessionError(Exception):
    pass


def session_path(name: str) -> Path:
    if not _NAME_RE.match(name or ""):
        raise SessionError("session names may only use letters, digits, '.', '_' and '-' (max 64)")
    return sessions_dir() / f"{name}.json"


def write_private_json(path: Path, data: dict) -> None:
    ensure_private_dir(path.parent)
    tmp = path.with_suffix(".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1)
    os.replace(tmp, path)
    if os.name != "nt":
        os.chmod(path, 0o600)


def save_state(name: str, state: dict) -> Path:
    path = session_path(name)
    write_private_json(path, state)
    return path


def load_state(name: str) -> dict:
    path = session_path(name)
    if not path.exists():
        raise SessionError(
            f"no saved session called '{name}'. Create it with: login.py save {name} --url <login page>"
        )
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def delete_state(name: str) -> bool:
    path = session_path(name)
    if path.exists():
        path.unlink()
        return True
    return False


def summarize_state(name: str, state: dict) -> dict:
    cookies = state.get("cookies", [])
    domains = sorted({c.get("domain", "").lstrip(".") for c in cookies if c.get("domain")})
    now = time.time()
    expiries = [c.get("expires", -1) for c in cookies if c.get("expires", -1) and c.get("expires", -1) > 0]
    expired = sum(1 for e in expiries if e < now)
    soonest = min((e for e in expiries if e >= now), default=None)
    path = session_path(name)
    return {
        "name": name,
        "cookies": len(cookies),
        "domains": domains,
        "expired_cookies": expired,
        "next_expiry": time.strftime("%Y-%m-%d", time.localtime(soonest)) if soonest else None,
        "saved": time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime)) if path.exists() else None,
        "origins_with_storage": len(state.get("origins", [])),
    }


def list_states() -> list[dict]:
    folder = sessions_dir()
    if not folder.exists():
        return []
    out = []
    for path in sorted(folder.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as handle:
                out.append(summarize_state(path.stem, json.load(handle)))
        except (OSError, ValueError, SessionError):
            out.append({"name": path.stem, "error": "unreadable"})
    return out


# ---------------------------------------------------------------------------
# Importing cookies exported from the user's own browser
# ---------------------------------------------------------------------------

_SAMESITE = {"strict": "Strict", "lax": "Lax", "none": "None", "no_restriction": "None",
             "unspecified": "Lax", "": "Lax"}


def _norm_cookie(c: dict) -> dict | None:
    name = c.get("name")
    domain = c.get("domain") or c.get("host")
    if not name or not domain:
        return None
    expires = c.get("expires", c.get("expirationDate", c.get("expiry", -1)))
    try:
        expires = float(expires) if expires not in (None, "", "Session") else -1
    except (TypeError, ValueError):
        expires = -1
    if c.get("session") is True:
        expires = -1
    secure = bool(c.get("secure", False))
    same = _SAMESITE.get(str(c.get("sameSite", "")).lower(), "Lax")
    if same == "None" and not secure:
        same = "Lax"  # Chromium rejects SameSite=None cookies that are not Secure
    host_only = c.get("hostOnly")
    if host_only is False and not domain.startswith("."):
        domain = "." + domain
    return {
        "name": str(name),
        "value": str(c.get("value", "")),
        "domain": domain,
        "path": c.get("path") or "/",
        "expires": expires,
        "httpOnly": bool(c.get("httpOnly", False)),
        "secure": secure,
        "sameSite": same,
    }


def parse_netscape(text: str) -> list[dict]:
    cookies = []
    for raw in text.splitlines():
        line = raw.strip()
        http_only = False
        if line.startswith("#HttpOnly_"):
            http_only = True
            line = line[len("#HttpOnly_"):]
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            parts = re.split(r"\s+", line, maxsplit=6)
        if len(parts) < 7:
            continue
        domain, include_sub, path, secure, expiry, name, value = parts[:7]
        if include_sub.upper() == "TRUE" and not domain.startswith("."):
            domain = "." + domain
        try:
            exp = float(expiry)
        except ValueError:
            exp = -1
        cookies.append({
            "name": name, "value": value, "domain": domain, "path": path or "/",
            "expires": exp if exp > 0 else -1, "httpOnly": http_only,
            "secure": secure.upper() == "TRUE", "sameSite": "Lax",
        })
    return cookies


def import_cookie_file(path: str | Path) -> dict:
    """Accept Netscape cookies.txt, a JSON cookie array (Cookie-Editor style)
    or a Playwright storage-state file. Returns a storage state dict."""
    raw = Path(path).expanduser().read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        raise SessionError("the cookie file is empty")
    if raw[0] in "[{":
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise SessionError(f"the file looks like JSON but could not be parsed: {exc}") from exc
        if isinstance(data, dict) and "cookies" in data:
            cookies = [x for x in (_norm_cookie(c) for c in data.get("cookies", [])) if x]
            return {"cookies": cookies, "origins": data.get("origins", [])}
        if isinstance(data, list):
            cookies = [x for x in (_norm_cookie(c) for c in data if isinstance(c, dict)) if x]
            return {"cookies": cookies, "origins": []}
        raise SessionError("unrecognised JSON cookie format")
    cookies = parse_netscape(raw)
    if not cookies:
        raise SessionError("no cookies found. Export them in 'Netscape cookies.txt' or JSON format.")
    return {"cookies": cookies, "origins": []}


# ---------------------------------------------------------------------------
# Using a session with the plain HTTP client
# ---------------------------------------------------------------------------

def to_cookiejar(state: dict) -> http.cookiejar.CookieJar:
    jar = http.cookiejar.CookieJar()
    now = time.time()
    for c in state.get("cookies", []):
        expires = c.get("expires", -1)
        if expires and 0 < expires < now:
            continue
        domain = c.get("domain", "")
        cookie = http.cookiejar.Cookie(
            version=0,
            name=c.get("name", ""),
            value=c.get("value", ""),
            port=None,
            port_specified=False,
            domain=domain,
            domain_specified=domain.startswith("."),
            domain_initial_dot=domain.startswith("."),
            path=c.get("path", "/"),
            path_specified=True,
            secure=bool(c.get("secure")),
            expires=int(expires) if expires and expires > 0 else None,
            discard=not (expires and expires > 0),
            comment=None,
            comment_url=None,
            rest={"HttpOnly": ""} if c.get("httpOnly") else {},
            rfc2109=False,
        )
        jar.set_cookie(cookie)
    return jar
