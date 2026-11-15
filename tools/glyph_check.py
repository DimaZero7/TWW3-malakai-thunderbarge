"""Every string the ship panel draws uses only characters proven to draw right in the game's fonts: py -3.14 tools/glyph_check.py

Why: the game draws text with its own bitmap fonts (.cuf in local_<lang>.pack font/, chosen by ui/fontcategories.xml in ui3.pack: our text layouts
body_10 / body_12 -> la_gioconda, header_*_bold -> la_gioconda_uppercase, body_12_italic -> georgia_italic). A character the font has with a
stand-in advance draws over its neighbour: run 20261115-065150, build/qa_ingame/pass3/picker_upkeep.png «0 за ход →20» (in the Russian fonts
«→» has an advance of 8 px for 16 px of ink at size 12; about 2370 of their 2411 non-Cyrillic glyphs share that stand-in advance).

The whitelist (WHITE): printable ASCII, the Cyrillic letters, and the non-ASCII characters proven both
  * by the game's own fonts: the glyph is there and its ink stays within its advance (2 px of slack) in every size of every font above
    (checked from the game's files when the game is installed: --fonts, on by default; skipped with a note otherwise), and
  * by the game's own Russian texts or by pictures of our panel in the game: «» and — (session pictures, build/qa_ingame/pass3), … (1733 of the
    game's Russian strings; the game's own shortening of a line, text_clip_behaviour ellipsis), – (727 of them).
The no-break space (in no font file) is proven by the game's texts alone: 11757 of its Russian strings, our building descriptions among them.
Not on it: «→» (broken), «·» (it draws, but the game's Russian texts never use it: the panel writes «110, радиус 6 м»), «−», «×», «№» (none
needed), the narrow and thin spaces (not in the fonts, never in the game's texts).

What is scanned (exit 1 on any character outside the whitelist, with where it was found):
  * the answers of the page's logic in every vector scenario (build/vectors/*.json: the foot line, the reasons, the previews, the notes, ...)
  * every text and tooltip of the panel in the layout dumps (build/ui_dump/*.json: what the page and the Lua draw in the reference states)
  * the configs the game's panel draws from (build/tree/ship_ui_config.json, ship_config.json, crew_data.json: names, effects, words)
  * the string literals of the drawing and logic modules of the page and of the game (comments left out)
Run tools/build.py, node tools/tests/vectors_export.mjs and node tools/tests/ui_dump_export.mjs first (check_mod.py --vectors does).
"""
import argparse
import json
import re
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.stdout.reconfigure(encoding="utf-8")

PROVEN = "«»—–…"          # beyond ASCII and Cyrillic; see the module's doc for the proof of each
# the no-break space: in no .cuf, yet in 11757 of the game's Russian strings, the building descriptions our windows show among them (the game's own
# building browser draws the same text): the engine spaces it itself. Proven by the game's texts, not by the fonts
BY_TEXTS = "\u00a0"
WHITE = set(chr(c) for c in range(0x20, 0x7F)) | {"\n"} | set(chr(c) for c in range(0x410, 0x450)) | {"Ё", "ё"} | set(PROVEN) | set(BY_TEXTS)
FONTS = ("la_gioconda", "la_gioconda_uppercase", "georgia_italic")      # ui/fontcategories.xml for the categories of our text layouts
SLACK = 2           # px the ink may pass the advance (the font's own «» and — sit within 0)

# the modules whose literals are drawn (the page's and the game's panel, its logic, the old crew panel and its button)
# (web/js/effects_model.mjs not: its literals are the constructor's notes and a reader of the game's lines; what it makes for the panel is in the
# configs and the dumps)
SOURCES = ["web/js/panel.js", "web/js/barge_buildings.js", "web/js/crew_model.mjs", "web/js/ui_text.mjs",
           "src/tww3_mtb_ship_ui.lua", "src/tww3_mtb_ship.lua", "src/tww3_mtb_crew_model.lua", "src/tww3_mtb_ship_screen.lua", "src/tww3_mtb_crew_ui.lua",
           "src/tww3_mtb_game.lua"]
CONFIGS = ["build/tree/ship_ui_config.json", "build/tree/ship_config.json", "build/tree/crew_data.json"]


