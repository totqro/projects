#!/usr/bin/env python3
"""Static server for local preview of the xgcalc pages."""
import functools, http.server, os, socketserver

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8095

os.chdir(ROOT)
SHARED = os.path.join(os.path.dirname(os.path.dirname(ROOT)), "web")  # /cyber.css lives at the site root

class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        clean = path.split("?", 1)[0]
        if clean in ("/cyber.css", "/dashboard.css"):
            return os.path.join(SHARED, clean.lstrip("/"))
        return super().translate_path(path)

handler = functools.partial(Handler, directory=ROOT)
socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", PORT), handler) as httpd:
    print(f"serving {ROOT} on http://127.0.0.1:{PORT}")
    httpd.serve_forever()
