"""HTTP routes."""

import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import patreon, render, session, store

STATIC_TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}
STATIC = {f"/static/{p.name}": (p.read_bytes(), STATIC_TYPES[p.suffix])
          for p in (Path(__file__).parent / "static").iterdir() if p.suffix in STATIC_TYPES}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self.send_body(render.page(store.snapshot()).encode(), "text/html; charset=utf-8")
        elif path == "/healthz":
            self.send_body(b"ok", "text/plain")
        elif path in STATIC:
            self.send_body(*STATIC[path])
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/cookie":
            length = int(self.headers.get("Content-Length") or 0)
            form = urllib.parse.parse_qs(self.rfile.read(length).decode())
            session.save(form.get("session_id", [""])[0])
            authed = patreon.check_auth()
            store.set_authed(authed)
            if authed:
                store.refresh_in_background()
            self.redirect_home()
        elif self.path == "/refresh":
            store.refresh_in_background()
            self.redirect_home()
        else:
            self.send_error(404)

    def send_body(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect_home(self):
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def log_message(self, *args):
        pass


def serve(port):
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
