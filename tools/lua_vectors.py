"""The page's logic replayed on the mod's Lua, without the game (docs/design/port-to-game.md, 4.2):
py -3.10 tools/lua_vectors.py [--src] [--env game|plain] [--no-f32] [--nudge K] [--max-diffs N] [--only TEXT]

Lua 5.1 (lupa.lua51) altered like the game's Lua (tools/game_lua_env.py: the game's UTF-8 string.find/sub/len, find refusing a 4th argument,
the library reduced to the census, each chunk in its own environment; --env plain: desktop Lua as it is). The modules as packed:
src/tww3_mtb_ship.lua, src/tww3_mtb_crew_model.lua (--src: out of src/) and the generated config out of build/campaign/pack/tww3_mtb_campaign.pack
(py -3.14 tools/build.py first), the fake game tools/tests/fake_game.lua, the driver tools/tests/vectors_replay.lua. Replays every scenario of
build/vectors (node tools/tests/vectors_export.mjs first) and compares every answer of every step, the strings byte for byte; then the pure
functions of crew_model. A mismatch prints scenario, step, action, field, expected, got.

Numbers as the game has them (unless --no-f32): every input number (config, sim, actions, unit calls) is rounded to float32 first, as the game's
own Lua reads them; numbers are compared as float32; and the float32 checker (game_lua_env.Float32) watches every local of the modules and of the
fake game at each return, the observed numbers, the unit results and the saved strings. A whole number beyond 2^24 anywhere, or an inexact number
in the saved state or an observed field, fails; an inexact fraction elsewhere fails unless ROUNDING below says why float32 cannot change what the
player sees there, and a value rounded half up (crew_model round) within float32 reach of the .5 edge fails. The local scan runs over the
page's tests, the first walk of each walk file and the unit calls (--deep: every scenario, about 20 times slower). --nudge K moves every fractional input K float32 steps (ulps) after the rounding: the results must not move (run with 4 and -4).
Also lints the two modules (game_lua_env.lint) and checks that every saved string re-encodes to itself (byte-exact save).
Exit 1 on any mismatch or failure, 0 when all agree. Also checks that the packed config is the one the vectors were made on.
"""
import argparse
import json
import struct
import sys
import time
from pathlib import Path

import lupa.lua51 as lupa51

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import pfh5  # noqa: E402
import game_lua_env as genv  # noqa: E402

PACK = REPO / "build" / "campaign" / "pack" / "tww3_mtb_campaign.pack"
VECTORS = REPO / "build" / "vectors"
SEP = chr(92)
FOLDER = f"script{SEP}campaign{SEP}tww3_mtb{SEP}"
MODULES = ["tww3_mtb_crew_model.lua", "tww3_mtb_ship.lua"]

# The places where float32 rounds a fraction and why that cannot change an answer: (chunk, local) -> reason. A new place fails the run until
# it is understood and listed here; the --nudge passes are the evidence for the reasons.
ROUNDING = {
    ("tww3_mtb_crew_model.lua", "round", "x"): "round(x): x is a percent or an ammo count made with fractional multipliers ((mult - 1) * 100, "
                                               "base * (1 + pct / 100)); whole after it, and the edge check (kind edge) shows when x lies within "
                                               "float32 reach of the .5 edge",
    ("tww3_mtb_crew_model.lua", "apply_pct", "v"): "apply_pct: v = base * (1 + pct / 100), rounded (to whole, to tenths for reload) before anyone reads it",
    ("tww3_mtb_crew_model.lua", "apply_pct", "(*temporary)"): "apply_pct reload: tenths (11.7) are no float32; the number is compared as float32, "
                                                              "written by num() to 6 digits (the same text from the float)",
    ("tww3_mtb_crew_model.lua", "crew_ammo", "each"): "crew_ammo: each = total / places is read only as whole-or-not and rounded (per)",
    ("unit", "", "apply_pct"): "apply_pct reload: as above",
    ("unit", "", "ammo"): "crew_ammo each: as above",
}
# Edges known and open: the page's own rule, not the port, rounds a true .5 by the error of a double; the game's float32 errs elsewhere.
# (caller chunk, text of the calling line) -> what differs. Reported on every run, not failed: the fix is the author's decision (it changes
# the page too). A float32 emulation of the same steps (struct, Python) gave the game's numbers below.
OPEN_EDGES = {
    ("tww3_mtb_crew_model.lua", "local total = round(base * (1 + (pct or 0) / 100))"):
        "crew_ammo total at an exact .5 (base * (100 + pct) / 100): page / game 1450 +5% 1523 / 1522, 1450 +15% 1667 / 1668, 210 +5% 221 / 220, "
        "210 +15% 241 / 242 (341 +50%, 143 +50% agree). Fix for both page and Lua: round(base * (100 + pct) / 100), exact in both (integers)",
    ("tww3_mtb_crew_model.lua", "if kind == 'reload' then return round(v * 10) / 10 end"):
        "apply_pct reload 16.6 +25%: truly 207.5, so the representation error decides: the game's float32 16.6 (16.6000004) gives 208 = 20.8 "
        "as the page, but 4 float32 steps lower gives 20.7 (--nudge -4). Fix: round(base * (100 + pct) / 10) / 10 on whole tenths of base",
}
SOURCES = {}


