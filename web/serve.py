#!/usr/bin/env python3
"""Local preview of the deployed site layout.

Mirrors what .github/workflows/deploy.yml assembles into build/, but serves
straight from the source folders so edits show up on reload:

  /               -> web/            (hub + shared stylesheets)
  /nhllines/...   -> nhllines/web/   (JSON falls back to nhllines/data/)
  /mlblines/...   -> mlblines/web/   (JSON falls back to mlblines/mlbdata/)
  /swingai/...    -> swingai/
  /xgcalc/...     -> xgcalc/web/
  /retired-site/  -> retired-site/   (a separate Firebase site; here for preview)
"""
import http.server, os, posixpath, socketserver, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
PORT = int(os.environ.get("PORT", 8100))

MOUNTS = [
    ("/nhllines", [os.path.join(ROOT, "nhllines", "web"), os.path.join(ROOT, "nhllines", "data")]),
    ("/mlblines", [os.path.join(ROOT, "mlblines", "web"), os.path.join(ROOT, "mlblines", "mlbdata")]),
    ("/swingai", [os.path.join(ROOT, "swingai")]),
    ("/xgcalc", [os.path.join(ROOT, "xgcalc", "web")]),
    ("/retired-site", [os.path.join(ROOT, "retired-site")]),
]


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB, **kwargs)

    def translate_path(self, path):
        clean = urllib.parse.unquote(path.split("?", 1)[0].split("#", 1)[0])
        clean = posixpath.normpath(clean)
        for prefix, dirs in MOUNTS:
            if clean == prefix or clean.startswith(prefix + "/"):
                rel = clean[len(prefix):].strip("/") or "index.html"
                parts = rel.split("/")
                for d in dirs:
                    candidate = os.path.join(d, *parts)
                    if os.path.isfile(candidate):
                        return candidate
                return os.path.join(dirs[0], *parts)
        return super().translate_path(clean)

    def do_GET(self):
        # Firebase Hosting 301s a bare directory path to its trailing-slash form
        # (/nhllines -> /nhllines/), which is what keeps each page's relative
        # asset links working. Mirror it so click-through from the hub behaves.
        bare = self.path.split("?", 1)[0]
        if any(bare == prefix for prefix, _ in MOUNTS):
            self.send_response(301)
            self.send_header("Location", bare + "/")
            self.end_headers()
            return
        super().do_GET()

    def end_headers(self):
        # Match firebase.json: nothing is cached, so every reload is fresh.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "404" in (args[1] if len(args) > 1 else ""):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"serving site preview on http://127.0.0.1:{PORT}")
        httpd.serve_forever()
