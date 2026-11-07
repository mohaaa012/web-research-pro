# Troubleshooting

Start with `python3 ${CLAUDE_SKILL_DIR}/scripts/doctor.py`: it checks Python,
the private venv, every optional package, whether Chromium starts, the
network, proxies, search keys and saved sessions, and prints the fix.

| Symptom (`reason:` or error) | What it means | What to do |
|---|---|---|
| `playwright_not_installed` | the browser rung is unavailable | `doctor.py --setup` (one time) |
| `browser_launch_failed` ... `missing dependencies` (Linux) | Chromium needs system libraries | `~/.web-research-pro/venv/bin/python -m playwright install-deps chromium` (asks for sudo), or install Google Chrome: the scripts fall back to it |
| `javascript_page_not_rendered` / `needs_browser` | the page is an empty JavaScript shell and no browser ran | install the browser, or rely on the reader rung |
| `blocked_by_site` with `blocked_cloudflare`, `captcha`, `datadome`... | an anti-bot wall answered every rung | do not fight it: public API / RSS (`site-recipes.md`), other sources, archive, or ask the user to save the page from their browser |
| `blocked_http429` | too many requests | wait, lower the pace (`crawl.py --delay 3`), fetch fewer pages |
| `login_required` | the page needs an account | the user's own session: `login.py save` or `login.py import` |
| `login_required` while using `--session` | the session expired or belongs to another domain | `login.py check NAME --url ...`, then save it again |
| `not_found` | 404/410 | check the URL; try `--method archive` for removed pages |
| `dns_error` | the domain does not resolve | typo, dead domain, or no internet |
| `proxy_blocked` | this machine's network policy blocked the host | not the website's fault; tell the user which host is blocked |
| `tls_error` | certificate problem | corporate proxy: set `SSL_CERT_FILE` to its CA bundle; macOS python.org: run "Install Certificates.command" or `doctor.py --setup` (installs certifi) |
| `timeout` | slow server | `--timeout 60`; for browsers also `--wait-for` a specific element |
| `reader_http_4xx`, `reader_got_challenge_page` | r.jina.ai could not read it either | expected for strongly protected sites; continue to archive / other sources |
| `archive_no_snapshot` | the Wayback Machine never saved it | no copy exists; look elsewhere |
| PDF warning "No text layer found" | scanned PDF (images only) | screenshot pages and read them visually, or find a text version |
| DuckDuckGo "asked for a human check" | too many automated searches from this IP | wait a few minutes; set `BRAVE_API_KEY` or `TAVILY_API_KEY` for a stable API; use built-in WebSearch if available |
| `reddit: Reddit refused anonymous API access` | Reddit limits anonymous API calls | `search.py "QUERY site:reddit.com"` instead |
| `login.py save`: "no screen available" | SSH/cloud/container | export cookies in your browser and `login.py import` |
| Google login says "this browser may not be secure" | Google blocks automated browsers | export cookies from your normal browser and `login.py import` |
| Output is cut with `[truncated: N more chars]` | output window limit | `--offset N` to continue, or `--out file.md` and read the file |
| Data from a sidebar/table is missing | article extraction dropped it | `--extract full` |

## Where things are stored

- `~/.web-research-pro/venv/` — private Python environment (safe to delete; `doctor.py --setup` recreates it)
- `~/.web-research-pro/sessions/` — saved logins (owner-only permissions; delete a file to log out)
- `~/.web-research-pro/monitor/` — page snapshots for monitor.py
- Playwright's Chromium lives in its standard cache (`~/.cache/ms-playwright`, `~/Library/Caches/ms-playwright` or `%USERPROFILE%\AppData\Local\ms-playwright`)

## Privacy notes

- Plain fetches and the browser talk only to the site you asked for.
- The **reader** rung sends the URL (never cookies) to Jina AI; the
  **archive** rung asks archive.org for a copy. Both are skipped for
  `--session` fetches, for private/intranet addresses, and with `--no-third-party`.
- Search queries go to the engine you choose.
