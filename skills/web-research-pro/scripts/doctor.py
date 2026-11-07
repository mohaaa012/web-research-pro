#!/usr/bin/env python3
"""Check (and optionally set up) everything web-research-pro needs.

  python3 doctor.py            report what works and how to fix what does not
  python3 doctor.py --setup    create ~/.web-research-pro/venv, install the Python
                               packages and download Chromium (one time, ~200 MB)
  python3 doctor.py --setup --no-browser   same, without Chromium
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from wrp.config import (VERSION, app_home, ensure_private_dir, reconfigure_stdout,  # noqa: E402
                        sessions_dir, venv_dir, venv_python)

REQUIREMENTS = HERE.parent / "requirements.txt"
OK, WARN, FAIL = "✅", "⚠️ ", "❌"


def run(cmd: list[str], timeout: int = 1800) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout + proc.stderr)[-4000:]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def setup(no_browser: bool) -> int:
    if sys.version_info < (3, 9):
        print(f"{FAIL} Python {platform.python_version()} is too old; install Python 3.9 or newer first.")
        return 1
    ensure_private_dir(app_home())
    py = venv_python()
    if not py.exists():
        print(f"• creating private virtualenv in {venv_dir()} ...", flush=True)
        code, out = run([sys.executable, "-m", "venv", str(venv_dir())], timeout=600)
        if code != 0:
            print(f"{FAIL} could not create the virtualenv:\n{out}")
            if platform.system() == "Linux":
                print("   On Debian/Ubuntu install it first:  sudo apt install python3-venv")
            return 1
    print("• installing Python packages (playwright, trafilatura, pypdf, certifi) ...", flush=True)
    code, out = run([str(py), "-m", "pip", "install", "--upgrade", "pip"], timeout=900)
    code, out = run([str(py), "-m", "pip", "install", "-r", str(REQUIREMENTS)], timeout=1800)
    if code != 0:
        print(f"{FAIL} pip install failed:\n{out}")
        return 1
    print(f"{OK} packages installed")
    if not no_browser:
        print("• downloading Chromium for Playwright (one time, about 150-200 MB) ...", flush=True)
        code, out = run([str(py), "-m", "playwright", "install", "chromium"], timeout=1800)
        if code != 0:
            errors = [line.strip() for line in out.splitlines() if "error" in line.lower() and " at " not in line]
            print(f"{WARN} Chromium download failed: {(errors or [out.strip()[-300:]])[0][:300]}\n"
                  f"   If Google Chrome or Edge is installed, the skill uses it instead (doctor checks this below).\n"
                  f"   Otherwise retry later with: python3 {HERE / 'doctor.py'} --setup")
        else:
            print(f"{OK} Chromium installed")
    print("\nchecking the result:\n")
    env = dict(os.environ, WRP_NO_REEXEC="1")
    return subprocess.call([str(py), str(HERE / "doctor.py")], env=env)


def check_browser() -> tuple[str, str]:
    try:
        from wrp.browser import Browser, BrowserUnavailable, playwright_installed
    except Exception as exc:  # pragma: no cover
        return FAIL, f"import error: {exc}"
    if not playwright_installed():
        return FAIL, "Playwright not installed -> run: python3 doctor.py --setup"
    started = time.monotonic()
    try:
        with Browser() as browser:
            engine = browser.start()
            version = getattr(engine, "version", "?")
            label = browser.engine
        return OK, f"Chromium {version} starts fine ({label}, {time.monotonic() - started:.1f}s)"
    except BrowserUnavailable as exc:
        return FAIL, str(exc)
    except Exception as exc:
        return FAIL, f"browser failed to start: {str(exc).splitlines()[0]}"


def check_network() -> tuple[str, str]:
    from wrp.config import browser_headers
    from wrp.net import http_request

    resp = http_request("https://example.com/", headers=browser_headers(), timeout=12)
    if resp.error:
        return WARN, f"could not reach example.com ({resp.error}). Proxy/firewall or offline?"
    return OK, f"internet reachable (example.com answered {resp.status} in {resp.elapsed_ms} ms)"


def main(argv: list[str] | None = None) -> int:
    reconfigure_stdout()
    p = argparse.ArgumentParser(description="Diagnose and set up web-research-pro.")
    p.add_argument("--setup", action="store_true", help="install everything into ~/.web-research-pro/venv")
    p.add_argument("--no-browser", action="store_true", help="with --setup: skip the Chromium download")
    p.add_argument("--json", action="store_true")
    p.add_argument("--offline", action="store_true", help="skip the internet check")
    args = p.parse_args(argv)
    if args.setup:
        return setup(args.no_browser)

    # Use the private venv when it exists, like the other scripts do.
    from wrp.config import ensure_venv

    ensure_venv()

    checks = []
    in_venv = Path(sys.prefix).resolve() == venv_dir().resolve()
    checks.append(("python", OK if sys.version_info >= (3, 9) else FAIL,
                   f"Python {platform.python_version()} at {sys.executable}" + (" (private venv)" if in_venv else "")))
    checks.append(("venv", OK if venv_python().exists() else WARN,
                   f"{venv_dir()}" if venv_python().exists() else "no private venv yet -> python3 doctor.py --setup"))
    for module, purpose in (("playwright", "browser for JavaScript pages"), ("trafilatura", "clean article text"),
                            ("pypdf", "PDF text"), ("certifi", "TLS certificates")):
        try:
            mod = __import__(module)
            version = getattr(mod, "__version__", "")
            if not version:
                from importlib.metadata import version as _v

                try:
                    version = _v(module)
                except Exception:
                    version = "installed"
            checks.append((module, OK, f"{version} — {purpose}"))
        except ImportError:
            level = WARN if module != "playwright" else FAIL
            checks.append((module, level, f"missing ({purpose}) -> python3 doctor.py --setup"))
    status, detail = check_browser()
    checks.append(("chromium", status, detail))
    if not args.offline:
        status, detail = check_network()
        checks.append(("network", status, detail))
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    checks.append(("proxy", OK, f"using HTTPS proxy {proxy.split('@')[-1]}" if proxy else "no proxy configured"))
    keys = [k for k in ("BRAVE_API_KEY", "TAVILY_API_KEY", "SEARXNG_URL", "JINA_API_KEY", "GITHUB_TOKEN") if os.environ.get(k)]
    checks.append(("search keys", OK, ("configured: " + ", ".join(keys)) if keys else
                   "none (DuckDuckGo + public APIs are used; optional keys give steadier search)"))
    display = platform.system() in ("Darwin", "Windows") or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    checks.append(("login window", OK if display else WARN,
                   "a screen is available for login.py save" if display else
                   "no screen here: use login.py import with exported cookies instead of login.py save"))
    sess = sessions_dir()
    count = len(list(sess.glob("*.json"))) if sess.exists() else 0
    checks.append(("sessions", OK, f"{count} saved in {sess}"))

    if args.json:
        print(json.dumps([{"check": c, "status": s.strip(), "detail": d} for c, s, d in checks], ensure_ascii=False, indent=2))
    else:
        print(f"web-research-pro {VERSION} — doctor\n")
        for name, status, detail in checks:
            print(f"{status} {name:13} {detail}")
        failed = [c for c, s, _ in checks if s == FAIL]
        print()
        if failed:
            print(f"Fix: python3 {HERE / 'doctor.py'} --setup")
        else:
            print("All good. Everything the skill needs is available.")
    return 1 if any(s == FAIL for _, s, _ in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
