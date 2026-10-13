# patreon-feed
<img width="1273" height="656" alt="Screenshot 2026-10-13 at 05 45 02" src="https://github.com/user-attachments/assets/2f6c25cf-a887-4266-9184-0f3335f3fd48" />

One fast local page listing recent posts from a few Patreon creators or collections. Any post with a YouTube video links straight to YouTube; everything else links to the Patreon post.

This is a response to Patreon who have built the slowest website it is possible to build.

```bash
cp .env.example .env   # set FEEDS
docker compose up -d --build
```

Open http://localhost:8097.

- **FEEDS**: comma-separated list. Each entry is a creator name (`patreon.com/<name>`), a creator URL or a collection URL (`patreon.com/collection/<id>`). Prefix with `Label=` to set the button name, e.g. `Fin vs History=https://www.patreon.com/collection/1245681`.
- **PATREON_SESSION_ID** (optional): your `session_id` cookie from patreon.com (dev tools → Application → Cookies). Without it, only public posts show.
- **Cookie status** is the pill under the header: green when signed in, red when missing or rejected. Click it to paste a new cookie; it's checked straight away and saved in the data volume, taking priority over `.env`.
- Posts refresh every `REFRESH_MINUTES` (default 30) and are cached in the `patreon-feed-data` volume.
- "YouTube only" is on by default and the filters are remembered per browser. Clicked posts are dimmed (stored in your browser); right-click a dimmed post to unmark it.

This uses Patreon's internal web API, the same one patreon.com itself calls, so it could break if they change it.

## Layout

| File | Job |
| --- | --- |
| `app.py` | Entry point: loads the cache and saved cookie, starts refreshing, serves. |
| `patreonfeed/config.py` | Environment variables and `FEEDS` parsing. |
| `patreonfeed/session.py` | The Patreon cookie: from `.env`, or pasted in the page and saved to `/data`. |
| `patreonfeed/patreon.py` | Talks to Patreon's API: sign-in check, feed lookup, posts, YouTube link detection. |
| `patreonfeed/store.py` | Holds the posts, refreshes on a timer, caches to `/data/cache.json`. |
| `patreonfeed/render.py` | Fills the HTML templates from the stored posts. |
| `patreonfeed/web.py` | HTTP routes. |
| `patreonfeed/templates/` | `page.html`, `card.html`, `auth.html`, using `$name` placeholders (Python's `string.Template`). |
| `patreonfeed/static/` | `style.css` and `app.js` (filters and watched marks). |

Templates and static files are read once at startup, so after editing them run `docker compose up -d --build`.
