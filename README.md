# patreon-feed

One fast local page listing recent posts from a few Patreon creators or collections. Any post with a YouTube video links straight to YouTube; everything else links to the Patreon post.

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
