"""Client for Patreon's internal web API (the one patreon.com itself calls)."""

import json
import re
import urllib.parse
import urllib.request

from . import config, session

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
API = "https://www.patreon.com/api"
YT_RE = re.compile(r"(?:youtube\.com/(?:watch\?(?:[^\"'\s<>]*&)?v=|embed/|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})")


def api_get(url):
    headers = {"User-Agent": UA, "Accept": "application/vnd.api+json"}
    if session.get():
        headers["Cookie"] = "session_id=" + session.get()
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def check_auth():
    """Name of the signed-in user (or True), False if the cookie is rejected,
    None if there is no cookie."""
    if not session.get():
        return None
    try:
        me = api_get(f"{API}/current_user?fields%5Buser%5D=full_name")
        return me["data"]["attributes"].get("full_name") or True
    except Exception:
        return False


def resolve(feed):
    """Look up the campaign (and collection title) behind a configured feed."""
    if "collection" in feed:
        q = urllib.parse.urlencode({"include": "campaign", "fields[collection]": "title",
                                    "fields[campaign]": "name,url"})
        r = api_get(f"{API}/collection/{feed['collection']}?{q}")
        campaign_id = r["data"]["relationships"]["campaign"]["data"]["id"]
        name = r["data"]["attributes"]["title"]
    else:
        q = urllib.parse.urlencode({"filter[vanity]": feed["vanity"], "fields[campaign]": "name,url"})
        data = api_get(f"{API}/campaigns?{q}")["data"]
        if not data:
            raise ValueError(f"no Patreon creator called '{feed['vanity']}'")
        campaign_id, name = data[0]["id"], data[0]["attributes"]["name"]
    return dict(feed, campaign_id=campaign_id, name=feed["label"] or name.strip())


def youtube_id(attrs):
    for text in ((attrs.get("embed") or {}).get("url"), (attrs.get("embed") or {}).get("html"), attrs.get("content")):
        if text:
            m = YT_RE.search(text)
            if m:
                return m.group(1)
    return None


def fetch_posts(feed):
    params = {
        "filter[campaign_id]": feed["campaign_id"],
        "filter[contains_exclusive_posts]": "true",
        "sort": "-published_at",
        "page[size]": "20",
        "fields[post]": "title,published_at,url,embed,image,post_type,current_user_can_view,content,teaser_text",
        "json-api-version": "1.0",
    }
    if "collection" in feed:
        params["filter[collection_id]"] = feed["collection"]
    url, posts = f"{API}/posts?{urllib.parse.urlencode(params)}", []
    while url and len(posts) < config.POSTS_PER_FEED:
        page = api_get(url)
        for p in page["data"]:
            a = p["attributes"]
            yt = youtube_id(a)
            posts.append({
                "id": p["id"],
                "feed": feed["key"],
                "title": (a.get("title") or "").strip() or "(untitled)",
                "published": a.get("published_at"),
                "patreon_url": a.get("url"),
                "youtube_id": yt,
                "image": f"https://i.ytimg.com/vi/{yt}/mqdefault.jpg" if yt else (a.get("image") or {}).get("url"),
                "locked": not a.get("current_user_can_view"),
                "type": a.get("post_type"),
            })
        url = (page.get("links") or {}).get("next")
    return posts[:config.POSTS_PER_FEED]
