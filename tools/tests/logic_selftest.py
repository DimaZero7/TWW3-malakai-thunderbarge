"""The expected answers of tools/tests/logic_selftest.lua, and the pieces a probe needs to ask the game for them.

    py -3.10 tools/tests/logic_selftest.py            runs the self-test on plain Lua 5.1 and on the game's emulated Lua (tools/game_lua_env.py),
                                                      fails if they differ, writes tools/tests/logic_selftest.json (name -> expected string)
    py -3.10 tools/tests/logic_selftest.py --check    the same, but compares with the JSON instead of writing it

For a probe (nothing here starts the game):
    import logic_selftest as LS
    code = LS.game_code()           # one Lua chunk: the two modules out of src/ and the self-test, inline; returns the results as one string
    ... send code to the game, get the returned string text ...
    bad = LS.compare(text)          # [(name, expected, got)]; [] when the game's Lua agrees
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tools"))
import game_lua_env as genv  # noqa: E402

SELFTEST = Path(__file__).with_suffix(".lua")
EXPECTED = Path(__file__).with_suffix(".json")
MODULES = {"CM": "tww3_mtb_crew_model.lua", "Ship": "tww3_mtb_ship.lua"}
F32_LITERALS = [16.6, 0.1, 2147483647, 16777217, 0.001, 1 / 3, 0.01, 0.0999999]      # the f32.* inputs of logic_selftest.lua, in its order


def f32_step():
    """f32.step as float32 arithmetic gives it (doubles cannot): 16777216 + 1 and 2147483648 - 1 stay where they are."""
    f = genv.f32
    return f"{int(f(f(16777217) + 1))}|{int(f(f(2147483647) - 1))}"


def game_code():
    """One chunk for the game's Lua: each module and the self-test as an inline function (no file loading needed), the results' _text returned."""
    parts = []
    for var, name in MODULES.items():
        parts.append(f"local {var} = (function()\n{(REPO / 'src' / name).read_text(encoding='utf-8')}\nend)()\n")
    parts.append(f"local T = (function()\n{SELFTEST.read_text(encoding='utf-8')}\nend)()\n")
    parts.append("return T(Ship, CM)._text\n")
    return "".join(parts)


def parse(text):
    out = {}
    for line in str(text).split("\n"):
        if "\t" in line:
            k, v = line.split("\t", 1)
            out[k] = v
    return out


def compare(text, expected=None):
    """[(name, expected, got)] for every expected answer the text does not give as expected."""
    want = expected or json.loads(EXPECTED.read_text(encoding="utf-8"))["expected"]
    got = parse(text)
    return [(k, v, got.get(k)) for k, v in want.items() if got.get(k) != v]


def run(game):
    import lupa.lua51 as l51
    if game:
        rt, _ = genv.new_runtime()
    else:
        rt = l51.LuaRuntime(unpack_returned_tuples=True)
    mods = {var: genv.load_mod(rt, (REPO / "src" / name).read_text(encoding="utf-8"), name) for var, name in MODULES.items()}
    T = genv.load_mod(rt, SELFTEST.read_text(encoding="utf-8"), SELFTEST.name)
    # the float32 values of the f32.* literals, as the game reads them
    out = parse(T(mods["Ship"], mods["CM"], rt.table_from([genv.f32(x) for x in F32_LITERALS]))._text)
    out["f32.step"] = f32_step()
    # the one chunk the game gets runs the same here (with doubles for the literals)
    same = rt.execute(game_code()) == T(mods["Ship"], mods["CM"])._text
    return out, same


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    plain, plain_chunk = run(False)
    game, game_chunk = run(True)
    bad = 0
    for k in sorted(set(plain) | set(game)):
        if plain.get(k) != game.get(k):
            bad += 1
            print(f"DIFFERS {k}: plain {plain.get(k)!r} | game env {game.get(k)!r}")
        elif plain[k].startswith("ERROR"):
            bad += 1
            print(f"ERROR {k}: {plain[k]}")
    if not (plain_chunk and game_chunk):
        bad += 1
        print("the one-chunk form (game_code) does not give the same text")
    if "--check" in argv:
        diff = compare("\n".join(f"{k}\t{v}" for k, v in game.items()))
        for k, want, got in diff:
            print(f"CHANGED {k}: expected {want!r}, got {got!r}")
        bad += len(diff)
    elif not bad:
        EXPECTED.write_text(json.dumps({"about": "tools/tests/logic_selftest.lua on plain Lua 5.1 and the game's emulated Lua (equal); "
                                        "written by py -3.10 tools/tests/logic_selftest.py", "expected": game},
                                       ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {EXPECTED}")
    print(f"logic self-test: {len(game)} answers, {bad} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
