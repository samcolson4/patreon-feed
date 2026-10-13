"""Settings read from environment variables (see README)."""

import os
import re


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


def env_secret(name):
    path = os.environ.get(name + "_FILE")
    if path and os.path.exists(path):
        return open(path).read().strip()
    return os.environ.get(name, "").strip()


FEEDS = parse_feeds(os.environ.get("FEEDS") or os.environ.get("CREATORS", ""))
ENV_SESSION_ID = env_secret("PATREON_SESSION_ID")
REFRESH_MINUTES = int(os.environ.get("REFRESH_MINUTES", "30"))
POSTS_PER_FEED = int(os.environ.get("POSTS_PER_FEED") or os.environ.get("POSTS_PER_CREATOR") or "40")
DATA_DIR = os.environ.get("DATA_DIR", "/data")
PORT = int(os.environ.get("PORT", "8000"))
CACHE_PATH = os.path.join(DATA_DIR, "cache.json")
COOKIE_PATH = os.path.join(DATA_DIR, "session_id")
