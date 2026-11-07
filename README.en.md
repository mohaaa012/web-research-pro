<p align="center">
  <img src=".claude-plugin/icon.png" width="120" alt="Web Research Pro">
</p>

<h1 align="center">Web Research Pro</h1>

<p align="center">
  <b>A Claude skill for real web research:</b> JavaScript pages, legitimate fallbacks when sites block bots,
  your own logins, full PDFs, site crawling, change monitoring and multi-engine search.
</p>

<p align="center"><a href="README.md">Versión en español</a></p>

---

## Why

Claude's built-in WebFetch/WebSearch return a small-model *summary* of a page, cannot run JavaScript, cannot log in,
and fail on compressed PDFs. Web Research Pro gives Claude a set of local scripts that:

- **Escalate automatically**: plain request with browser headers → real Chromium → reader service (r.jina.ai) → Wayback Machine copy. It only climbs when needed, and every result says how it was obtained.
- **Return full text** (tables, links and code blocks included), not a summary.
- **Read PDFs, RSS/Atom feeds and JSON APIs.**
- **Use your own sessions** for pages behind your login. You type your password in a real browser window (or import cookies); it never passes through the chat.
- **Crawl** a docs site or blog section into Markdown files (obeys robots.txt, rate-limited, de-duplicated).
- **Monitor** pages or single values (prices, rankings) and show a diff when they change.
- **Search** DuckDuckGo with a region, Brave/Tavily/SearXNG with your keys, plus Wikipedia, Hacker News, Reddit, GitHub, arXiv and Stack Overflow.
- **Stay honest**: when a page cannot be read it says why and suggests legitimate alternatives — it never invents content.

Measured on 4 real tasks against a strong WebFetch-only baseline: **100% vs 75%** (details in [docs/BENCHMARK.md](docs/BENCHMARK.md)). 79 automated tests run on Linux, macOS and Windows.

## Install

Requires **Python 3.9+** and [Claude Code](https://code.claude.com). The installer creates a private venv in `~/.web-research-pro` and downloads Chromium once (~200 MB).

macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/mohaaa012/web-research-pro/main/install.sh | bash
```

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/mohaaa012/web-research-pro/main/install.ps1 | iex
```

As a Claude Code plugin:

```bash
claude plugin marketplace add mohaaa012/web-research-pro
```

```bash
claude plugin install web-research-pro@mohaaa012-plugins
```

then ask Claude to "set up web-research-pro" once (it installs the browser).

claude.ai: download `web-research-pro.skill` from [Releases](https://github.com/mohaaa012/web-research-pro/releases) and upload it in Settings → Capabilities → Skills.

Check your setup:

```bash
python3 ~/.claude/skills/web-research-pro/scripts/doctor.py
```

## Use

Just talk to Claude: *"Research the mechanics shared by the top 10 Roblox games right now"*, *"Read this PDF and give me the key figures"*, *"Watch this product page and tell me if the price drops below €150"*. Claude picks the right script.

| Script | Purpose |
|---|---|
| `fetch.py` | Read pages/PDFs/feeds/JSON with the automatic ladder; screenshots, scrolling, clicks |
| `search.py` | Web + specialised search; `--fetch K` also reads the top K results |
| `crawl.py` | Save a site section as Markdown files |
| `monitor.py` | Detect changes in a page or a single value |
| `login.py` | Store your own logged-in session locally |
| `doctor.py` | Diagnose and set up |

Full option reference: [commands.md](skills/web-research-pro/references/commands.md).

## What it does not do

No CAPTCHA solving, no paywall bypassing, no anti-bot evasion, no access to accounts that are not yours. Those
defences are the site owner's decision; the skill uses public routes instead (APIs, RSS, archives, other sources)
and tells you plainly when something is not accessible.

## Privacy

Everything runs on your machine. Only two optional rungs involve third parties: the reader service (receives the URL,
never cookies) and the Wayback Machine. Both are skipped with `--no-third-party`, for private/intranet addresses, and
whenever a session is used. See [SECURITY.md](SECURITY.md).

## Development

```bash
make dev && make test
```

Evals live in `skills/web-research-pro/evals/` in the `claude plugin eval` format. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 mohaaa012.
