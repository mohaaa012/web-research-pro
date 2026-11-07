# Site recipes: public routes to the data

When a website blocks automated requests, or the page is heavy JavaScript,
the same data is often available from an **official or long-standing public
endpoint** that returns clean JSON. `fetch.py` prints JSON nicely, so you can
read these directly: `fetch.py "https://registry.npmjs.org/react/latest"`.

Endpoints marked *(unofficial)* are used widely but not formally documented by
the company; they can change. If one fails, fall back to the normal page.

## Contents
- [Developer ecosystems](#developer-ecosystems)
- [Communities and social](#communities-and-social)
- [Games and apps](#games-and-apps)
- [Reference, papers, data](#reference-papers-data)
- [News, blogs and changing pages](#news-blogs-and-changing-pages)

## Developer ecosystems

| Need | Endpoint |
|---|---|
| npm package metadata | `https://registry.npmjs.org/<pkg>` (all versions) · `.../<pkg>/latest` |
| npm weekly downloads | `https://api.npmjs.org/downloads/point/last-week/<pkg>` |
| PyPI package | `https://pypi.org/pypi/<pkg>/json` |
| PyPI downloads | `https://pypistats.org/api/packages/<pkg>/recent` |
| Rust crate | `https://crates.io/api/v1/crates/<name>` (downloads, versions) |
| GitHub repo / releases | `https://api.github.com/repos/<owner>/<repo>` · `.../releases/latest` |
| A file in a GitHub repo | `https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>` |
| Go module docs | `https://pkg.go.dev/<module>` (plain HTML, reads fine) |

## Communities and social

| Need | Endpoint |
|---|---|
| Reddit listing or thread as JSON | add `.json` to the URL: `https://www.reddit.com/r/<sub>/top.json?t=week&limit=25` (may be refused from some networks) |
| Hacker News items | `https://hacker-news.firebaseio.com/v0/topstories.json` · `.../item/<id>.json` |
| Hacker News search | `search.py "query" --engine hn` |
| YouTube video title/channel | `https://www.youtube.com/oembed?url=<video URL>&format=json` |
| TikTok video title/author | `https://www.tiktok.com/oembed?url=<video URL>` |
| X/Twitter post text | `https://publish.twitter.com/oembed?url=<post URL>` *(may stop working)* |
| Instagram, Facebook, LinkedIn, TikTok profiles | login walls: use the user's own session (login.py) or report it as not accessible |

## Games and apps

| Need | Endpoint |
|---|---|
| Roblox: place ID → universe ID | `https://apis.roblox.com/universes/v1/places/<placeId>/universe` *(unofficial)* |
| Roblox game stats (playing now, visits, favourites, dates) | `https://games.roblox.com/v1/games?universeIds=<id>,<id>` *(unofficial)* |
| Roblox likes/dislikes | `https://games.roblox.com/v1/games/votes?universeIds=<id>` *(unofficial)* |
| Roblox game icons | `https://thumbnails.roblox.com/v1/games/icons?universeIds=<id>&size=512x512&format=Png` *(unofficial)* |
| Roblox group / user | `https://groups.roblox.com/v1/groups/<id>` · `https://users.roblox.com/v1/users/<id>` *(unofficial)* |
| Roblox discovery/charts pages | JavaScript-heavy: `fetch.py https://www.roblox.com/charts --method browser --scroll 3` |
| Steam game details | `https://store.steampowered.com/api/appdetails?appids=<appid>&cc=es&l=spanish` |
| Steam players online now | `https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid=<appid>` |
| iOS App Store app | `https://itunes.apple.com/lookup?id=<appId>&country=es` · search: `https://itunes.apple.com/search?term=<words>&entity=software&country=es` |

The Roblox place ID is the number in a game URL (`roblox.com/games/<placeId>/name`).
Convert it to a universe ID first, then query several games in one call to
compare them (e.g. for competitor research).

## Reference, papers, data

| Need | Endpoint |
|---|---|
| Wikipedia summary | `https://<lang>.wikipedia.org/api/rest_v1/page/summary/<Title>` |
| Wikipedia full article | normal page URL works well with `fetch.py` |
| arXiv paper search | `search.py "query" --engine arxiv` (PDF links included) |
| Any PDF | `fetch.py URL.pdf --out paper.md` (page markers keep citations precise) |
| Weather | `https://api.open-meteo.com/v1/forecast?latitude=<lat>&longitude=<lon>&current=temperature_2m,wind_speed_10m` |
| Crypto prices | `https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=eur,usd` (rate-limited) |
| Old versions of any page | `fetch.py URL --method archive --archive-date YYYYMMDD` |

## News, blogs and changing pages

- Most news sites and blogs publish RSS/Atom. `fetch.py` lists them as
  `feeds_found:`; reading the feed is faster and rarely blocked. Common paths:
  `/feed`, `/rss`, `/feed.xml`, `/atom.xml`, `/index.xml`.
- WordPress sites expose `https://<site>/wp-json/wp/v2/posts?per_page=10`
  (title, date, content as JSON).
- Changelogs, prices, rankings: `monitor.py check URL --regex "..."`.
- Paywalled articles: do not bypass. Look for the press release, the
  original study, the author's own post, or other outlets reporting the same
  facts, and say that the original was paywalled.
