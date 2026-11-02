"""Opens the built pack in RPFM 5.3.3 (tools_ext/rpfm/rpfm_server.exe, its MCP interface) and lists what RPFM reads.
py -3.14 tools/rpfm_check.py [--campaign] [--tools] [--update-schemas]   --tools only prints the server's tool list.
"""
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SERVER = REPO / "tools_ext" / "rpfm" / "rpfm_server.exe"
PACK = REPO / "build" / "v1" / "pack" / "tww3_mtb_v1.pack"
if "--campaign" in sys.argv:
    PACK = REPO / "build" / "campaign" / "pack" / "tww3_mtb_campaign.pack"
URL = "http://127.0.0.1:45127/mcp"


class Mcp:
    def __init__(self):
        self.session = None
        self.next_id = 1

    def post(self, method, params=None, notify=False):
        body = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if not notify:
            body["id"] = self.next_id
            self.next_id += 1
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        request = urllib.request.Request(URL, json.dumps(body).encode(), headers)
        with urllib.request.urlopen(request, timeout=120) as response:
            self.session = response.headers.get("Mcp-Session-Id", self.session)
            raw = response.read().decode("utf-8", "replace")
        if notify:
            return None
        for line in raw.splitlines():
            if line.startswith("data:") and line[5:].strip():
                return json.loads(line[5:])
        return json.loads(raw)


def main():
    if not SERVER.exists():
        raise SystemExit("RPFM is not installed in tools_ext/rpfm")
    server = subprocess.Popen([str(SERVER)], cwd=SERVER.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        mcp = Mcp()
        for _ in range(30):
            try:
                result = mcp.post("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                                 "clientInfo": {"name": "tww3_mtb", "version": "1"}})
                break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.5)
        else:
            raise SystemExit("the server did not answer")
        print("server:", json.dumps(result.get("result", result).get("serverInfo")))
        mcp.post("notifications/initialized", notify=True)
        tools = mcp.post("tools/list")["result"]["tools"]
        names = {t["name"]: t for t in tools}
        print(len(names), "tools")
        if "--tools" in sys.argv:
            for name, tool in names.items():
                print(name, json.dumps(tool.get("inputSchema", {}).get("properties", {}))[:150])
            return

        def call(name, **arguments):
            answer = mcp.post("tools/call", {"name": name, "arguments": arguments})
            if "error" in answer:
                raise SystemExit(f"{name}: {answer['error']}")
            text = "".join(c.get("text", "") for c in answer["result"].get("content", []))
            if answer["result"].get("isError"):
                raise SystemExit(f"{name}: {text[:400]}")
            return text
        print(call("set_game", game="warhammer_3", rebuild_dependencies=False)[:260])
        if "--update-schemas" in sys.argv:
            state = json.loads(call("update_schemas"))
            while state.get("state") not in ("finished", "failed", "cancelled"):
                state = json.loads(call("wait_for_job", job=state["job"]))
            print("update_schemas:", json.dumps(state, ensure_ascii=False)[:300])
        opened = call("open_pack", paths=[str(PACK)])
        print("open_pack:", opened[:300])
        key = json.loads(opened)
        key = key.get("key") or key.get("pack") or key.get("pack_key") or key["packs"][0]["key"] if isinstance(key, dict) else key
        print("pack key:", key)
        source = {"pack": key}
        listing = call("list_files", source=source)
        print("list_files:", listing[:1500])
        sep = chr(92)
        paths = [f["path"] for f in json.loads(listing)["files"] if f["path"].startswith("db/")]
        for path in paths:
            info = call("table_info", file={"source": source, "path": path})
            print(path, re.search(r'"row_count":\s*(\d+)', info).group(0) if re.search(r'"row_count":\s*(\d+)', info) else info[-80:])
        rows = call("table_rows", file={"source": source, "path": "db/land_units_tables/!tww3_mtb"},
                    columns=["key", "class", "man_entity", "man_animation", "mount", "num_mounts", "attribute_group"])
        print("land_units:", rows[:500])
        rows = call("table_rows", file={"source": source, "path": "db/main_units_tables/!tww3_mtb"},
                    columns=["unit", "caste", "num_men", "land_unit", "porthole_composite_scene"])
        print("main_units:", rows[:400])
    finally:
        server.terminate()
        server.wait(timeout=20)


if __name__ == "__main__":
    main()
