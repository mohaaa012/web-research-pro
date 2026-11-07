"""Paths, identity strings and environment handling shared by every script."""

from __future__ import annotations

import locale
import os
import platform
import re
import sys
from pathlib import Path

VERSION = "1.0.0"
PROJECT_URL = "https://github.com/mohaaa012/web-research-pro"

# Honest identification for public APIs (Wikipedia, arXiv, Hacker News...).
# Wikimedia in particular asks every client to identify itself this way.
TOOL_USER_AGENT = f"web-research-pro/{VERSION} (+{PROJECT_URL})"

# A normal desktop browser User-Agent for ordinary web pages. Many sites
# answer 403 to the default "Python-urllib/3.x" string even for a single,
# human-initiated page view; this mirrors what the user's own browser sends.
_CHROME_MAJOR = "148"


def _platform_token() -> str:
    system = platform.system()
    if system == "Darwin":
        return "Macintosh; Intel Mac OS X 10_15_7"
    if system == "Windows":
        return "Windows NT 10.0; Win64; x64"
    return "X11; Linux x86_64"


def browser_user_agent(chrome_major: str | None = None) -> str:
    override = os.environ.get("WRP_USER_AGENT")
    if override:
        return override
    major = chrome_major or _CHROME_MAJOR
    return (
        f"Mozilla/5.0 ({_platform_token()}) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
    )


_LANG_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z]{2,4})?$")


def accept_language() -> str:
    """Accept-Language built from WRP_ACCEPT_LANGUAGE or the system locale."""
    explicit = os.environ.get("WRP_ACCEPT_LANGUAGE")
    if explicit:
        return explicit
    candidates = [os.environ.get("LC_ALL"), os.environ.get("LANG")]
    try:
        candidates.append(locale.getlocale()[0])
    except (ValueError, TypeError):  # pragma: no cover - odd locales
        pass
    for raw in candidates:
        if not raw:
            continue
        code = raw.split(".")[0].replace("_", "-")
        if code.upper() in ("C", "POSIX") or not _LANG_RE.match(code):
            continue
        primary = code.split("-")[0].lower()
        if primary == "en":
            return f"{code},en;q=0.9"
        return f"{code},{primary};q=0.9,en;q=0.8"
    return "en-US,en;q=0.9"


def browser_headers(extra: dict | None = None) -> dict:
    headers = {
        "User-Agent": browser_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "application/pdf;q=0.9,*/*;q=0.8",
        "Accept-Language": accept_language(),
        "Upgrade-Insecure-Requests": "1",
    }
    if extra:
        headers.update(extra)
    return headers


def api_headers(extra: dict | None = None) -> dict:
    headers = {
        "User-Agent": TOOL_USER_AGENT,
        "Accept": "application/json",
        "Accept-Language": accept_language(),
    }
    if extra:
        headers.update(extra)
    return headers


# ---------------------------------------------------------------------------
# Local data folder (~/.web-research-pro). Nothing here is ever uploaded.
# ---------------------------------------------------------------------------

def app_home() -> Path:
    custom = os.environ.get("WRP_HOME")
    return Path(custom).expanduser() if custom else Path.home() / ".web-research-pro"


def venv_dir() -> Path:
    return app_home() / "venv"


def venv_python() -> Path:
    if os.name == "nt":
        return venv_dir() / "Scripts" / "python.exe"
    return venv_dir() / "bin" / "python"


def sessions_dir() -> Path:
    return app_home() / "sessions"


def monitor_dir() -> Path:
    return app_home() / "monitor"


def ensure_private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
    return path


def ensure_venv() -> None:
    """Re-run the current script inside the private virtualenv when it exists.

    The installer puts Playwright, trafilatura and pypdf in
    ~/.web-research-pro/venv so they never clash with the system Python.
    Claude (and the user) can then always run plain `python3 script.py`:
    if the venv is there, the script transparently switches to it.
    """
    if os.environ.get("WRP_NO_REEXEC") == "1":
        return
    py = venv_python()
    if not py.exists():
        return
    try:
        if Path(sys.prefix).resolve() == venv_dir().resolve():
            return
    except OSError:
        return
    env = dict(os.environ, WRP_NO_REEXEC="1")
    args = [str(py), *sys.argv]
    if os.name == "nt":
        import subprocess

        sys.exit(subprocess.call(args, env=env))
    os.execve(str(py), args, env)


def reconfigure_stdout() -> None:
    """Make sure UTF-8 text never crashes on Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
