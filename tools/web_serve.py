"""The local web page of the airship screen: py -3.14 tools/web_serve.py [--port 8765] [--export]

Serves, on 127.0.0.1 only:
  /            web/            our code, layout and pictures
  /build/      build/web/      what tools/web_export.py took from the game and the mod's build (models, textures, the game's UI pictures, data.json, three.js)
  /mod/ui/     data/ui/        the mod's own panel pictures and building icons, read in place
and the constructor's file of the tree of buildings (web/js/constructor.js), the only file the page writes. Every state of the file has a version
(the first 16 hex of the SHA-256 of its bytes), so a page that has an old state cannot write over a newer one:
  GET  /data/tree_design.json    the file, its version in the header X-Tree-Version
  GET  /api/tree_design/version  {"version"}: what the open constructor asks every two seconds to see a change made from outside
  POST /api/tree_design?base=V   the body (the file's JSON text) becomes web/data/tree_design.json, written atomically, when the file on disk is still
                                 version V; otherwise nothing is written and the answer is 409 {"error": "conflict", "version", "text"}: the file as it is now.
                                 Without base (a page of the constructor older than versions): the change is merged building by building with what was
                                 written since that page's last write (merge3); a building changed on both sides keeps the file's state, the page's text
                                 goes to a copy beside the file (tree_design.page-<time>.json), and the answer is 409 saying so
  POST /api/tree_design/backup   a copy of that file beside it, web/data/tree_design.backup-<time>.json (the last 20 kept); answers {"name"}. A body with
                                 nodes: that tree is the copy (-page in the name), a state of a page that is not written
  GET  /api/tree_icons           the building icons of the mod and of the game's export, and the effect icons, as pack paths
--tree <file>: the page reads and writes that file in place of web/data/tree_design.json (tools/tests/constructor_walk.mjs runs its own server so).
Runs tools/web_export.py first when build/web is missing (or with --export), and tools/web_art.py when web/art is missing. Stop with Ctrl+C.
"""
import argparse
import hashlib
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
# the text the pages without versions last saw: what they last wrote, or the file when the server started (merge3's base for them)
LEGACY_BASE = {"text": None}
MAX_BODY = 8 * 1024 * 1024
ROOTS = [("/build/", REPO / "build" / "web"), ("/mod/ui/", REPO / "data" / "ui"), ("/", REPO / "web")]


def version_of(blob):
    return hashlib.sha256(blob).hexdigest()[:16]


def current():
    """(bytes, version) of the tree's file now; (b"", "none") when there is none."""
    blob = TREE_FILE.read_bytes() if TREE_FILE.exists() else b""
    return blob, version_of(blob) if blob else "none"


