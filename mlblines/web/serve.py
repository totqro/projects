#!/usr/bin/env python3
"""Dev server that serves web/ files and proxies mlbdata/ JSON files."""
import os, http.server, socketserver

WEB_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(WEB_DIR), "mlbdata")

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.endswith(".json"):
            fpath = os.path.join(DATA_DIR, os.path.basename(path))
            if os.path.exists(fpath):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(fpath, "rb") as f:
                    self.wfile.write(f.read())
                return
        super().do_GET()

port = int(os.environ.get("PORT", 8091))
socketserver.TCPServer(("", port), Handler).serve_forever()
