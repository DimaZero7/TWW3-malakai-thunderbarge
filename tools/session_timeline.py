"""The phases of one game session with their times: <run>/timeline.txt, so a change to the start is measured, not guessed.

  py -3.14 tools/session_timeline.py RUN_DIR      the timeline of a finished run again (what the run folder has)

Sources, merged by time: the harness's own marks (tools/crew_cycle.py Session.mark: the launch, the main menu answering,
start_campaign sent, the first tick, the map ready, every mode reached, the stop, the game gone), window.log (the window
shown), the game's "timeline" lines in tww3_mtb_events.jsonl (tools/tests/skip_intro.lua: the loading screen, each skip,
the intro's end, the player's turn ends and starts; 1 s clock) and lines of log.txt (the battle's attack and dismiss,
the turn ends). Older runs have no marks and no game lines: then only window.log and log.txt are used.
"""
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

LOG_MARKS = [            # (pattern on a log.txt line after its time, the name in the timeline)
    (r"^run ", "run folder"),
    (r"^1$", "start_campaign answered (log.txt)"),
    (r"^peace ", "peace with everyone (the map was ready)"),
    (r"^clicked button_attack", "battle: attack clicked"),
    (r"^clicked button_dismiss_results", "battle: results dismissed"),
    (r"^clicked button_dismiss ", "back on the map: post-battle panel dismissed"),
    (r"^turn \{", "turn end by script"),
    (r"^=== step ", None),          # the step's own title, shortened
    (r"^ERROR", "ERROR"),
]


class Timeline:
    def __init__(self):
        self.marks = []          # (epoch, what)

    def mark(self, what):
        self.marks.append((time.time(), what))


def _clock(base, hms):
    """HH:MM:SS of the run's day as epoch; a time before the start by more than an hour is the next day."""
    h, m, s = (int(x) for x in hms.split(":"))
    day = datetime.fromtimestamp(base).replace(hour=h, minute=m, second=s, microsecond=0)
    if day.timestamp() < base - 3600:
        day += timedelta(days=1)
    return day.timestamp()


def collect(run, marks=(), started=None):
    """[(epoch, source, what)] of the run folder plus the harness's marks."""
    run = Path(run)
    rows = [(t, "harness", w) for t, w in marks]
    log = run / "log.txt"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
    base = started
    if base is None:
        m = re.match(r"(\d{8}-\d{6})", run.name)
        base = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").timestamp() if m else (rows[0][0] if rows else time.time())
    for line in lines:
        m = re.match(r"^(\d\d:\d\d:\d\d) (.*)", line)
        if not m:
            continue
        for pattern, name in LOG_MARKS:
            if re.search(pattern, m.group(2)):
                rows.append((_clock(base, m.group(1)), "log.txt", name or m.group(2)[4:80]))
                break
    win = run / "window.log"
    if win.exists():
        for line in win.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^(\d\d:\d\d:\d\d)\S* window \d+ shown", line)
            if m:
                rows.append((_clock(base, m.group(1)), "window.log", "game window shown"))
                break
    events = run / "tww3_mtb_events.jsonl"
    if events.exists():
        for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("event") == "timeline":
                m = re.match(r"^(\d\d:\d\d:\d\d) (.*)", row.get("text", ""))
                if m:
                    rows.append((_clock(base, m.group(1)), "game " + row.get("mode", ""), m.group(2)))
    rows.sort(key=lambda r: r[0])
    return rows, base


def _first(rows, what, after=0):
    return next((t for t, _, w in rows if t >= after and w.startswith(what)), None)


def phases(rows, base):
    """[(name, seconds or None)] of the start and of each turn end and battle."""
    out = []
    fe = _first(rows, "frontend answers")
    sent = _first(rows, "start_campaign sent")
    tick = _first(rows, "first tick")
    ready = _first(rows, "map ready")
    for name, a, b in (("launch -> main menu answers", base, fe), ("main menu -> start_campaign sent", fe, sent),
                       ("start_campaign -> first tick (the campaign loads)", sent, tick),
                       ("first tick -> map ready (the intro)", tick, ready), ("launch -> map ready (the whole start)", base, ready)):
        out.append((name, round(b - a) if a and b else None))
    for t, src, w in rows:
        if w.startswith("turn end ") and src.startswith("game"):
            n = w.split()[-1]
            back = next((u for u, s2, w2 in rows if u >= t and s2.startswith("game") and w2.startswith("turn start ")), None)
            out.append((f"turn {n}: player's turn end -> next turn start (AI)", round(back - t) if back else None))
    for t, _, w in rows:
        if w == "battle: attack clicked":
            on = _first(rows, "mode battle", t)
            out.append(("battle: attack -> battle Lua answers (load)", round(on - t) if on else None))
        if w == "battle: results dismissed":
            back = _first(rows, "mode campaign", t)
            out.append(("battle: results dismissed -> campaign Lua answers (load)", round(back - t) if back else None))
    stop = _first(rows, "stop asked")
    gone = _first(rows, "game gone")
    out.append(("stop -> no game in tasklist", round(gone - stop) if stop and gone else None))
    return out


def write(run, marks=(), started=None, note=""):
    """Writes <run>/timeline.txt; returns its lines."""
    run = Path(run)
    rows, base = collect(run, marks, started)
    lines = [f"timeline of {run.name}: seconds from the launch ({time.strftime('%H:%M:%S', time.localtime(base))}){'; ' + note if note else ''}",
             "  phases:"]
    for name, sec in phases(rows, base):
        lines.append(f"    {name:<62} {'-' if sec is None else str(sec) + ' s'}")
    lines.append("  events (source, seconds from the launch, clock, what):")
    for t, src, w in rows:
        lines.append(f"    {src:<15} +{t - base:7.1f}  {time.strftime('%H:%M:%S', time.localtime(t))}  {w}")
    (run / "timeline.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n".join(write(sys.argv[1])))