def bad_chars(s):
    return sorted({c for c in s if c not in WHITE})


def strings(v, where, out):
    if isinstance(v, str):
        if v:
            out.append((where, v))
    elif isinstance(v, dict):
        for k, x in v.items():
            strings(x, f"{where}.{k}", out)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            strings(x, f"{where}[{i}]", out)


def lua_literals(text):
    """The string literals of a Lua file, comments left out: [(line, string)]."""
    out, i, n, line = [], 0, len(text), 1
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif text.startswith("--", i):
            m = re.match(r"--\[(=*)\[", text[i:])
            if m:
                end = text.find("]" + m.group(1) + "]", i)
                end = n if end < 0 else end + 2 + len(m.group(1))
            else:
                end = text.find("\n", i)
                end = n if end < 0 else end
            line += text.count("\n", i, end)
            i = end
        elif c in "'\"":
            j, buf = i + 1, []
            while j < n and text[j] != c:
                if text[j] == "\\":
                    buf.append(text[j:j + 2])
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            out.append((line, "".join(buf)))
            i = j + 1
        elif text.startswith("[[", i) or re.match(r"\[=+\[", text[i:]):
            m = re.match(r"\[(=*)\[", text[i:])
            end = text.find("]" + m.group(1) + "]", i)
            end = n if end < 0 else end
            out.append((line, text[i + 2 + len(m.group(1)):end]))
            line += text.count("\n", i, end)
            i = end + 2 + len(m.group(1))
        else:
            i += 1
    return out


def js_literals(text):
    """The string and template literals of a JS file, comments and regular expressions left out: [(line, string)]."""
    out, i, n, line = [], 0, len(text), 1
    prev = ""           # the last significant character: a / after an operand divides, else starts a regular expression
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif c in " \t\r":
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i)
            end = n if end < 0 else end + 2
            line += text.count("\n", i, end)
            i = end
        elif c == "/" and (not prev or prev in "(,=:[!&|?{};+-*%<>~^" or text[max(0, i - 7):i].rstrip().endswith("return")):
            j = i + 1
            cls = False
            while j < n and (text[j] != "/" or cls) and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                    continue
                cls = (cls or text[j] == "[") and text[j] != "]"
                j += 1
            i = j + 1
            prev = "a"
        elif c in "'\"`":
            j, buf = i + 1, []
            while j < n and text[j] != c:
                if text[j] == "\\":
                    buf.append(text[j:j + 2])
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            s = "".join(buf)
            out.append((line, s))
            line += s.count("\n")
            i = j + 1
            prev = "a"
        else:
            prev = c if not (c.isalnum() or c in "_$)]") else "a"
            i += 1
    return out