def write_tree(text):
    fd, tmp = tempfile.mkstemp(prefix=".tree_design.", suffix=".tmp", dir=TREE_FILE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, TREE_FILE)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def merge3(base, theirs, mine):
    """Building by building: (merged nodes, [ids changed on both sides]). base, theirs, mine: the files' dicts. A building changed only in mine takes
    mine; only in theirs, theirs; on both (and differently), theirs, its id listed. A building added on one side comes in; one deleted on a side where the
    other did not change it goes. The order: theirs, then what only mine added."""
    def key(d):
        return {n.get("id"): n for n in d.get("nodes", []) if isinstance(n, dict)}
    b, t, m = key(base), key(theirs), key(mine)

    def same(x, y):
        return json.dumps(x, sort_keys=True, ensure_ascii=False) == json.dumps(y, sort_keys=True, ensure_ascii=False)
    out, clashes = [], []
    for i in list(t) + [i for i in m if i not in t]:
        if i in t and i in m:
            if same(t[i], m[i]) or (i in b and same(m[i], b[i])):
                out.append(t[i])
            elif i in b and same(t[i], b[i]):
                out.append(m[i])
            else:
                out.append(t[i])
                clashes.append(i)
        elif i in t:            # not in mine: deleted there, or added in theirs
            if i in b and same(t[i], b[i]):
                continue
            if i in b:
                clashes.append(i)
            out.append(t[i])
        else:                   # only in mine: added there, or deleted in theirs
            if i in b and same(m[i], b[i]):
                continue
            if i in b:
                clashes.append(i)
            out.append(m[i])
    return out, clashes


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".mjs": "text/javascript",
                      ".gltf": "model/gltf+json", ".bin": "application/octet-stream", ".json": "application/json"}

    def translate_path(self, path):
        path = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
        if path == "/data/tree_design.json":
            return str(TREE_FILE)          # the tree's file, also when --tree points elsewhere
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
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/tree_design/version":
            return self._answer(200, {"version": current()[1]})
        if path == "/data/tree_design.json":
            blob, version = current()
            if not blob:
                return self._answer(404, {"error": "no file"})
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("X-Tree-Version", version)
            self.end_headers()
            self.wfile.write(blob)
            return None
        if path == "/api/tree_icons":
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
            # the body a tree (a state of the page that is not written: the side not chosen in a conflict): that; otherwise the file on disk
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n).decode("utf-8") if 0 < n <= MAX_BODY else ""
            try:
                given = json.loads(body) if body else None
            except ValueError:
                given = None
            own = isinstance(given, dict) and isinstance(given.get("nodes"), list)
            if not own and not TREE_FILE.exists():
                return self._answer(200, {"name": None})
            stamp = time.strftime('%Y%m%d-%H%M%S')
            name = f"tree_design.backup-{stamp}{'-page' if own else ''}.json"
            k = 2
            while TREE_FILE.with_name(name).exists():
                name = f"tree_design.backup-{stamp}{'-page' if own else ''}-{k}.json"
                k += 1
            target = TREE_FILE.with_name(name)
            if own:
                target.write_text(body, encoding="utf-8")
            else:
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
        base = (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("base") or [None])[0]
        page_text = text          # what the page has: the base of its next write when it has no versions
        blob, version = current()
        merged, clashes = False, []
        if base is not None and base != version:
            # an old state: nothing is written, the page gets the file as it is now
            return self._answer(409, {"error": "conflict", "version": version, "text": blob.decode("utf-8")})
        if base is None and blob and LEGACY_BASE["text"] is not None and blob.decode("utf-8") != LEGACY_BASE["text"]:
            # a page without versions over a file changed since it last wrote: building by building
            try:
                theirs, old = json.loads(blob.decode("utf-8")), json.loads(LEGACY_BASE["text"])
            except ValueError:
                theirs = old = None
            if isinstance(theirs, dict) and isinstance(theirs.get("nodes"), list):
                nodes, clashes = merge3(old, theirs, data)
                if clashes:
                    name = f"tree_design.page-{time.strftime('%Y%m%d-%H%M%S')}.json"
                    TREE_FILE.with_name(name).write_text(text, encoding="utf-8")
                # the newer format's file stays in its format: its own text with the nodes merged
                out = dict(theirs, nodes=nodes) if int(theirs.get("format") or 1) >= int(data.get("format") or 1) else dict(data, nodes=nodes)
                text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
                merged = True
        try:
            write_tree(text)
        except OSError as e:
            return self._answer(500, {"error": str(e)})
        if base is None:
            LEGACY_BASE["text"] = page_text
        new_version = version_of(text.encode("utf-8"))
        if clashes:
            return self._answer(409, {"error": "файл изменён извне: страница устарела, обновите её (F5); её правки построек " + ", ".join(clashes)
                                      + " сохранены копией рядом с файлом", "merged": False, "version": new_version})
        return self._answer(200, {"ok": True, "bytes": len(text.encode("utf-8")), "nodes": len(json.loads(text)["nodes"]), "version": new_version, "merged": merged})

    def log_message(self, fmt, *args):
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--export", action="store_true", help="run tools/web_export.py again")
    ap.add_argument("--tree", help="another file of the tree in place of web/data/tree_design.json (the tests' own copy; its backups beside it)")
    a = ap.parse_args()
    if a.tree:
        global TREE_FILE
        TREE_FILE = Path(a.tree).resolve()
    if TREE_FILE.exists():
        LEGACY_BASE["text"] = TREE_FILE.read_text(encoding="utf-8")
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
