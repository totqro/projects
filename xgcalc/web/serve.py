#!/usr/bin/env python3
"""Static server for local preview of the xgcalc pages."""
import functools, http.server, json, os, socketserver, sys, urllib.parse

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8095

os.chdir(ROOT)
SHARED = os.path.join(os.path.dirname(os.path.dirname(ROOT)), "web")  # /cyber.css lives at the site root
sys.path.insert(0, os.path.dirname(ROOT))
import nhl_game  # noqa: E402  (the NHL API has no CORS, so the tracker's import goes through here)

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if not url.path.startswith("/nhl/"):
            return super().do_GET()
        q = dict(urllib.parse.parse_qsl(url.query))
        try:
            if url.path == "/nhl/games":
                body, code = {"games": nhl_game.list_games(q["date"])}, 200
            elif url.path == "/nhl/import":
                body, code = nhl_game.build_backup(int(q["game"]), q.get("team")), 200
            else:
                body, code = {"error": "unknown NHL route"}, 404
        except (KeyError, ValueError) as e:
            body, code = {"error": str(e)}, 400
        except Exception as e:  # network trouble reaching the NHL
            body, code = {"error": f"NHL API: {e}"}, 502
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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
