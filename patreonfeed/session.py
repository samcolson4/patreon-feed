"""The Patreon session_id cookie. One pasted into the web page is saved in the
data volume and wins over the one in .env."""

import os

from . import config

_session_id = config.ENV_SESSION_ID


def get():
    return _session_id


def load_saved():
    global _session_id
    try:
        with open(config.COOKIE_PATH) as f:
            _session_id = f.read().strip() or _session_id
    except OSError:
        pass


def save(value):
    global _session_id
    value = value.strip().strip('"')
    if value.startswith("session_id="):
        value = value[len("session_id="):].split(";")[0]
    _session_id = value
    os.makedirs(config.DATA_DIR, exist_ok=True)
    fd = os.open(config.COOKIE_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value)