def prove_fonts():
    """Each whitelisted character beyond ASCII and Cyrillic in every size of our fonts in the game's Russian pack: there, and its ink within its
    advance. -> (list of failures, note)"""
    try:
        from gamepack import DATA, entries
    except Exception as e:      # the reader needs Python 3.14 (compression.zstd)
        return [], f"the game's fonts not read ({e})"
    pack = DATA / "local_ru.pack"
    if not pack.exists():
        return [], f"the game's fonts not checked: {pack} not found"
    want = lambda name: name.replace("\\", "/").lower().startswith("font/") and name.lower().endswith(".cuf")
    files = {}
    for name, data in entries(pack, want):
        stem = Path(name.replace("\\", "/")).stem.lower()
        family = stem.rsplit("_", 1)[0] if stem.rsplit("_", 1)[-1].isdigit() else stem
        if family in FONTS:
            files[stem] = data
    fails, seen, odd = [], set(), set()
    for stem, d in sorted(files.items()):
        if d[:4] != b"CUF0":
            fails.append(f"{stem}: not a CUF font")
            continue
        n = struct.unpack_from("<14H", d, 4)[11]
        cmap = struct.unpack_from("<65536H", d, 0x20)
        base = 0x20 + 131072
        offs = struct.unpack_from(f"<{n}I", d, base + 5 * n)
        bitmaps = base + 5 * n + 4 * n
        seen.add(stem.rsplit("_", 1)[0] if stem.rsplit("_", 1)[-1].isdigit() else stem)
        for ch in PROVEN:
            g = cmap[ord(ch)]
            if g == 0xFFFF:
                fails.append(f"{stem}: no glyph for {ch!r} U+{ord(ch):04X}")
                continue
            top, left, w, h, adv = struct.unpack_from("<bbBBB", d, base + 5 * g)
            if bitmaps + offs[g] + w * h > len(d):
                odd.add(stem)       # a file of another layout of the format (georgia_italic_22): not ours to judge
                break
            bm = d[bitmaps + offs[g]:bitmaps + offs[g] + w * h]
            cols = [i for i in range(w) if any(bm[r * w + i] > 60 for r in range(h))]
            if cols and (cols[-1] + left + 1 > adv + SLACK or cols[0] + left < -SLACK):
                fails.append(f"{stem}: {ch!r} U+{ord(ch):04X} draws past its advance (ink {cols[0] + left}..{cols[-1] + left + 1}, advance {adv})")
    missing = [f for f in FONTS if f not in seen]
    note = (f"the game's fonts: {len(files) - len(odd)} files of {', '.join(sorted(seen))} checked for {' '.join(PROVEN)}"
            + (f" ({', '.join(sorted(odd))}: another layout of the format, not read)" if odd else ""))
    if missing:
        fails.append(f"no font file of {', '.join(missing)} in {pack.name}")
    return fails, note


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-fonts", action="store_true", help="do not read the game's fonts (the whitelist's proof)")
    ap.add_argument("--max", type=int, default=20, help="the findings printed (all are counted)")
    args = ap.parse_args()
    found = []          # (where, the string, its bad characters)
    counted = {"vectors": 0, "dumps": 0, "configs": 0, "literals": 0}

    def look(kind, where, s):
        counted[kind] += 1
        bad = bad_chars(s)
        if bad:
            found.append((where, s, bad))

    vec = sorted((REPO / "build" / "vectors").glob("*.json"))
    if not vec:
        print("no build/vectors: run node tools/tests/vectors_export.mjs first")
        return 1
    for f in vec:
        out = []
        strings(json.loads(f.read_text(encoding="utf-8")), f.stem, out)
        seen = set()
        for where, s in out:
            if s not in seen:
                seen.add(s)
                look("vectors", where, s)
    dumps = sorted((REPO / "build" / "ui_dump").glob("*.json"))
    for f in dumps:
        if f.name == "index.json":
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        for r in d.get("components") or []:
            for k in ("text", "tooltip"):
                if r.get(k):
                    look("dumps", f"{f.stem}: {r['path']} {k}", r[k])
    for rel in CONFIGS:
        p = REPO / rel
        if not p.exists():
            print(f"no {rel}: run py -3.14 tools/build.py first")
            return 1
        out = []
        strings(json.loads(p.read_text(encoding="utf-8")), rel, out)
        for where, s in out:
            look("configs", where, s)
    for rel in SOURCES:
        text = (REPO / rel).read_text(encoding="utf-8")
        lits = lua_literals(text) if rel.endswith(".lua") else js_literals(text)
        for line, s in lits:
            look("literals", f"{rel}:{line}", s)
    fails, note = ([], "the game's fonts not read (--no-fonts)") if args.no_fonts else prove_fonts()
    print(f"glyphs: {counted['vectors']} vector answers, {counted['dumps']} texts of {len(dumps)} dumps, {counted['configs']} config strings, "
          f"{counted['literals']} literals of {len(SOURCES)} modules; whitelist: ASCII, Cyrillic, {' '.join(PROVEN)}, the no-break space")
    print(note)
    for f in fails:
        print("FONT", f)
    by = {}
    for where, s, bad in found:
        by.setdefault(tuple(bad), []).append((where, s))
    for bad, rows in by.items():
        print(f"OUTSIDE {' '.join(f'{c!r} U+{ord(c):04X}' for c in bad)}: {len(rows)} strings")
        for where, s in rows[:args.max]:
            print(f"  {where}: {s[:160]!r}")
    if found or fails:
        print(f"FAIL: {len(found)} strings with characters outside the whitelist, {len(fails)} font failures")
        return 1
    print("ok: every drawn string within the whitelist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
