#!/usr/bin/env python3
"""Watch a page and report what changed since the last check.

Good for prices, stock, changelogs, job posts, game update notes, rankings...
The first check stores a snapshot; later checks print CHANGED with a diff, or
UNCHANGED. Snapshots live in ~/.web-research-pro/monitor/.

Commands:
  check URL [--name NAME] [--regex PATTERN] [--selector CSS]   compare with the last snapshot
  list                                                          show what is being watched
  forget NAME                                                   delete a watch

Examples:
  python3 monitor.py check https://example.com/product --regex "Precio: ([0-9.,]+ ?€)"
  python3 monitor.py check https://site.com/changelog --name changelog
  python3 monitor.py check https://app.site.com/stats --selector "#stats" --session mysite
Tip: run it on a schedule (cron, Task Scheduler or Claude /loop) to get alerts.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wrp.config import ensure_private_dir, ensure_venv, monitor_dir, reconfigure_stdout  # noqa: E402

ensure_venv()

from wrp.fetcher import FetchOptions, fetch  # noqa: E402
from wrp.output import slugify_url  # noqa: E402

MAX_STORED_CHARS = 300_000
HISTORY = 30


def _path(name: str):
    if not re.match(r"^[A-Za-z0-9._-]{1,80}$", name):
        raise SystemExit("error: names may only use letters, digits, '.', '_' and '-'")
    return monitor_dir() / f"{name}.json"


def _normalize(text: str) -> str:
    # ignore pure whitespace churn so only real changes are reported
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _selected_text(url: str, selector: str, opts: FetchOptions) -> tuple[str, str]:
    from wrp.browser import Browser
    from wrp.sessions import load_state

    state = load_state(opts.session) if opts.session else None
    with Browser() as browser:
        engine = browser.start()
        context = engine.new_context(storage_state=state) if state else engine.new_context()
        try:
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=opts.timeout * 1000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            page.wait_for_selector(selector, timeout=opts.timeout * 1000)
            texts = page.locator(selector).all_inner_texts()
            return "\n".join(texts), page.title()
        finally:
            context.close()


def cmd_check(args) -> int:
    name = args.name or slugify_url(args.url, 60)
    path = _path(name)
    opts = FetchOptions(method=args.method, session=args.session, timeout=args.timeout,
                        third_party=False)  # a live check must never read an old archived copy
    if args.selector:
        try:
            text, title = _selected_text(args.url, args.selector, opts)
        except Exception as exc:
            print(f"STATUS: ERROR\nerror: could not read selector {args.selector!r}: {str(exc).splitlines()[0]}")
            return 2
    else:
        result = fetch(args.url, opts)
        if not result.ok:
            print(f"STATUS: ERROR\nerror: could not read the page ({result.reason})")
            for tip in result.suggestions:
                print(f"suggestion: {tip}")
            return 2
        text, title = result.content, result.title
    if args.regex:
        matches = re.findall(args.regex, text, flags=re.I | re.M)
        flat = [m if isinstance(m, str) else " | ".join(m) for m in matches]
        if not flat:
            print(f"STATUS: ERROR\nerror: the pattern {args.regex!r} was not found on the page")
            return 2
        text = "\n".join(flat)
    text = _normalize(text)[:MAX_STORED_CHARS]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    previous = None
    if path.exists():
        with open(path, encoding="utf-8") as handle:
            previous = json.load(handle)
    record = previous or {"name": name, "url": args.url, "created": now, "history": []}
    record.update({"url": args.url, "title": title, "last_checked": now, "regex": args.regex, "selector": args.selector})
    if previous is None:
        status = "NEW"
    elif previous.get("hash") == digest:
        status = "UNCHANGED"
    else:
        status = "CHANGED"
        record["last_changed"] = now
    record["history"] = (record.get("history", []) + [{"at": now, "hash": digest[:16], "chars": len(text),
                                                         "status": status}])[-HISTORY:]
    old_text = (previous or {}).get("text", "")
    record["hash"], record["text"] = digest, text
    ensure_private_dir(path.parent)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=1)
    print(f"STATUS: {status}\nwatch: {name}\nurl: {args.url}\nchecked: {now}")
    if previous:
        print(f"previous check: {previous.get('last_checked')}  (last change: {previous.get('last_changed', 'never')})")
    if status == "NEW":
        print(f"first snapshot saved ({len(text)} chars). Run the same command later to see changes.")
        if args.regex:
            print("current value(s):\n" + text[:2000])
    elif status == "CHANGED":
        diff = list(difflib.unified_diff(old_text.splitlines(), text.splitlines(), "before", "now", lineterm="", n=1))
        shown = diff[: args.max_diff_lines]
        print(f"--- diff ({len(diff)} lines{', truncated' if len(diff) > len(shown) else ''}) ---")
        print("\n".join(shown))
    return 0


def cmd_list(args) -> int:
    folder = monitor_dir()
    rows = []
    for path in sorted(folder.glob("*.json")) if folder.exists() else []:
        try:
            with open(path, encoding="utf-8") as handle:
                d = json.load(handle)
            rows.append(d)
        except (OSError, ValueError):
            continue
    if not rows:
        print("nothing is being watched yet. Start with: monitor.py check URL")
        return 0
    for d in rows:
        print(f"- {d['name']}: {d['url']} · checked {d.get('last_checked')} · last change {d.get('last_changed', 'never')}"
              f" · {len(d.get('history', []))} checks")
    return 0


def cmd_forget(args) -> int:
    path = _path(args.name)
    if path.exists():
        path.unlink()
        print(f"stopped watching '{args.name}'")
        return 0
    print(f"no watch called '{args.name}'")
    return 1


def main(argv: list[str] | None = None) -> int:
    reconfigure_stdout()
    p = argparse.ArgumentParser(description="Detect changes on web pages.",
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog="Commands:" + __doc__.split("Commands:", 1)[1])
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check", help="fetch the page and compare with the last snapshot")
    c.add_argument("url")
    c.add_argument("--name", help="short name for this watch (default derived from the URL)")
    c.add_argument("--regex", help="only watch the text matching this regular expression")
    c.add_argument("--selector", help="only watch this CSS selector (uses the browser)")
    c.add_argument("--method", choices=["auto", "http", "browser"], default="auto")
    c.add_argument("--session", help="saved login session (see login.py)")
    c.add_argument("--timeout", type=float, default=30)
    c.add_argument("--max-diff-lines", type=int, default=80)
    c.set_defaults(fn=cmd_check)
    lst = sub.add_parser("list", help="list watches")
    lst.set_defaults(fn=cmd_list)
    f = sub.add_parser("forget", help="delete a watch")
    f.add_argument("name")
    f.set_defaults(fn=cmd_forget)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
