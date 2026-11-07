#!/usr/bin/env python3
"""Manage the user's OWN logged-in sessions so fetch/crawl can read private pages.

Passwords never pass through Claude or this script: you type them yourself in
a real browser window, or you export cookies from the browser you already use.
Sessions live in ~/.web-research-pro/sessions/ (only your user can read them).

Commands:
  save NAME --url LOGIN_URL     open a browser window, log in by hand, then CLOSE the window to save
  import NAME FILE              import cookies exported from your browser (cookies.txt or JSON)
  list                          show saved sessions (domains, cookie counts, expiry; never values)
  check NAME --url URL          test whether the session still gets past the login wall
  delete NAME                   remove a saved session

Examples:
  python3 login.py save github --url https://github.com/login
  python3 login.py import instagram ~/Downloads/cookies.txt
  python3 fetch.py https://github.com/settings/profile --session github
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wrp.config import ensure_venv, reconfigure_stdout  # noqa: E402

ensure_venv()

from wrp import sessions  # noqa: E402
from wrp.sessions import SessionError  # noqa: E402


def has_display() -> bool:
    if platform.system() in ("Darwin", "Windows"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def cmd_save(args) -> int:
    from wrp.browser import Browser, BrowserUnavailable

    if not has_display():
        print("error: no screen available here (SSH / cloud / container), so a browser window cannot open.\n"
              "Do this instead on your own computer:\n"
              "  1. Log in to the site in your normal browser.\n"
              "  2. Export its cookies with an extension such as 'Get cookies.txt LOCALLY' (cookies.txt).\n"
              f"  3. python3 login.py import {args.name} /path/to/cookies.txt", file=sys.stderr)
        return 2
    path = sessions.session_path(args.name)
    existing = None
    if path.exists():
        try:
            existing = sessions.load_state(args.name)
        except (OSError, ValueError, SessionError):
            existing = None
    browser = Browser(headed=True)
    try:
        engine = browser.start()
    except BrowserUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    context = engine.new_context(storage_state=existing) if existing else engine.new_context()
    page = context.new_page()
    try:
        page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
    except Exception as exc:
        print(f"warning: the login page did not finish loading ({str(exc).splitlines()[0]})", file=sys.stderr)
    print(f"A browser window is open at {args.url}\n"
          f"  -> Log in there with your own account (2FA works as usual).\n"
          f"  -> When you see you are logged in, CLOSE THE WINDOW to save the session '{args.name}'.\n"
          f"  (Waiting up to {args.timeout // 60} minutes...)", flush=True)
    deadline = time.monotonic() + args.timeout
    snapshot = None
    try:
        while time.monotonic() < deadline:
            try:
                snapshot = context.storage_state()  # keep the latest copy in memory
            except Exception:
                break  # browser closed
            if not context.pages:
                break
            if not any(not p.is_closed() for p in context.pages):
                break
            time.sleep(1.5)
        else:
            print("timeout reached: saving whatever session exists now", file=sys.stderr)
    finally:
        try:
            snapshot = context.storage_state()
        except Exception:
            pass
        browser.close()
    if not snapshot or not snapshot.get("cookies"):
        print("error: no cookies were captured; the login may not have finished. Try again.", file=sys.stderr)
        return 1
    sessions.save_state(args.name, snapshot)
    info = sessions.summarize_state(args.name, snapshot)
    print(f"saved session '{args.name}': {info['cookies']} cookies for {', '.join(info['domains'][:6])}")
    print(f"use it with: python3 fetch.py <URL> --session {args.name}")
    return 0


def cmd_import(args) -> int:
    state = sessions.import_cookie_file(args.file)
    sessions.save_state(args.name, state)
    info = sessions.summarize_state(args.name, state)
    print(f"imported session '{args.name}': {info['cookies']} cookies for {', '.join(info['domains'][:8])}")
    if info["expired_cookies"]:
        print(f"note: {info['expired_cookies']} cookies were already expired")
    print(f"the original file may contain your login: delete it now ({args.file})")
    print(f"use it with: python3 fetch.py <URL> --session {args.name}")
    return 0


def cmd_list(args) -> int:
    items = sessions.list_states()
    if args.json:
        print(json.dumps(items, indent=2))
        return 0
    if not items:
        print("no saved sessions. Create one with: login.py save NAME --url LOGIN_URL")
        return 0
    for item in items:
        if item.get("error"):
            print(f"- {item['name']}: {item['error']}")
            continue
        print(f"- {item['name']}: {item['cookies']} cookies · {', '.join(item['domains'][:5])}"
              f" · saved {item['saved']} · next expiry {item['next_expiry'] or 'session-only'}"
              + (f" · {item['expired_cookies']} expired" if item["expired_cookies"] else ""))
    return 0


def cmd_check(args) -> int:
    from wrp.fetcher import FetchOptions, fetch

    result = fetch(args.url, FetchOptions(session=args.name, method=args.method, timeout=30))
    if result.ok:
        print(f"OK: session '{args.name}' can read {result.final_url} ({result.chars} chars, via {result.method})")
        print(f"page title: {result.title}")
        return 0
    print(f"NOT OK: {result.reason}. The session may have expired; run: login.py save {args.name} --url <login page>")
    return 1


def cmd_delete(args) -> int:
    if sessions.delete_state(args.name):
        print(f"deleted session '{args.name}'")
        return 0
    print(f"no session called '{args.name}'")
    return 1


def main(argv: list[str] | None = None) -> int:
    reconfigure_stdout()
    p = argparse.ArgumentParser(description=__doc__.split("Commands:")[0].strip(),
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog="Commands:" + __doc__.split("Commands:", 1)[1])
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("save", help="log in by hand in a visible browser window")
    s.add_argument("name")
    s.add_argument("--url", required=True, help="the site's login page")
    s.add_argument("--timeout", type=int, default=600, help="seconds to wait (default 600)")
    s.set_defaults(fn=cmd_save)
    i = sub.add_parser("import", help="import cookies exported from your browser")
    i.add_argument("name")
    i.add_argument("file")
    i.set_defaults(fn=cmd_import)
    lst = sub.add_parser("list", help="list saved sessions")
    lst.add_argument("--json", action="store_true")
    lst.set_defaults(fn=cmd_list)
    c = sub.add_parser("check", help="test a session against a private URL")
    c.add_argument("name")
    c.add_argument("--url", required=True)
    c.add_argument("--method", choices=["auto", "http", "browser"], default="auto")
    c.set_defaults(fn=cmd_check)
    d = sub.add_parser("delete", help="delete a saved session")
    d.add_argument("name")
    d.set_defaults(fn=cmd_delete)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except SessionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: file not found: {exc.filename}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
