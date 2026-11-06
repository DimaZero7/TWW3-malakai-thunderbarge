"""The local web page of the airship screen: py -3.14 tools/web_serve.py [--port 8765] [--export]

Serves, on 127.0.0.1 only:
  /            web/            our code, layout and pictures
  /build/      build/web/      what tools/web_export.py took from the game and the mod's build (models, textures, the game's UI pictures, data.json, three.js)
  /mod/ui/     data/ui/        the mod's own panel pictures and building icons, read in place
Runs tools/web_export.py first when build/web is missing (or with --export), and tools/web_art.py when web/art is missing. Stop with Ctrl+C.
"""
import argparse
import http.server
import subprocess
import sys
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
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
    server = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"http://127.0.0.1:{a.port}/  (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
