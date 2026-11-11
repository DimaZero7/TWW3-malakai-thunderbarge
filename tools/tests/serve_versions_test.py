"""The versions of the tree's file in tools/web_serve.py: py -3.14 tools/tests/serve_versions_test.py
A server of its own (port 8768, a file in the temp folder): a write on the current version passes, one on an old version is refused with the file as
it is, and a page older than versions (no base) is merged building by building with what was written since its last write, so it never takes back
a change made from outside; a building changed on both sides keeps the file's state and the page's text goes to a copy. Prints a line a check."""
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PORT = 8768
URL = f"http://127.0.0.1:{PORT}"
failed = 0


def check(name, ok, extra=""):
    global failed
    failed += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {extra}"))


def tree(**notes):
    return {"format": 2, "nodes": [{"id": k, "name": k, "note": v, "requires": []} for k, v in notes.items()]}


def post(body, base=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(URL + "/api/tree_design" + (f"?base={base}" if base else ""), data=data, method="POST",
                                 headers={"Content-Type": "application/json", "Origin": URL})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get():
    with urllib.request.urlopen(URL + "/data/tree_design.json") as r:
        return r.headers.get("X-Tree-Version"), json.loads(r.read())


folder = Path(tempfile.mkdtemp(prefix="mtb_versions_"))
file = folder / "tree_design.json"
file.write_text(json.dumps(tree(a="0", b="0"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
server = subprocess.Popen([sys.executable, str(REPO / "tools" / "web_serve.py"), "--port", str(PORT), "--tree", str(file)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(50):
        try:
            get()
            break
        except OSError:
            time.sleep(0.2)
    v0, _ = get()
    code, j = post(tree(a="0", b="outside"), v0)
    check("a write on the current version passes and gives the new version", code == 200 and j["version"] != v0, j)
    code, j = post(tree(a="stale", b="0"), v0)
    check("a write on an old version: 409, the file as it is, nothing written", code == 409 and json.loads(j["text"])["nodes"][1]["note"] == "outside" and get()[1]["nodes"][0]["note"] == "0", j)
    # a page older than versions: it last saw a=0, b=0 (the file at the server's start); it changes a; b was changed from outside since
    code, j = post(tree(a="old page", b="0"))
    now = get()[1]
    check("an old page's write is merged: its change in, the change from outside kept", code == 200 and now["nodes"][0]["note"] == "old page" and now["nodes"][1]["note"] == "outside", (code, j, now))
    code, j = post(tree(a="old page again", b="0"))
    now = get()[1]
    check("its next write too: the outside change is never taken back", now["nodes"][0]["note"] == "old page again" and now["nodes"][1]["note"] == "outside", now)
    v, _ = get()
    post(tree(a="outside 2", b="outside"), v)
    code, j = post(tree(a="page clash", b="0"))
    now = get()[1]
    copies = list(folder.glob("tree_design.page-*.json"))
    check("the same building changed on both sides: the file's kept, the page's text in a copy, the page told (409)",
          code == 409 and now["nodes"][0]["note"] == "outside 2" and copies and "page clash" in copies[0].read_text(encoding="utf-8"), (code, j, now))
finally:
    server.kill()
print(f"failed: {failed}")
sys.exit(1 if failed else 0)
