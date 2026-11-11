"""The local web page of the airship screen: py -3.14 tools/web_serve.py [--port 8765] [--export]

Serves, on 127.0.0.1 only:
  /            web/            our code, layout and pictures
  /build/      build/web/      what tools/web_export.py took from the game and the mod's build (models, textures, the game's UI pictures, data.json, three.js)
  /mod/ui/     data/ui/        the mod's own panel pictures and building icons, read in place
and the constructor's file of the tree of buildings (web/js/constructor.js), the only file the page writes:
  POST /api/tree_design          the body (the file's JSON text) becomes web/data/tree_design.json, written atomically
  POST /api/tree_design/backup   a copy of that file beside it, web/data/tree_design.backup-<time>.json (the last 20 kept); answers {"name"}
  GET  /api/tree_icons           the building icons of the mod and of the game's export, and the effect icons, as pack paths
Runs tools/web_export.py first when build/web is missing (or with --export), and tools/web_art.py when web/art is missing. Stop with Ctrl+C.
"""
import argparse
import http.server
import json
import os
import tempfile
import time
import subprocess
import sys
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TREE_FILE = REPO / "web" / "data" / "tree_design.json"
MAX_BODY = 8 * 1024 * 1024
ROOTS = [("/build/", REPO / "build" / "web"), ("/mod/ui/", REPO / "data" / "ui"), ("/", REPO / "web")]


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".mjs": "text/javascript",
                      ".gltf": "model/gltf+json", ".bin": "application/octet-stream", ".json": "application/json"}

    def translate_path(self, path):
        path = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
        for prefix, folder in ROOTS:
            if path.startswith(prefix):
                rel = path[len(prefix):]
                target = (folder / rel).resolve()
                if target != folder.resolve() and folder.resolve() not in target.parents:
                    return str(folder / "__outside__")
                return str(target)
        return str(REPO / "web" / "__none__")

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")      # a new export shows at once
        super().end_headers()

    # ---- the constructor's file: only from this page (same host, JSON body), only this one file ----
    def _answer(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _local(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        origin = self.headers.get("Origin")
        ok_origin = origin is None or urllib.parse.urlsplit(origin).hostname in ("127.0.0.1", "localhost")
        return host in ("127.0.0.1", "localhost") and ok_origin

    def do_GET(self):
        if urllib.parse.urlsplit(self.path).path == "/api/tree_icons":
            def listed(folder, prefix):
                return sorted(prefix + f.name for f in folder.glob("*.png") if f.name != "contact-sheet.png") if folder.exists() else []
            return self._answer(200, {
                "buildings": listed(REPO / "data" / "ui" / "buildings", "ui/buildings/icons/tww3_mtb_")
                + listed(REPO / "build" / "web" / "game" / "ui" / "buildings" / "icons", "ui/buildings/icons/"),
                "effects": listed(REPO / "build" / "web" / "game" / "ui" / "campaign ui" / "effect_bundles", "ui/campaign ui/effect_bundles/")})
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if not self._local():
            return self._answer(403, {"error": "only from this page"})
        if path == "/api/tree_design/backup":
            if not TREE_FILE.exists():
                return self._answer(200, {"name": None})
            name = f"tree_design.backup-{time.strftime('%Y%m%d-%H%M%S')}.json"
            target = TREE_FILE.with_name(name)
            target.write_bytes(TREE_FILE.read_bytes())
            for old in sorted(TREE_FILE.parent.glob("tree_design.backup-*.json"))[:-20]:
                old.unlink()
            return self._answer(200, {"name": name})
        if path != "/api/tree_design":
            return self._answer(404, {"error": "no such address"})
        if "json" not in (self.headers.get("Content-Type") or ""):
            return self._answer(415, {"error": "JSON only"})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            return self._answer(413, {"error": "empty or too large"})
        text = self.rfile.read(n).decode("utf-8")
        try:
            data = json.loads(text)
        except ValueError as e:
            return self._answer(400, {"error": f"not JSON: {e}"})
        if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
            return self._answer(400, {"error": "no list of nodes"})
        if not text.endswith("\n"):
            text += "\n"
        fd, tmp = tempfile.mkstemp(prefix=".tree_design.", suffix=".tmp", dir=TREE_FILE.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            os.replace(tmp, TREE_FILE)
        except OSError as e:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            return self._answer(500, {"error": str(e)})
        return self._answer(200, {"ok": True, "bytes": len(text.encode("utf-8")), "nodes": len(data["nodes"])})

    def log_message(self, fmt, *args):
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--export", action="store_true", help="run tools/web_export.py again")
    a = ap.parse_args()
    if a.export or not (REPO / "build" / "web" / "manifest.json").exists():
        subprocess.run([sys.executable, str(REPO / "tools" / "web_export.py")], check=True)
    if not (REPO / "web" / "art" / "layers.json").exists():
        subprocess.run(["py", "-3.10", str(REPO / "tools" / "web_art.py")], check=True)
    # a page asks for many pictures at once: a long queue of connections, so none is refused while the others are served
    http.server.ThreadingHTTPServer.request_queue_size = 128
    server = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"http://127.0.0.1:{a.port}/  (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
