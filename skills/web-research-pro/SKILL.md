---
name: web-research-pro
description: Advanced web research and page reading beyond the built-in WebSearch/WebFetch. Renders JavaScript pages in a real headless browser, escalates automatically when a site blocks simple requests (browser, reader service, Wayback Machine), reads pages behind the user's OWN logins via locally saved sessions, extracts full text from PDFs, feeds and JSON APIs, crawls docs sites, watches pages for changes and searches several engines (DuckDuckGo by region, Brave/Tavily/SearXNG with keys, Wikipedia, Hacker News, Reddit, GitHub, arXiv, Stack Overflow). Use it whenever the user wants something researched, looked up, verified or compared online, gives a URL to read or summarise, asks to scrape, crawl or monitor a site or price, or when WebFetch/WebSearch came back empty, partial, blocked, login-walled or JavaScript-only. Also for Spanish requests such as busca en internet, investiga, lee este enlace, mira esta web, rastrea or vigila esta página.
license: MIT
compatibility: Claude Code or any agent with a shell and Python 3.9+. Browser features need Playwright + Chromium (installed once by doctor.py --setup). Needs network access to the sites being read.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*)
---

# Web Research Pro

A toolbox of scripts that read the web the way a careful person would: cheap
methods first, a real browser when the page needs JavaScript, public archives
or reader services when a site refuses automated requests, and the user's own
login when the content is private to them. Everything runs on the user's
machine; results come back as clean Markdown with a header saying exactly how
the content was obtained.

Scripts live in `${CLAUDE_SKILL_DIR}/scripts/` (if that variable shows up
literally, use the folder this SKILL.md was loaded from). Run them with
`python3` (`python` or `py` on Windows). Each one supports `--help`.

| Script | What it is for |
|---|---|
| `fetch.py URL...` | Read pages, PDFs, feeds, JSON. Automatic ladder: http → browser → reader → archive |
| `search.py "query"` | Search the web and specialised sources; `--fetch K` also reads the top results |
| `crawl.py URL` | Save a whole docs site / blog section as Markdown files (polite, obeys robots.txt) |
| `monitor.py check URL` | Detect changes since the last check (prices, changelogs, rankings) |
| `login.py save/import` | Store the user's own logged-in session locally, for `--session NAME` |
| `doctor.py` | Diagnose problems; `--setup` installs the optional pieces once |

## Why use this instead of the built-in tools

WebFetch hands the page to a small model and returns its summary, so exact
figures, tables and quotes get lost; it cannot run JavaScript, log in, or read
localhost. WebSearch can be unavailable or limited by region. The scripts here
return the **full text**, keep links and tables, and report failures honestly.
Built-in WebSearch is still fine for a quick factual lookup — use whichever is
cheaper for the question, and switch to these scripts as soon as you need the
real content or a built-in tool comes back empty, blocked or vague.

## First use

If a script reports missing pieces (no browser, no PDF support), run
`python3 ${CLAUDE_SKILL_DIR}/scripts/doctor.py`. Its `--setup` option creates a
private virtualenv in `~/.web-research-pro/venv` and downloads Chromium
(one time, ~200 MB). Tell the user in one line what you are installing and why
before running it. Without it everything except the browser still works.
When the user asks to set up, install, update or check this skill, run
`doctor.py --setup` (or plain `doctor.py` to check) and summarise the result.

## Choosing the right tool

- **One known URL** → `fetch.py URL`. The ladder escalates by itself; you only
  force a method when you already know the site (e.g. `--method browser` for a
  dashboard or a single-page app, to skip a wasted plain request).
- **Interactive pages** → `--scroll N` for infinite feeds, `--click "CSS"` for
  "load more" or cookie banners, `--wait-for "CSS"` for slow widgets,
  `--screenshot shot.png` when layout/charts matter (then look at the image).
- **Long documents** → `--out file.md` (or `--out-dir dir/` for many URLs) and
  then grep/read the file. Printing 80,000 characters into the conversation
  wastes context; reading the parts you need does not.
- **Listings, prices, tables, stats** → default `--extract auto` keeps them.
  Use `--extract main` only for clean article text, `--extract full` if
  something seems missing.
- **Many pages of one site** → `crawl.py URL --max-pages N` (add `--sitemap`
  when the site has one), then read `INDEX.md` and grep the folder.
- **Finding sources** → `search.py "query"`. Search in the user's language and
  in English when that widens coverage; add `--engine web,wikipedia,hn,reddit`
  for community/encyclopedic angles, `arxiv` for papers, `github` for code,
  `stackoverflow` for programming errors; `--time w` for recent news;
  `--region es-es` (or another country-language) for local results.
- **"Tell me when it changes"** → `monitor.py check URL` (with `--regex` to
  watch just a price or number). Suggest scheduling it (cron, Task Scheduler,
  or `/loop`) if the user wants alerts.

## Research workflow (for "investiga…", comparisons, market questions)

1. Break the question into 2–5 concrete sub-questions. Ask the user only if the
   goal is genuinely ambiguous; otherwise state your interpretation and go.
2. Search with 2–4 different phrasings. Prefer **primary sources**: official
   sites and docs, APIs, filings, datasets, the people involved. Use aggregators
   and forums to find leads and opinions, not as proof of facts.
