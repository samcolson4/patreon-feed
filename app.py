"""Patreon feed: one fast page listing recent posts from a few creators,
linking straight to YouTube wherever a post has a YouTube video.

Stdlib only. Config comes from environment variables (see README).
"""

import html
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def env_secret(name):
    path = os.environ.get(name + "_FILE")
    if path and os.path.exists(path):
        return open(path).read().strip()
    return os.environ.get(name, "").strip()


def parse_feeds(raw):
    """Each entry is a creator name, a creator URL or a collection URL, optionally
    prefixed with "Label=". Entries are separated by commas or newlines."""
    feeds = []
    for entry in re.split(r"[,\n]", raw):
        entry = entry.strip()
        if not entry:
            continue
        m = re.match(r"^([^=/:]+?)\s*=\s*(\S.*)$", entry)
        label, target = (m.group(1).strip(), m.group(2).strip()) if m else (None, entry)
        col = re.search(r"collection/(\d+)", target)
        if col:
            feeds.append({"key": "col:" + col.group(1), "collection": col.group(1), "label": label})
        else:
            vanity = target.split("?")[0].strip("/").rsplit("/", 1)[-1]
            feeds.append({"key": "c:" + vanity, "vanity": vanity, "label": label})
    return feeds


FEEDS = parse_feeds(os.environ.get("FEEDS") or os.environ.get("CREATORS", ""))
SESSION_ID = env_secret("PATREON_SESSION_ID")
REFRESH_MINUTES = int(os.environ.get("REFRESH_MINUTES", "30"))
POSTS_PER_FEED = int(os.environ.get("POSTS_PER_FEED") or os.environ.get("POSTS_PER_CREATOR") or "40")
DATA_DIR = os.environ.get("DATA_DIR", "/data")
PORT = int(os.environ.get("PORT", "8000"))
CACHE_PATH = os.path.join(DATA_DIR, "cache.json")
COOKIE_PATH = os.path.join(DATA_DIR, "session_id")


def load_saved_cookie():
    """A cookie pasted into the web page wins over the one in .env."""
    global SESSION_ID
    try:
        with open(COOKIE_PATH) as f:
            SESSION_ID = f.read().strip() or SESSION_ID
    except OSError:
        pass


def save_cookie(value):
    global SESSION_ID
    value = value.strip().strip('"')
    if value.startswith("session_id="):
        value = value[len("session_id="):].split(";")[0]
    SESSION_ID = value
    os.makedirs(DATA_DIR, exist_ok=True)
    fd = os.open(COOKIE_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
API = "https://www.patreon.com/api"
YT_RE = re.compile(r"(?:youtube\.com/(?:watch\?(?:[^\"'\s<>]*&)?v=|embed/|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})")

state = {"posts": [], "feeds": {}, "updated": None, "errors": [], "authed": None}
lock = threading.Lock()


def api_get(url):
    headers = {"User-Agent": UA, "Accept": "application/vnd.api+json"}
    if SESSION_ID:
        headers["Cookie"] = "session_id=" + SESSION_ID
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


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
    while url and len(posts) < POSTS_PER_FEED:
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
    return posts[:POSTS_PER_FEED]


def check_auth():
    if not SESSION_ID:
        return None
    try:
        me = api_get(f"{API}/current_user?fields%5Buser%5D=full_name")
        return me["data"]["attributes"].get("full_name") or True
    except Exception:
        return False


def refresh():
    feeds, posts, errors = {}, [], []
    with lock:
        known = dict(state["feeds"])
    for feed in FEEDS:
        try:
            f = known.get(feed["key"])
            if not f or f.get("label") != feed["label"]:
                f = resolve(feed)
            feeds[feed["key"]] = f
            posts.extend(fetch_posts(f))
        except Exception as e:
            errors.append(f"{feed['label'] or feed['key']}: {e}")
    authed = check_auth()
    posts.sort(key=lambda p: p["published"] or "", reverse=True)
    with lock:
        state.update(posts=posts, feeds=feeds, errors=errors, authed=authed,
                     updated=datetime.now(timezone.utc).isoformat())
        snapshot = dict(state)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_PATH + ".tmp", "w") as f:
        json.dump(snapshot, f)
    os.replace(CACHE_PATH + ".tmp", CACHE_PATH)
    print(f"refreshed: {len(posts)} posts, {len(errors)} errors", flush=True)


def refresher():
    while True:
        try:
            refresh()
        except Exception as e:
            print("refresh failed:", e, flush=True)
        time.sleep(REFRESH_MINUTES * 60)


