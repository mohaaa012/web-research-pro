# Command reference

All scripts: `python3 ${CLAUDE_SKILL_DIR}/scripts/<script> --help` prints the
same information. Exit codes: `0` ok, `1` some target failed (details are in
the output), `2` usage/configuration error.

## Contents
- [fetch.py](#fetchpy) — read pages, PDFs, feeds, JSON
- [search.py](#searchpy) — web + specialised search
- [crawl.py](#crawlpy) — save a site section to files
- [monitor.py](#monitorpy) — change detection
- [login.py](#loginpy) — the user's own sessions
- [doctor.py](#doctorpy) — diagnosis and setup
- [Environment variables](#environment-variables)

## fetch.py

```
fetch.py URL [URL ...] [options]
```

| Option | Meaning |
|---|---|
| `--method auto\|http\|browser\|reader\|archive` | `auto` (default) climbs http → browser → reader → archive only as needed |
| `--session NAME` | use a session saved with login.py; disables third-party fallbacks |
| `--extract auto\|main\|full` | `auto` keeps data on listings/product pages and uses clean article text on articles |
| `--format markdown\|json\|html`, `--json` | output format (`html` = the raw/rendered HTML) |
| `--max-chars N` / `--offset N` | print a window of the text (default 25,000 chars; `0` = all) |
| `--out FILE` | save the whole result to a file, print a short preview |
| `--out-dir DIR` | save every URL as its own file and print a summary table |
| `--links` | append the list of links found on the page |
| `--screenshot FILE.png` | full-page screenshot (forces the browser) |
| `--scroll N` | scroll N screens for lazy/infinite content (forces the browser) |
| `--click CSS` | click elements before reading, repeatable (cookie banners, "load more") |
| `--wait-for CSS` | wait until an element exists |
| `--wait MS` | extra wait after loading |
| `--timeout S` | seconds per attempt (default 30) |
| `--headed` | visible browser window, for debugging on a machine with a screen |
| `--no-third-party` | never use r.jina.ai or the Wayback Machine |
| `--archive-date YYYYMMDD` | with `--method archive`: snapshot closest to that date |
| `--max-pdf-pages N` | stop PDF extraction after N pages |

Output header fields: `title`, `url` (after redirects), `ok`, `method`,
`attempts` (each rung and why it failed), `http_status`, `content` (type and
extractor), `published`/`author` when the page declares them, `archived_at`
for archive copies, `feeds_found` (RSS/Atom feeds the page advertises),
`warning:` and `suggestion:` lines, then `---` and the text.

Examples:
```bash
fetch.py https://example.com/article
fetch.py https://app.example.com/stats --method browser --wait-for "#chart" --screenshot stats.png
fetch.py https://shop.example.com/search?q=chair --scroll 3 --extract full
fetch.py https://example.com/report.pdf --out report.md
fetch.py URL1 URL2 URL3 URL4 --out-dir sources/
fetch.py https://old.example.com/page --method archive --archive-date 20200101
fetch.py https://example.com/feed.xml          # RSS/Atom -> numbered item list
```

## search.py

```
search.py "query" [--engine LIST] [-n N] [--region cc-ll] [--time d|w|m|y] [--site DOMAIN] [--fetch K] [--json]
```

| Engine | Source | Notes |
|---|---|---|
| `web` (default) | best available web engine | Brave → Tavily → SearXNG if configured, else DuckDuckGo |
| `duckduckgo` / `ddg` | DuckDuckGo HTML + Lite | keyless; can ask for a human check after many searches |
| `brave` | Brave Search API | `BRAVE_API_KEY` (free tier) |
| `tavily` | Tavily API | `TAVILY_API_KEY` (free tier) |
| `searxng` | your SearXNG instance | `SEARXNG_URL`; JSON output must be enabled |
| `wikipedia` | Wikipedia search API | language from `--lang` or `--region` |
| `hn` | Hacker News (Algolia) | points and comment counts |
| `reddit` | Reddit search | Reddit may refuse anonymous API calls from some networks |
| `github` | GitHub repositories | `GITHUB_TOKEN` raises the rate limit |
| `arxiv` | arXiv papers | includes PDF links |
| `stackoverflow` | Stack Exchange API | `--se-site superuser`, `askubuntu`, ... |

`--region` uses country-language codes (`es-es`, `mx-es`, `us-en`, `fr-fr`,
`wt-wt` for none); the default comes from the system locale. `--fetch K` reads
the top K results with the full fetch ladder and prints `--fetch-chars`
(default 4,000) characters of each.

## crawl.py

```
crawl.py START_URL [--max-pages 25] [--depth 2] [--scope prefix|host|domain] [--include RE] [--exclude RE]
         [--sitemap] [--method http|auto|browser] [--session NAME] [--delay 1.0] [--out-dir DIR]
```

- Default scope is the start URL's folder (`/docs/guide/x` → everything under `/docs/guide/`).
- Obeys robots.txt (including `Crawl-delay`), strips tracking parameters,
  skips binaries and duplicates (redirects and identical pages).
- Writes `NNN-<slug>.md` per page, `INDEX.md` (table of pages) and `pages.jsonl`.
- Hard cap of 500 pages per run.

## monitor.py

```
monitor.py check URL [--name NAME] [--regex PATTERN] [--selector CSS] [--method auto|http|browser] [--session NAME]
monitor.py list
monitor.py forget NAME
```

First line of output is `STATUS: NEW | UNCHANGED | CHANGED | ERROR`; a
unified diff follows a change. `--regex` keeps only the matched text (groups
joined with ` | `), so layout changes elsewhere on the page do not trigger
alerts. Snapshots: `~/.web-research-pro/monitor/NAME.json` (last 30 checks).
Monitoring never uses archived copies.

## login.py

```
login.py save NAME --url LOGIN_URL [--timeout 600]   # visible window; close it when logged in
login.py import NAME FILE                             # cookies.txt (Netscape), Cookie-Editor JSON, Playwright state
login.py list [--json]                                # names, domains, counts, expiry — never values
login.py check NAME --url PRIVATE_URL
login.py delete NAME
```

## doctor.py

```
doctor.py [--json] [--offline]      # report
doctor.py --setup [--no-browser]    # private venv + packages + Chromium
```

## Environment variables

| Variable | Effect |
|---|---|
| `WRP_HOME` | data folder (default `~/.web-research-pro`) |
| `WRP_USER_AGENT` | override the browser User-Agent used for page requests |
| `WRP_ACCEPT_LANGUAGE` | override Accept-Language (default from the system locale) |
| `WRP_CHROMIUM_PATH` | use a specific Chromium/Chrome executable |
| `WRP_READER_URL` | alternative reader endpoint (default `https://r.jina.ai/`) |
| `JINA_API_KEY` | higher limits for the reader service |
| `BRAVE_API_KEY`, `TAVILY_API_KEY`, `SEARXNG_URL` | search APIs |
| `GITHUB_TOKEN`, `STACKEXCHANGE_KEY` | higher limits for those sources |
| `HTTPS_PROXY`, `NO_PROXY`, `SSL_CERT_FILE` | proxies and custom certificates (honoured by HTTP and browser) |