3. Read the best 3–8 sources in full with `fetch.py` (in one call with
   `--out-dir` when there are several). Skim titles of the rest.
4. Cross-check every key fact (numbers, dates, claims) in at least two
   independent sources. When they disagree, say so and explain which is more
   credible and why.
5. Check dates. Prefer the newest data, state the date of each figure, and
   flag anything that may be outdated (including archived copies).
6. Write the answer (format below). Separate what the sources say from your
   own analysis or recommendation.

## Answer format

Answer in the user's language. For a quick lookup, a few sentences with
inline sources are enough. For research, use this shape:

```
## Respuesta corta / Short answer
2–4 sentences that answer the question directly.

## Hallazgos clave / Key findings
- Finding with a number or fact [1]
- Finding confirmed by two sources [2][3]

## Detalles / Details   (tables when comparing options)

## Fiabilidad y lagunas / Confidence and gaps
What could not be verified, sources that were blocked or behind a login,
archived copies used (with their date), conflicting data.

## Fuentes / Sources
[1] Title — URL (date; how it was read: http/browser/archive 2024-05-01)
```

## Being honest about what you read

The header of every result shows `ok`, `method`, the attempt chain and
warnings. Use it:
- Only report what is in the fetched text. If a page failed, say it failed
  and why (`reason:`), and never fill the gap with guesses about its content.
- `method: archive` means a Wayback Machine copy: give its `archived_at` date.
- `method: reader` means a third-party (r.jina.ai) conversion: fine to use,
  mention it if precision matters.
- `paywall_hint` means part of the article may be missing; say so.
- Quote exact wording when the user needs precision; paraphrase otherwise.

## When a page will not open

Read the `reason` and `suggestion` lines, then:
- **blocked_by_site** (Cloudflare, CAPTCHA, 403/429): the ladder already tried
  every legitimate route. Look for the same facts somewhere else — the site's
  public API or RSS feed (see `references/site-recipes.md`), its press page,
  other outlets citing it, the archive (`--method archive`). Or ask the user
  to open the page in their own browser and save it as PDF/HTML; then read the
  file. Do not try to defeat CAPTCHAs or anti-bot systems.
- **login_required**: the content is behind an account. Offer the user the
  login flow below — only for their own accounts.
- **needs_browser / javascript_page_not_rendered**: run `doctor.py --setup`.
- **not_found**: check the URL; `--method archive` may still have it.
- **timeout / dns_error / proxy_blocked**: network or environment issue; retry
  once, then tell the user what is blocked.
- **No text in a PDF** (scanned): say so; a screenshot read visually may help.

`references/troubleshooting.md` covers more cases.

## Reading pages behind the user's own login

Some content is only visible to the logged-in user (their dashboards, orders,
private groups, analytics). With their permission:

1. Explain that they will log in themselves; you never see the password.
2. On a machine with a screen: `python3 ${CLAUDE_SKILL_DIR}/scripts/login.py save NAME --url LOGIN_URL`
   opens a browser window; the user logs in (2FA works) and closes the window.
3. Without a screen (SSH, cloud), or for sites that refuse automated browsers
   (Google, for example): the user exports cookies from their normal browser
   with an extension such as "Get cookies.txt LOCALLY", then
   `login.py import NAME cookies.txt`, and deletes the exported file.
4. Read with `fetch.py URL --session NAME` (works with `crawl.py` and
   `monitor.py` too). `login.py list` shows saved sessions, `check` tests one.

Never ask for or accept passwords, tokens or cookie values in the chat: they
would end up in logs and transcripts. Session files stay in
`~/.web-research-pro/sessions/` with owner-only permissions, and pages read
with a session are never sent to third-party fallbacks.

## Boundaries, and why

- **No CAPTCHA solving, paywall bypassing or anti-bot evasion.** Those
  defences express the site owner's decision; getting around them can break
  terms of service or laws, and it gets the user's IP banned. Use the public
  routes above instead.
- **Only the user's own accounts.** A session is the user acting as
  themselves; using someone else's access is unauthorised access.
- **Be polite with volume.** `crawl.py` obeys robots.txt, waits between
  requests and caps pages. Keep bulk jobs proportional to the question.
- **Personal data:** collect what the task needs, nothing more.

## Command reference

`references/commands.md` lists every option of every script with examples.
The most used:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/fetch.py URL [URL...] [--method browser] [--out-dir dir] [--json]
python3 ${CLAUDE_SKILL_DIR}/scripts/search.py "query" [--engine web,hn] [--region es-es] [--time m] [--fetch 3]
python3 ${CLAUDE_SKILL_DIR}/scripts/crawl.py URL [--max-pages 30] [--sitemap] [--method auto]
python3 ${CLAUDE_SKILL_DIR}/scripts/monitor.py check URL [--regex "Price: (\S+)"] [--name NAME]
python3 ${CLAUDE_SKILL_DIR}/scripts/login.py save NAME --url LOGIN_URL | import NAME FILE | list
python3 ${CLAUDE_SKILL_DIR}/scripts/doctor.py [--setup]
```

Exit codes: 0 = everything worked, 1 = some URL failed (details in the
output), 2 = usage or configuration error.