def ago(iso):
    if not iso:
        return ""
    secs = (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    for unit, n in (("y", 31536000), ("mo", 2592000), ("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= n:
            return f"{int(secs // n)}{unit} ago"
    return "just now"


def render():
    with lock:
        s = dict(state)
    e = html.escape
    cards = []
    for p in s["posts"]:
        f = s["feeds"].get(p.get("feed", ""), {})
        href = f"https://www.youtube.com/watch?v={p['youtube_id']}" if p["youtube_id"] else p["patreon_url"]
        badge = ('<span class="b yt">YouTube</span>' if p["youtube_id"]
                 else '<span class="b lock">Locked</span>' if p["locked"]
                 else '<span class="b">Patreon</span>')
        img = f'<img loading="lazy" src="{e(p["image"])}" alt="">' if p["image"] else '<div class="noimg"></div>'
        cards.append(
            f'<a class="card" href="{e(href)}" target="_blank" rel="noopener" data-id="{e(p["id"])}" '
            f'data-feed="{e(p.get("feed", ""))}" data-yt="{1 if p["youtube_id"] else 0}">'
            f'<div class="thumb">{img}{badge}</div>'
            f'<div class="meta"><div class="t">{e(p["title"])}</div>'
            f'<div class="s">{e(f.get("name", p.get("feed", "")))} · <time title="{e(p["published"] or "")}">{ago(p["published"])}</time></div></div></a>')
    chips = "".join(f'<button class="chip" data-c="{e(k)}">{e(f["name"])}</button>' for k, f in s["feeds"].items())
    if s["authed"] is False:
        pill, msg = "bad", "Cookie rejected — locked posts will stay locked. Paste a fresh one."
    elif s["authed"] is None:
        pill, msg = "bad", "No Patreon cookie set, so only public posts are visible."
    else:
        pill, msg = "ok", ""
    label = f"Signed in as {e(s['authed'])}" if s["authed"] not in (None, False, True) else \
        "Signed in" if s["authed"] else "Cookie rejected" if s["authed"] is False else "Not signed in"
    notice = COOKIE_FORM.format(pill=pill, label=label, msg=e(msg), open="" if pill == "ok" else " open")
    errs = "".join(f'<p class="warn">{e(x)}</p>' for x in s["errors"])
    if not FEEDS:
        errs += '<p class="warn">No feeds configured — set FEEDS in .env.</p>'
    elif s["updated"] is None:
        errs += '<p class="warn">Fetching posts… refresh in a few seconds.</p>'
    return PAGE.format(cards="".join(cards), chips=chips, notice=notice + errs,
                       updated=e(ago(s["updated"]) if s["updated"] else "never"))


COOKIE_FORM = """<details class="auth"{open}><summary class="pill {pill}">{label}</summary>
<form method="post" action="/cookie"><p>{msg}</p>
<p>Copy the <code>session_id</code> cookie from patreon.com (Dev Tools → Application → Cookies → www.patreon.com) and paste it here.</p>
<input name="session_id" type="password" autocomplete="off" placeholder="session_id value" required>
<button type="submit">Save &amp; check</button></form></details>"""


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Patreon Feed</title>
<style>
:root{{--bg:#fafafa;--fg:#111;--mut:#666;--card:#fff;--line:#e5e5e5;--acc:#c00}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0f0f0f;--fg:#eee;--mut:#999;--card:#1a1a1a;--line:#2a2a2a;--acc:#f33}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif}}
header{{position:sticky;top:0;z-index:1;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}}
h1{{font-size:16px;margin:0 12px 0 0}}.chip{{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:99px;padding:4px 12px;cursor:pointer;font:inherit}}
.chip.on{{background:var(--fg);color:var(--bg)}}label{{color:var(--mut);display:flex;gap:4px;align-items:center}}.upd{{margin-left:auto;color:var(--mut);font-size:12px}}
main{{padding:16px;display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}}
.card{{color:inherit;text-decoration:none;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}}
.card:hover{{border-color:var(--mut)}}.card.seen{{opacity:.45}}.thumb{{position:relative;aspect-ratio:16/9;background:var(--line)}}
.thumb img{{width:100%;height:100%;object-fit:cover;display:block}}.b{{position:absolute;right:6px;bottom:6px;background:#000c;color:#fff;font-size:11px;padding:2px 6px;border-radius:4px}}
.b.yt{{background:var(--acc)}}.meta{{padding:8px 10px 10px}}.t{{font-weight:600}}.s{{color:var(--mut);font-size:12px;margin-top:2px}}
.auth{{margin:8px 16px 0}}.auth summary{{cursor:pointer;display:inline-block;list-style:none}}.auth summary::-webkit-details-marker{{display:none}}
.pill{{border-radius:99px;padding:3px 10px;font-size:12px;font-weight:600}}.pill.ok{{background:#1a7f3722;color:#1a7f37}}.pill.bad{{background:#cf222e22;color:#cf222e}}
.auth form{{margin-top:8px;padding:12px;border:1px solid var(--line);border-radius:8px;background:var(--card);max-width:560px}}.auth p{{margin:0 0 8px}}.auth p:empty{{display:none}}
.auth input{{width:100%;padding:6px 8px;font:inherit;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px;margin-bottom:8px}}
.auth button{{font:inherit;padding:5px 12px;border-radius:6px;border:1px solid var(--line);background:var(--fg);color:var(--bg);cursor:pointer}}
.warn{{margin:8px 16px 0;padding:8px 12px;border-radius:6px;background:#f5a62322;border:1px solid #f5a62366}}.hide{{display:none}}
</style></head><body>
<header><h1>Patreon Feed</h1><button class="chip on" data-c="">All</button>{chips}
<label><input type="checkbox" id="yt"> YouTube only</label><label><input type="checkbox" id="unseen"> Hide watched</label>
<span class="upd">updated {updated}</span></header>{notice}<main>{cards}</main>
<script>
const K="seen",get=()=>{{try{{return new Set(JSON.parse(localStorage.getItem(K)||"[]"))}}catch(e){{return new Set()}}}};
const P="prefs",prefs=(()=>{{try{{return JSON.parse(localStorage.getItem(P))||{{}}}}catch(e){{return {{}}}}}})();
let seen=get(),creator=prefs.feed||"";const cards=[...document.querySelectorAll(".card")];
if(!document.querySelector(`header .chip[data-c="${{CSS.escape(creator)}}"]`))creator="";
document.getElementById("yt").checked=prefs.yt!==false;document.getElementById("unseen").checked=!!prefs.unseen;
document.querySelectorAll("header .chip").forEach(x=>x.classList.toggle("on",x.dataset.c===creator));
function apply(){{const yt=document.getElementById("yt").checked,un=document.getElementById("unseen").checked;
try{{localStorage.setItem(P,JSON.stringify({{feed:creator,yt,unseen:un}}))}}catch(e){{}}
cards.forEach(c=>{{const s=seen.has(c.dataset.id);c.classList.toggle("seen",s);
c.classList.toggle("hide",(creator&&c.dataset.feed!==creator)||(yt&&c.dataset.yt!=="1")||(un&&s))}})}}
document.querySelectorAll("header .chip").forEach(b=>b.onclick=()=>{{creator=b.dataset.c;
document.querySelectorAll("header .chip").forEach(x=>x.classList.toggle("on",x===b));apply()}});
document.getElementById("yt").onchange=document.getElementById("unseen").onchange=apply;
cards.forEach(c=>{{c.addEventListener("click",()=>{{seen.add(c.dataset.id);try{{localStorage.setItem(K,JSON.stringify([...seen]))}}catch(e){{}}apply()}});
c.addEventListener("contextmenu",ev=>{{if(seen.has(c.dataset.id)){{ev.preventDefault();seen.delete(c.dataset.id);try{{localStorage.setItem(K,JSON.stringify([...seen]))}}catch(e){{}}apply()}}}})}});
apply();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] == "/healthz":
            body, ctype = b"ok", "text/plain"
        elif self.path.split("?")[0] == "/":
            body, ctype = render().encode(), "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/cookie":
            length = int(self.headers.get("Content-Length") or 0)
            form = urllib.parse.parse_qs(self.rfile.read(length).decode())
            save_cookie(form.get("session_id", [""])[0])
            authed = check_auth()
            with lock:
                state["authed"] = authed
            if authed:
                threading.Thread(target=refresh, daemon=True).start()
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
        elif self.path == "/refresh":
            threading.Thread(target=refresh, daemon=True).start()
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    try:
        with open(CACHE_PATH) as f:
            state.update(json.load(f))
    except (OSError, ValueError):
        pass
    load_saved_cookie()
    threading.Thread(target=refresher, daemon=True).start()
    print(f"listening on :{PORT} for {len(FEEDS)} feeds", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
