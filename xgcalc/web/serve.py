#!/usr/bin/env python3
"""Static server for local preview of the xgcalc pages."""
import functools, http.server, os, socketserver

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8095

os.chdir(ROOT)
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", PORT), handler) as httpd:
    print(f"serving {ROOT} on http://127.0.0.1:{PORT}")
    httpd.serve_forever()
