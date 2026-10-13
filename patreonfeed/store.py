"""In-memory posts, refreshed from Patreon on a timer and cached to disk."""

import json
import os
import threading
import time
from datetime import datetime, timezone

from . import config, patreon

state = {"posts": [], "feeds": {}, "updated": None, "errors": [], "authed": None}
lock = threading.Lock()


def snapshot():
    with lock:
        return dict(state)


def set_authed(authed):
    with lock:
        state["authed"] = authed


def load_cache():
    try:
        with open(config.CACHE_PATH) as f:
            state.update(json.load(f))
    except (OSError, ValueError):
        pass


def save_cache(data):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(config.CACHE_PATH + ".tmp", "w") as f:
        json.dump(data, f)
    os.replace(config.CACHE_PATH + ".tmp", config.CACHE_PATH)


def refresh():
    feeds, posts, errors = {}, [], []
    known = snapshot()["feeds"]
    for feed in config.FEEDS:
        try:
            f = known.get(feed["key"])
            if not f or f.get("label") != feed["label"]:
                f = patreon.resolve(feed)
            feeds[feed["key"]] = f
            posts.extend(patreon.fetch_posts(f))
        except Exception as e:
            errors.append(f"{feed['label'] or feed['key']}: {e}")
    authed = patreon.check_auth()
    posts.sort(key=lambda p: p["published"] or "", reverse=True)
    with lock:
        state.update(posts=posts, feeds=feeds, errors=errors, authed=authed,
                     updated=datetime.now(timezone.utc).isoformat())
        data = dict(state)
    save_cache(data)
    print(f"refreshed: {len(posts)} posts, {len(errors)} errors", flush=True)


def refresh_in_background():
    threading.Thread(target=refresh, daemon=True).start()


def start_refresher():
    def loop():
        while True:
            try:
                refresh()
            except Exception as e:
                print("refresh failed:", e, flush=True)
            time.sleep(config.REFRESH_MINUTES * 60)
    threading.Thread(target=loop, daemon=True).start()