def open_edge(where):
    """The OPEN_EDGES reason for an edge site 'chunk:line fn from caller_chunk:line fn', or None."""
    if " from " not in where:
        return None
    caller = where.split(" from ", 1)[1].split(" ", 1)[0]
    if ":" not in caller:
        return None
    chunk, line = caller.rsplit(":", 1)
    text = SOURCES.get(chunk, "").split("\n")
    try:
        code = text[int(line) - 1].strip()
    except (ValueError, IndexError):
        return None
    for (c, marker), why in OPEN_EDGES.items():
        if c == chunk and code.startswith(marker):
            return why
    return None


def py(v):
    """A Lua value as Python: a table with keys 1..n a list, another a dict."""
    if lupa51.lua_type(v) == "table":
        keys = list(v.keys())
        if keys and all(isinstance(k, int) for k in keys) and sorted(keys) == list(range(1, len(keys) + 1)):
            return [py(v[i]) for i in range(1, len(keys) + 1)]
        return {str(k): py(x) for k, x in v.items()}
    return v


F32 = True      # numbers compared as float32 (main sets it)


def num_eq(a, b):
    if F32:
        return genv.f32(a) == genv.f32(b)
    return float(a) == float(b)


def same(a, b):
    """JSON-like equality: numbers by value, booleans apart from numbers, null the same as absent, an empty list the same as an empty object."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return num_eq(a, b)
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


def nudged(x, k):
    """x rounded to float32, then k float32 steps away when float32 had to round it (0.9, 1.15; a whole number or 0.5 the game holds exactly)."""
    x32 = genv.f32(x)
    if x32 is None or not k or x32 == float(x):
        return x32
    i = struct.unpack("<i", struct.pack("<f", x32))[0] + k
    return struct.unpack("<f", struct.pack("<i", i))[0]


def numbers_as_game(v, k):
    """Every number of a JSON-like value rounded to float32 (and nudged k steps): the game reads its numbers so."""
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        r = nudged(v, k)
        return int(r) if r == int(r) and abs(r) < 2 ** 53 else r
    if isinstance(v, list):
        return [numbers_as_game(x, k) for x in v]
    return {key: numbers_as_game(x, k) for key, x in v.items()}


def walk_numbers(v, path=""):
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return
    if isinstance(v, (int, float)):
        yield path, v
    elif isinstance(v, list):
        for x in v:
            yield from walk_numbers(x, path + "[]")
    elif isinstance(v, dict):
        for key, x in v.items():
            yield from walk_numbers(x, path + "." + key)


def main(argv=None):
    global F32
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-diffs", type=int, default=12, help="the mismatches printed (all are counted)")
    ap.add_argument("--only", default=None, help="only the scenarios whose name has this text")
    ap.add_argument("--src", action="store_true", help="the two modules out of src/ (the config still out of the pack)")
    ap.add_argument("--env", choices=("game", "plain"), default="game", help="game: Lua altered like the game's (default); plain: desktop Lua 5.1")
    ap.add_argument("--no-f32", action="store_true", help="doubles as desktop Lua has them: no float32 rounding of inputs, no float32 checker")
    ap.add_argument("--nudge", type=int, default=0, help="move every fractional input this many float32 steps (try 4 and -4)")
    ap.add_argument("--deep", action="store_true", help="the float32 scan of every local in every scenario (about 20 times slower: an hour); "
                    "by default it scans the page's tests, the first walk of each walk file and the unit calls")
    args = ap.parse_args(argv)
    F32 = not args.no_f32
    if not PACK.exists():
        sys.exit(f"no pack {PACK}: py -3.14 tools/build.py first")
    meta_path = VECTORS / "meta.json"
    if not meta_path.exists():
        sys.exit("no vectors: node tools/tests/vectors_export.mjs first")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    files, _ = pfh5.read_pack(PACK.read_bytes())

    if args.env == "game":
        lua, info = genv.new_runtime()
        env_text = f"game env (UTF-8 find/sub/len, find refuses a 4th argument; removed {info['removed'] or 'nothing'}; mod chunks in their own environment)"
    else:
        lua = lupa51.LuaRuntime(unpack_returned_tuples=True)
        env_text = "plain desktop Lua"
    if lua.eval("_VERSION") != "Lua 5.1":
        sys.exit("not Lua 5.1: " + str(lua.eval("_VERSION")))

    diffs, shown = 0, 0

    def report(text):
        nonlocal diffs, shown
        diffs += 1
        if shown < args.max_diffs:
            shown += 1
            print("MISMATCH " + text)

    def source(name):
        if args.src and name in MODULES:
            return (REPO / "src" / name).read_text(encoding="utf-8")
        return files[FOLDER + name].decode("utf-8")

    for name in MODULES:
        SOURCES[name] = source(name)
        for no, what in genv.lint(source(name)):
            report(f"[lint] {name}:{no}: {what}")

    def module(name, text=None):
        return genv.load_mod(lua, text if text is not None else source(name), name)

    CM = module("tww3_mtb_crew_model.lua")
    Ship = module("tww3_mtb_ship.lua")
    packed = module("tww3_mtb_ship_config.lua")
    Fake = module("fake_game.lua", (REPO / "tools" / "tests" / "fake_game.lua").read_text(encoding="utf-8"))
    R = module("vectors_replay.lua", (REPO / "tools" / "tests" / "vectors_replay.lua").read_text(encoding="utf-8"))(Ship, CM, Fake)
    decode, encode = Ship.decode, Ship.encode

    def lua_json(v):
        if F32:
            v = numbers_as_game(v, args.nudge)
        return decode(json.dumps(v, ensure_ascii=False))

    # the pack's config is the one the vectors ran on
    if not same(py(packed), meta["config"]):
        sys.exit("the pack's ship config is not the one of build/vectors: run py -3.14 tools/build.py and node tools/tests/vectors_export.mjs again")
    author = lua_json(py(packed)) if F32 else packed

    # every rounding half up of the crew's numbers goes through crew_model's round(x) (named by the line it starts on)
    round_line = next(i for i, l in enumerate(SOURCES["tww3_mtb_crew_model.lua"].splitlines(), 1) if l.startswith("local function round(x)"))
    checker = genv.Float32(lua, MODULES + ["fake_game.lua"], [f"tww3_mtb_crew_model.lua|{round_line}|x"]) if F32 else None

    def look(where, name, v):
        if checker and isinstance(v, (int, float)) and not isinstance(v, bool):
            checker.check(v, where, name)

    def check_saved(scenario, step_no):
        saved = py(R.saved_of(w))
        for key, s in (saved or {}).items():
            if s in ("", "0", "1") or not s[:1] in "{[\"":
                continue
            try:
                value = json.loads(s)
            except ValueError as e:
                report(f"[{scenario}] step {step_no}: saved {key} is not JSON: {e}: {s[:120]}")
                continue
            again = encode(decode(s))
            if again != s:
                report(f"[{scenario}] step {step_no}: saved {key} does not re-encode to itself: {s[:120]!r} -> {again[:120]!r}")
            for path, x in walk_numbers(value):
                # a whole number must be one the game holds exactly; a fraction is written to 9 significant digits, which read back the
                # game's float32 bit for bit (plain Lua reads the 9 digits as a double: only the text is the same there)
                if x == int(x) and not genv.is_f32(x):
                    report(f"[{scenario}] step {step_no}: saved {key}{path} = {x!r}: a whole number the game cannot hold exactly (above 2^24)")
                elif x != int(x) and genv.f32(x) is None:
                    report(f"[{scenario}] step {step_no}: saved {key}{path} = {x!r}: beyond float32")

    started = time.time()
    scenarios = steps = fields = scanned = 0
    for name in meta["files"]:
        if name == "units.json":
            continue
        for sc_no, sc in enumerate(json.loads((VECTORS / name).read_text(encoding="utf-8"))["scenarios"]):
            if args.only and args.only not in sc["name"]:
                continue
            scenarios += 1
            # the local scan costs: the tests of the page, the first walk of each file (or everything with --deep, or with --only)
            if checker:
                scan = args.deep or args.only or not name.startswith("walks") or sc_no == 0
                scanned += 1 if scan else 0
                checker.start() if scan else checker.stop()
            config = author if sc["config"] == "author" else lua_json(sc["config"])
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
                    if g[0] == "n":
                        look("observe", f, g[1])
                        if F32 and not genv.is_f32(g[1]):
                            report(f"[{sc['name']}] step {step_no} {action}: field {f} = {g[1]!r} is not a float32 the game can hold exactly")
                    if e[0] == "missing" or g[0] == "missing":
                        report(f"[{sc['name']}] step {step_no} {action}: field {f}: expected {'(no such field)' if e[0] == 'missing' else show(e)}, got {'(no such field)' if g[0] == 'missing' else show(g)}")
                    elif e[0] != g[0] or (not num_eq(e[1], g[1]) if e[0] == "n" else e[1] != g[1]):
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
                if action.get("do") == "reload":
                    check_saved(sc["name"], i)
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
    R.author = author
    if checker:
        checker.start()
    if not args.only:
        for u in json.loads((VECTORS / "units.json").read_text(encoding="utf-8"))["units"]:
            units += 1
            call = {k: v for k, v in u.items() if k != "want"}
            try:
                got = py(R.unit(lua_json(call)))
            except lupa51.LuaError as e:
                report(f"[unit {u['fn']}] {json.dumps(call, ensure_ascii=False)[:200]}: the Lua failed: {e}")
                continue
            for path, x in walk_numbers(got):
                look("unit", u["fn"] + path, x)
            if not same(got, u["want"]):
                report(f"[unit {u['fn']}] {json.dumps(call, ensure_ascii=False)[:300]}: expected {json.dumps(u['want'], ensure_ascii=False)}, got {json.dumps(got, ensure_ascii=False)}")
    if checker:
        checker.stop()

    f32_text = "float32 off (--no-f32)"
    if checker:
        sites = checker.sites()
        bad, rounding, open_ = [], [], []
        for kind, where, lname, count, first in sites:
            if where == "unit":
                key = ("unit", "", lname.split(".", 1)[0].split("[", 1)[0])
            elif ":" in where:
                chunk, rest = where.split(":", 1)
                key = (chunk, rest.split(" ")[1] if " " in rest else "", lname)
            else:
                key = (where, "", lname)
            line = f"{kind} {where} {lname}: {count}x, first {first!r}"
            if key not in ROUNDING and key[1] == "nil":      # a tail call has no function name: the same chunk and local
                key = next((k for k in ROUNDING if k[0] == key[0] and k[2] == key[2]), key)
            if kind == "inexact" and where not in ("saved", "observe") and key in ROUNDING:
                rounding.append(line)
            elif kind == "edge" and open_edge(where):
                open_.append(line + "\n      OPEN: " + open_edge(where))
            else:
                bad.append(line)
        for line in bad:
            report("[float32] " + line)
        f32_text = (f"float32: inputs rounded{f' and nudged {args.nudge:+d} ulps' if args.nudge else ''}; locals scanned in {scanned} scenarios and the units; "
                    f"{len(sites)} sites seen, {len(bad)} failing, "
                    f"{len(rounding)} known rounding sites, {len(open_)} OPEN edges (the page's rule differs in the game: reported, not failed)")
        for line in rounding:
            f32_text += "\n  rounding " + line
        for line in open_:
            f32_text += "\n  edge " + line
    print(f"lua vectors ({lua.eval('_VERSION')}, {env_text}): {scenarios} scenarios, {steps} steps, {fields} answers compared, {units} unit calls, "
          f"{diffs} mismatches ({time.time() - started:.0f} s)\n{f32_text}")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
