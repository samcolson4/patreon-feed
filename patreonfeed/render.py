"""Turns the store's state into the HTML page, using the files in templates/."""

from datetime import datetime, timezone
from html import escape as e
from pathlib import Path
from string import Template

from . import config

TEMPLATES = {p.stem: Template(p.read_text()) for p in (Path(__file__).parent / "templates").glob("*.html")}


def ago(iso):
    if not iso:
        return ""
    secs = (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    for unit, n in (("y", 31536000), ("mo", 2592000), ("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= n:
            return f"{int(secs // n)}{unit} ago"
    return "just now"


def card(post, feeds):
    feed_key = post.get("feed", "")
    yt = post["youtube_id"]
    if yt:
        badge = '<span class="b yt">YouTube</span>'
    elif post["locked"]:
        badge = '<span class="b lock">Locked</span>'
    else:
        badge = '<span class="b">Patreon</span>'
    return TEMPLATES["card"].substitute(
        href=e(f"https://www.youtube.com/watch?v={yt}" if yt else post["patreon_url"] or ""),
        id=e(post["id"]),
        feed=e(feed_key),
        yt="1" if yt else "0",
        image=f'<img loading="lazy" src="{e(post["image"])}" alt="">' if post["image"] else "",
        badge=badge,
        title=e(post["title"]),
        feed_name=e(feeds.get(feed_key, {}).get("name", feed_key)),
        published=e(post["published"] or ""),
        ago=ago(post["published"]),
    )


def auth_box(authed):
    if authed is None:
        status, label, msg = "bad", "Not signed in", "No Patreon cookie set, so only public posts are visible."
    elif authed is False:
        status, label, msg = "bad", "Cookie rejected", "Cookie rejected — locked posts will stay locked. Paste a fresh one."
    else:
        status, label, msg = "ok", "Signed in" if authed is True else f"Signed in as {authed}", ""
    return TEMPLATES["auth"].substitute(
        status=status, label=e(label), message=e(msg), open="" if status == "ok" else " open")


def page(s):
    warnings = [e(x) for x in s["errors"]]
    if not config.FEEDS:
        warnings.append("No feeds configured — set FEEDS in .env.")
    elif s["updated"] is None:
        warnings.append("Fetching posts… refresh in a few seconds.")
    return TEMPLATES["page"].substitute(
        chips="".join(f'<button class="chip" data-c="{e(k)}">{e(f["name"])}</button>' for k, f in s["feeds"].items()),
        updated=ago(s["updated"]) if s["updated"] else "never",
        auth=auth_box(s["authed"]),
        warnings="".join(f'<p class="warn">{w}</p>' for w in warnings),
        cards="".join(card(p, s["feeds"]) for p in s["posts"]),
    )
