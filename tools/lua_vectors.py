"""The page's logic replayed on the mod's Lua, without the game (docs/design/port-to-game.md, 4.2): py -3.10 tools/lua_vectors.py [--max-diffs N] [--only TEXT]

Lua 5.1 (lupa.lua51), the modules as packed: src/tww3_mtb_ship.lua, src/tww3_mtb_crew_model.lua and the generated config out of
build/campaign/pack/tww3_mtb_campaign.pack (py -3.14 tools/build.py first), the fake game tools/tests/fake_game.lua, the driver
tools/tests/vectors_replay.lua. Replays every scenario of build/vectors (node tools/tests/vectors_export.mjs first) and compares every answer of
every step, the strings byte for byte; then the pure functions of crew_model. A mismatch prints scenario, step, action, field, expected, got.
Exit 1 on any mismatch, 0 when all agree. Also checks that the packed config is the one the vectors were made on.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import lupa.lua51 as lupa51

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import pfh5  # noqa: E402

PACK = REPO / "build" / "campaign" / "pack" / "tww3_mtb_campaign.pack"
VECTORS = REPO / "build" / "vectors"
SEP = chr(92)
FOLDER = f"script{SEP}campaign{SEP}tww3_mtb{SEP}"


def py(v):
    """A Lua value as Python: a table with keys 1..n a list, another a dict."""
    if lupa51.lua_type(v) == "table":
        keys = list(v.keys())
        if keys and all(isinstance(k, int) for k in keys) and sorted(keys) == list(range(1, len(keys) + 1)):
            return [py(v[i]) for i in range(1, len(keys) + 1)]
        return {str(k): py(x) for k, x in v.items()}
    return v


def same(a, b):
    """JSON-like equality: numbers by value, booleans apart from numbers, null the same as absent, an empty list the same as an empty object."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    if isinstance(a, (list, dict)) and isinstance(b, (list, dict)) and not a and not b:
        return True
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        a = {k: v for k, v in a.items() if v is not None}
        b = {k: v for k, v in b.items() if v is not None}
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    return a == b


def typed(v):
    """An expected answer in the form the Lua driver writes it."""
    if v is None:
        return ("z", None)
    if isinstance(v, bool):
        return ("b", v)
    if isinstance(v, (int, float)):
        return ("n", float(v))
    return ("s", v)


