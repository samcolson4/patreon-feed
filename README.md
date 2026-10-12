# patreon-feed

One fast local page listing recent posts from a few Patreon creators. Any post with a YouTube video links straight to YouTube; everything else links to the Patreon post.

```bash
cp .env.example .env   # set CREATORS and PATREON_SESSION_ID
docker compose up -d --build
```

Open http://localhost:8097.

- **CREATORS**: comma-separated creator names (`patreon.com/<name>`) or full URLs.
- **PATREON_SESSION_ID**: your `session_id` cookie from patreon.com (dev tools → Application → Cookies). Without it, only public posts show. It lasts for months; if it expires, the page shows a warning.
- Posts refresh every `REFRESH_MINUTES` (default 30) and are cached in the `patreon-feed-data` volume.
- Clicked posts are dimmed (stored in your browser); right-click a dimmed post to unmark it.

This uses Patreon's internal web API, the same one patreon.com itself calls, so it could break if they change it.