def unesc(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            out.append({"n": "\n", "t": "\t", "\\": "\\"}.get(s[i + 1], s[i + 1]))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def parse(text):
    got = {}
    for line in text.split("\n"):
        field, _, v = line.partition("\t")
        if v == "z":
            got[field] = ("z", None)
        elif v.startswith("b:"):
            got[field] = ("b", v == "b:true")
        elif v.startswith("n:"):
            got[field] = ("n", float(v[2:]))
        else:
            got[field] = ("s", unesc(v[2:]))
    return got


def show(t):
    return "null" if t[0] == "z" else repr(t[1])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-diffs", type=int, default=12, help="the mismatches printed (all are counted)")
    ap.add_argument("--only", default=None, help="only the scenarios whose name has this text")
    args = ap.parse_args(argv)
    if not PACK.exists():
        sys.exit(f"no pack {PACK}: py -3.14 tools/build.py first")
    meta_path = VECTORS / "meta.json"
    if not meta_path.exists():
        sys.exit("no vectors: node tools/tests/vectors_export.mjs first")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    files, _ = pfh5.read_pack(PACK.read_bytes())

    lua = lupa51.LuaRuntime(unpack_returned_tuples=True)
    if lua.eval("_VERSION") != "Lua 5.1":
        sys.exit("not Lua 5.1: " + str(lua.eval("_VERSION")))
    load = lua.eval("function(src, name) local f, e = loadstring(src, '@' .. name); if not f then error(e) end; return f() end")

    def module(name, blob=None):
        src = blob if blob is not None else files[FOLDER + name].decode("utf-8")
        return load(src, name)

    CM = module("tww3_mtb_crew_model.lua")
    Ship = module("tww3_mtb_ship.lua")
    packed = module("tww3_mtb_ship_config.lua")
    Fake = module("fake_game.lua", (REPO / "tools" / "tests" / "fake_game.lua").read_text(encoding="utf-8"))
    R = module("vectors_replay.lua", (REPO / "tools" / "tests" / "vectors_replay.lua").read_text(encoding="utf-8"))(Ship, CM, Fake)
    decode = Ship.decode

    def lua_json(v):
        return decode(json.dumps(v, ensure_ascii=False))

    # the pack's config is the one the vectors ran on
    diffs, shown = 0, 0
    if not same(py(packed), meta["config"]):
        sys.exit("the pack's ship config is not the one of build/vectors: run py -3.14 tools/build.py and node tools/tests/vectors_export.mjs again")

    def report(text):
        nonlocal diffs, shown
        diffs += 1
        if shown < args.max_diffs:
            shown += 1
            print("MISMATCH " + text)

    started = time.time()
    scenarios = steps = fields = 0
    for name in meta["files"]:
        if name == "units.json":
            continue
        for sc in json.loads((VECTORS / name).read_text(encoding="utf-8"))["scenarios"]:
            if args.only and args.only not in sc["name"]:
                continue
            scenarios += 1
            config = packed if sc["config"] == "author" else lua_json(sc["config"])
            try:
                w = R.world(config, lua_json(sc["sim"]))
            except lupa51.LuaError as e:
                report(f"[{sc['name']}] the world does not start: {e}")
                continue
            expected = {f: typed(v) for f, v in sc["obs0"].items()}

            def compare(step_no, action):
                nonlocal fields
                got = parse(R.observe(w))
                for f in sorted(set(expected) | set(got)):
                    fields += 1
                    e, g = expected.get(f, ("missing", None)), got.get(f, ("missing", None))
                    if e[0] == "missing" or g[0] == "missing":
                        report(f"[{sc['name']}] step {step_no} {action}: field {f}: expected {'(no such field)' if e[0] == 'missing' else show(e)}, got {'(no such field)' if g[0] == 'missing' else show(g)}")
                    elif e[0] != g[0] or (e[1] != g[1]):
                        report(f"[{sc['name']}] step {step_no} {action}: field {f}: expected {show(e)}, got {show(g)}")
            compare(0, "(start)")
            for i, st in enumerate(sc["steps"], 1):
                action = {k: v for k, v in st.items() if k not in ("ret", "set", "del")}
                label = json.dumps(action, ensure_ascii=False)
                try:
                    ret = R.apply(w, lua_json(action))
                except lupa51.LuaError as e:
                    report(f"[{sc['name']}] step {i} {label}: the Lua failed: {e}")
                    break
                steps += 1
                fields += 1
                if ret != st["ret"]:
                    report(f"[{sc['name']}] step {i} {label}: answer of the action: expected {st['ret']!r}, got {ret!r}")
                for f, v in st["set"].items():
                    expected[f] = typed(v)
                for f in st.get("del", []):
                    expected.pop(f, None)
                try:
                    compare(i, label)
                except lupa51.LuaError as e:
                    report(f"[{sc['name']}] step {i} {label}: the Lua failed while answering: {e}")
                    break

    units = 0
    R.author = packed
    if not args.only:
        for u in json.loads((VECTORS / "units.json").read_text(encoding="utf-8"))["units"]:
            units += 1
            call = {k: v for k, v in u.items() if k != "want"}
            try:
                got = py(R.unit(lua_json(call)))
            except lupa51.LuaError as e:
                report(f"[unit {u['fn']}] {json.dumps(call, ensure_ascii=False)[:200]}: the Lua failed: {e}")
                continue
            if not same(got, u["want"]):
                report(f"[unit {u['fn']}] {json.dumps(call, ensure_ascii=False)[:300]}: expected {json.dumps(u['want'], ensure_ascii=False)}, got {json.dumps(got, ensure_ascii=False)}")

    print(f"lua vectors ({lua.eval('_VERSION')}): {scenarios} scenarios, {steps} steps, {fields} answers compared, {units} unit calls, "
          f"{diffs} mismatches ({time.time() - started:.0f} s)")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
