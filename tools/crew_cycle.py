"""The crew in real campaign battles: choose, fight, autoresolve, save, load, choose again.

  py -3.14 tools/crew_cycle.py all               everything below, in order, each session with its own hard limit
  py -3.14 tools/crew_cycle.py session NAME      one session of data/crew_cycle.json
  py -3.14 tools/crew_cycle.py report            the table of results from build/crew/cycle/results.jsonl
  --igpu             the lowest settings instead of what the session asks: the RTX is out of the machine
  --scale N          all time limits of the session times N, for a slow GPU
  --limit-scale N    only the hard limit of the session times N; fights stay as long as in earlier runs, so kills compare
  --minimized        ask Windows to start the game minimized and not active
  --set KEY=VALUE    a setting for this session only (run_game.py restores the file after it)

Sessions are in data/crew_cycle.json. Each runs through tools/run_game.py (lock, closing of the game, the user's files restored),
with memreader Plus from the Workshop folder unless the session says otherwise. Pictures only through PrintWindow.
Every battle appends one line to build/crew/cycle/results.jsonl, so an interrupted run loses nothing.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import capture  # noqa: E402
import crew_lua  # noqa: E402
import crew_session  # noqa: E402
import far_view  # noqa: E402
import rc  # noqa: E402
import run_game as rg  # noqa: E402

SPEC = json.loads((REPO / "data" / "crew_cycle.json").read_text(encoding="utf-8"))
OPTIONS = json.loads((REPO / "data" / "crew_options.json").read_text(encoding="utf-8"))
TESTS = REPO / "tools" / "tests"
OUT = REPO / "build" / "crew" / "cycle"
RESULTS = OUT / "results.jsonl"
SAVES = rg.SAVES
FIGHT_LIMIT = 150       # seconds of real time; the battle runs at speed 3
SCALE = 1.0             # --scale: every limit below is multiplied by it
LIMIT_SCALE = 1.0
IGPU = False
MINIMIZED = False
EXTRA_SETTINGS = []
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def scaled(seconds):
    return seconds * SCALE


class Session:
    def __init__(self, name, deadline):
        self.name = name
        self.deadline = deadline
        self.dir = None
        self.battle_no = 0

    def log(self, *a):
        text = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
        print(text[:400], flush=True)
        if self.dir:
            with (self.dir / "log.txt").open("a", encoding="utf-8") as f:
                f.write(text + "\n")

    def check_time(self):
        if time.time() > self.deadline:
            raise TimeoutError("hard limit of the session")

    def lua(self, code, wait=15):
        self.check_time()
        return crew_lua.run(code, scaled(wait))

    def plain(self, code, wait=15):
        self.check_time()
        return rc.send(code, scaled(wait))

    def mode(self):
        row = rc.send("return mtb.mode", 3)
        return row["result"] if row["ok"] else None

    def wait_mode(self, mode, limit=300):
        end = time.time() + scaled(limit)
        while time.time() < end:
            self.check_time()
            if self.mode() == mode:
                return
            time.sleep(2)
        raise TimeoutError(f"mode {mode} not reached in {limit} s")

    def shot(self, name):
        s = rc.state()
        capture.unminimize_behind(s["pid"])     # the user may have minimized the game: a minimized window paints nothing
        hwnd = capture.find_window(s["pid"])
        if not hwnd:
            self.log("shot", name, "no window")
            return
        capture.save_shot(hwnd, self.dir / f"{name}.png", (s["x_res"], s["y_res"]))

    def memory_mb(self):
        s = rc.state()
        out = subprocess.run(["tasklist", "/FI", f"PID eq {s['pid']}", "/FO", "CSV", "/NH"], capture_output=True, text=True, errors="replace").stdout
        digits = re.sub(r"\D", "", out.rsplit('","', 1)[-1])
        return int(digits) // 1024 if digits else None

    def sim_ms(self):
        """The battle's clock in ms."""
        row = self.plain("return bm:time_elapsed_ms()", 8)
        try:
            return float(row["result"]) if row["ok"] else None
        except (TypeError, ValueError):
            return None

    def sim_rate(self, sim_start, real_start):
        now = self.sim_ms()
        if sim_start is None or now is None:
            return None
        return round((now - sim_start) / 1000 / (time.time() - real_start), 2)

    def tick_rate(self, seconds=10):
        """How often a 1 ms real-time callback fires. It cannot fire more than once a frame, so this approximates frames per second."""
        self.plain("_G.mtb_ticks = 0; core.tm:repeat_real_callback(function() _G.mtb_ticks = _G.mtb_ticks + 1 end, 1, 'tww3_mtb_ticks'); return 1", 8)
        begin = time.time()
        time.sleep(seconds)
        row = self.plain("core.tm:remove_real_callback('tww3_mtb_ticks'); return _G.mtb_ticks", 8)
        try:
            return round(float(row["result"]) / (time.time() - begin), 1)
        except (TypeError, ValueError):
            self.log("ticks", row["result"])
            return None

    def script(self, name, **values):
        code = "".join(f'{k} = "{v}"\n' for k, v in values.items()) + (TESTS / name).read_text(encoding="utf-8")
        return self.plain(code)

    def visible(self, name):
        row = self.plain(f'local b = mtb.find("{name}", true); return b and tostring(b:CurrentState()) or "-"', 5)
        return row["result"] if row["ok"] else "-"

    def click(self, name):
        return self.plain(f'return mtb.click("{name}")', 5)["result"]

    def choose(self, choice):
        code = "".join(f'assert(tww3_mtb_crew.set("{g}", "{o}"))\n' for g, o in choice.items())
        row = self.plain(code + "return tostring(tww3_mtb_crew.status) .. ' ' .. mtb.dump(tww3_mtb_crew.get())", 15)
        self.log("choice", row["result"])
        return row

    def open_panel(self):
        time.sleep(3)
        for attempt in range(round(scaled(8))):
            if self.visible("button_attack") != "-":
                return
            self.log("blockers", self.script("dismiss_blockers.lua")["result"])
            self.log("attack", self.script("attack_nearest.lua")["result"])
            for _ in range(8):
                time.sleep(1)
                if self.visible("button_attack") != "-":
                    return
        self.shot("no_panel")
        raise TimeoutError("the pre-battle panel did not open")

    def back_on_map(self, limit=40):
        for attempt in range(round(scaled(limit))):
            if self.visible("button_end_turn") != "-":
                return True
            for name in ("button_captive_option_kill", "button_dismiss", "button_set_win", "button_continue", "button_dismiss_results", "button_accept"):
                if self.visible(name) != "-":
                    self.log(self.click(name))
                    break
            time.sleep(2)
        self.shot("not_on_map")
        return False

    def seats_ok(self, text, choice):
        """Counts the seats whose man in the battle really has the row of the chosen option."""
        groups = OPTIONS["groups"]
        lines = str(text).split("\n")
        good, bad = 0, []
        full = dict(self.current)
        full.update(choice)
        for group, option in full.items():
            opt = groups[group]["options"][option]
            for seat in groups[group]["seats"]:
                line = next((x for x in lines if f" {seat} " in x), "")
                if opt.get("empty"):
                    ok = " mtb_bp_empty " in line
                elif opt.get("stock"):
                    ok = "wh3_dlc25_dwf_veh_thunderbarge_grungni" in line or f" mtb_bp_{option}_" in line
                else:
                    ok = f" mtb_bp_{option}_" in line
                if ok:
                    good += 1
                else:
                    bad.append(seat)
        return good, bad

    def gpu_note(self):
        """Which card runs the game: the process table of nvidia-smi, written to the log."""
        try:
            out = subprocess.run(["nvidia-smi", "pmon", "-c", "1"], capture_output=True, text=True, errors="replace", timeout=30).stdout
            line = next((x for x in out.splitlines() if "warhammer" in x.lower()), "Warhammer3 is not on the NVIDIA card")
            used = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used", "--format=csv,noheader"], capture_output=True, text=True, errors="replace", timeout=30).stdout.strip()
            self.log("gpu", " ".join(line.split()), "|", used)
        except (OSError, subprocess.SubprocessError) as e:
            self.log("gpu check failed", e)

    def hold(self, seconds):
        """Waits for commands from outside (tools/rc.py, tools/far_view.py) until build/crew/cycle/CONTINUE appears."""
        flag = OUT / getattr(self, "hold_flag", "CONTINUE")
        flag.unlink(missing_ok=True)
        self.log("hold", seconds)
        end = time.time() + seconds
        while time.time() < end and not flag.exists():
            self.check_time()
            time.sleep(1)
        flag.unlink(missing_ok=True)
        self.log("hold over")

    def battle(self, spec):
        self.battle_no += 1
        label = spec["label"]
        self.log("=== battle", label, spec.get("choice"))
        if spec.get("from_game"):       # the crew the buildings chose: nothing is set by the test
            self.sync_current()
        row = self.choose(spec.get("choice", {}))
        if not row["ok"]:
            raise RuntimeError(row["result"])
        self.current.update(spec.get("choice", {}))
        result = {"session": self.name, "label": label, "choice": dict(self.current), "status": row["result"], "memory_before_mb": self.memory_mb()}
        if spec.get("expect_status"):
            result["status_ok"] = spec["expect_status"] in str(row["result"])
        units = {"mtb_units": spec["units"]} if spec.get("units") else {}
        self.log("spawn", self.script("spawn_fight.lua", **units)["result"])
        self.open_panel()
        if spec.get("autoresolve"):
            self.log(self.click("button_autoresolve"))
            time.sleep(4)
            result["back_on_map"] = self.back_on_map()
            self.shot(f"{label}_auto")
            result["kind"] = "autoresolve"
            self.save_result(result)
            return
        self.log(self.click("button_attack"))
        self.wait_mode("battle", 300)
        time.sleep(4)
        men = self.lua("return C.men()", 20)
        (self.dir / f"men_{label}.txt").write_text(str(men["result"]), encoding="utf-8")
        if spec.get("from_game"):
            (self.dir / f"read_{label}.txt").write_text(str(self.plain((TESTS / "battle_read.lua").read_text(encoding="utf-8"), 15)["result"]), encoding="utf-8")
        if men["ok"]:
            result["seats_ok"], result["seats_bad"] = self.seats_ok(men["result"], {})
            self.log("seats", result["seats_ok"], result["seats_bad"][:6])
        else:
            result["seats_ok"], result["seats_bad"] = None, ["no memory access: " + str(men["result"])[:80]]
        self.gpu_note()
        wanted = spec.get("shots", True)
        for cam in SPEC["cameras"] if wanted else []:
            if isinstance(wanted, list) and cam["name"] not in wanted:
                continue
            self.lua(f'return C.camera({cam["f"]},{cam["r"]},{cam["u"]},{cam["tf"]},{cam["tr"]},{cam["tu"]},{cam["fov"]})', 10)
            time.sleep(1.5)
            self.shot(f'{label}_{cam["name"]}')
        self.plain("bm:end_current_battle_phase(); return 1", 5)
        time.sleep(3)
        self.log("fight", self.lua((TESTS / "crew_fight.lua").read_text(encoding="utf-8"), 10)["result"])
        if "abilities" in spec:     # the unit's abilities, as the battle has them: is the harpoon there
            read = str(self.plain((TESTS / "battle_read.lua").read_text(encoding="utf-8"), 15)["result"])
            result["harpoon"] = "spear_of_grungni" in read
            result["harpoon_ok"] = result["harpoon"] == spec["abilities"]
            self.log("harpoon", result["harpoon"], "expected", spec["abilities"])
        if spec.get("burner"):      # the barge's own ability: the mission "Призыв Духа" counts it
            time.sleep(4)
            self.log("burner", self.script("battle_ability.lua")["result"])
        fired_at = None
        started = time.time()
        stats = []
        limit = scaled(spec.get("fight", FIGHT_LIMIT))
        extra = scaled(spec.get("after_fire", 12))
        sim_start = self.sim_ms()
        while time.time() - started < limit:
            time.sleep(5)
            r = self.lua("C.order(); return C.stats()", 8)
            stats.append(str(r["result"]))
            m = re.search(r"near=(\d+).*pct=([\d.]+) kills=(\d+)", str(r["result"]))
            if m and fired_at is None and (int(m.group(3)) > 0 or float(m.group(2)) < 0.9995):
                fired_at = time.time()
                self.log("fired", r["result"])
            if fired_at and time.time() - fired_at > extra:
                break
            if m and spec.get("stop_near") and int(m.group(1)) <= spec["stop_near"] and time.time() - started > scaled(60):
                break
        (self.dir / f"stats_{label}.txt").write_text("\n".join(stats), encoding="utf-8")
        self.log("end", stats[-1] if stats else "-")
        result["sim_rate"] = self.sim_rate(sim_start, started)      # battle seconds per real second; 3 is the speed asked for
        result["fight_seconds"] = round(time.time() - started)
        if spec.get("measure"):
            result["ticks_per_s"] = self.tick_rate()
        last = re.search(r"near=(\S+).*pct=([\d.]+) kills=(\d+) hp=(\S+)", stats[-1]) if stats else None
        if last:
            result.update(near=last.group(1), ammo=float(last.group(2)), kills=int(last.group(3)), hp=last.group(4))
        result["min_near"] = min((int(x) for s in stats for x in re.findall(r"near=(\d+)", s)), default=None)
        result["fired"] = fired_at is not None
        if spec.get("from_game") or spec.get("ammo_report"):
            result["ammo_report"] = str(self.plain("return tostring(tww3_mtb_ammo.status) .. ' | ' .. tww3_mtb_ammo.report()", 8)["result"])
            self.log("ammo", result["ammo_report"])
        self.shot(f"{label}_fight")
        if spec.get("late_shots"):
            self.lua("bm:modify_battle_speed(1); if _G.mtb_crew_uc then _G.mtb_crew_uc:halt() end; return 1", 8)
            time.sleep(8)
        for name in spec.get("late_shots", []):
            cam = next(c for c in SPEC["cameras"] if c["name"] == name)
            self.lua(f'return C.camera({cam["f"]},{cam["r"]},{cam["u"]},{cam["tf"]},{cam["tr"]},{cam["tu"]},{cam["fov"]})', 10)
            time.sleep(1.5)
            self.shot(f"{label}_late_{name}")
        if spec.get("far_views") or spec.get("hold"):
            self.lua("bm:modify_battle_speed(1); if _G.mtb_crew_uc then _G.mtb_crew_uc:halt() end; return 1", 8)
            time.sleep(4)
            if spec.get("far_views"):
                far_view.standard(label, spec["far_views"] if isinstance(spec["far_views"], str) else "far_views")
            if spec.get("hold"):
                self.hold(spec["hold"])
            self.lua("bm:modify_battle_speed(1); return 1", 8)
        self.log(self.script("battle_kill_enemy.lua")["result"])
        for attempt in range(round(scaled(25))):
            if self.visible("button_dismiss_results") != "-":
                break
            if attempt == round(scaled(8)):
                self.plain("bm:end_battle(); return 1", 5)
            time.sleep(3)
        self.log(self.click("button_dismiss_results"))
        self.wait_mode("campaign", 300)
        time.sleep(4)
        result["back_on_map"] = self.back_on_map()
        result["memory_after_mb"] = self.memory_mb()
        result["kind"] = "battle"
        self.save_result(result)

    def ammo_set(self, spec):
        for _ in range(20):
            status = self.plain("return tww3_mtb_ammo and tww3_mtb_ammo.status", 8)["result"]
            if status != "waiting":
                break
            time.sleep(1)
        code = "".join(f'tww3_mtb_ammo.set_ammo("{g}", {n})\n' for g, n in spec.get("ammo", {}).items())
        return self.plain(code + "return tww3_mtb_ammo.status", 8)["result"]

    def ammo_note(self, label, text):
        self.log(label, text)
        with (self.dir / f"ammo_{label}.txt").open("a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + str(text) + "\n")

    def ammo_battle(self, spec):
        """The groups run dry one by one in a real campaign battle; the module's own log and counts go to ammo_<label>.txt.
        spec: choice, ammo {group: shots}, units, wait_dry (groups, or all), watch (battle seconds after they are dry),
        refill {group: shots} and refill_watch: new ammunition, the group must fire exactly that much again."""
        label = spec["label"]
        self.log("=== ammo battle", label, spec.get("choice"), spec.get("ammo"))
        if not spec.get("expect_off"):      # without memreader Plus nothing can be chosen: the stock crew from the tables
            row = self.choose(spec.get("choice", {}))
            if not row["ok"]:
                raise RuntimeError(row["result"])
            self.current.update(spec.get("choice", {}))
        self.log("spawn", self.script("spawn_fight.lua", mtb_units=spec.get("units", "wh_main_grn_inf_goblin_spearmen,wh_main_grn_inf_goblin_spearmen,wh_main_grn_inf_goblin_archers"))["result"])
        self.open_panel()
        self.log(self.click("button_attack"))
        self.wait_mode("battle", 300)
        time.sleep(4)
        self.ammo_note(label, "status after loading: " + str(self.plain("return tww3_mtb_ammo.status", 8)["result"]))
        men = self.lua("return C.men()", 20)
        (self.dir / f"men_{label}.txt").write_text(str(men["result"]), encoding="utf-8")
        status = str(self.ammo_set(spec))
        self.ammo_note(label, "set: " + status)
        if status != "running" and not spec.get("expect_off"):     # nothing to measure: the game closes at once
            raise RuntimeError("ammunition module: " + status)
        self.plain("bm:end_current_battle_phase(); return 1", 5)
        time.sleep(3)
        self.log("fight", self.lua((TESTS / "crew_fight.lua").read_text(encoding="utf-8"), 10)["result"])
        self.log(self.lua((TESTS / "ammo_fight.lua").read_text(encoding="utf-8"), 10)["result"])
        self.log(self.plain("return _G.mtb_ammo_t.keep_enemy()", 10)["result"])
        if spec.get("speed"):
            self.plain(f'bm:modify_battle_speed({spec["speed"]}); return 1', 5)
        started = time.time()
        sim_start = self.sim_ms()
        limit = spec.get("real_limit", 420)
        groups = spec.get("wait_dry", "all")
        watch = spec.get("watch", 30)
        refilled = False
        shot_mid = False
        final = None
        while time.time() - started < limit:
            time.sleep(5)
            self.check_time()
            self.log("order", self.plain("return _G.mtb_ammo_t.order()", 8)["result"])
            self.ammo_note(label, self.plain("return _G.mtb_ammo_t.line()", 8)["result"])
            row = self.plain(f'return _G.mtb_ammo_t.dry_for("{groups}")', 8)
            try:
                dry = float(row["result"])
            except (TypeError, ValueError):
                dry = -1
            if not shot_mid and time.time() - started > 40:
                self.shot(f"{label}_mid")
                shot_mid = True
            if dry >= watch:
                if spec.get("refill") and not refilled:
                    self.ammo_note(label, f"after {dry:.0f} s dry: refill {spec['refill']}")
                    self.ammo_set({"ammo": spec["refill"]})
                    refilled = True
                    groups = ",".join(spec["refill"])
                    watch = spec.get("refill_watch", 60)
                    continue
                break
        self.shot(f"{label}_end")
        final = self.plain("return _G.mtb_ammo_t.line()", 8)["result"]
        self.ammo_note(label, "END " + str(final))
        self.ammo_note(label, "LOG " + str(self.plain("return table.concat(tww3_mtb_ammo.log_lines, ' ; ')", 8)["result"]))
        result = {"session": self.name, "label": label, "kind": "ammo", "choice": dict(self.current), "ammo": spec.get("ammo"), "report": str(final),
                  "sim_rate": self.sim_rate(sim_start, started), "seconds": round(time.time() - started), "refilled": refilled}
        self.save_result(result)
        self.log(self.plain("return _G.mtb_ammo_t.release_enemy()", 8)["result"])
        self.log(self.script("battle_kill_enemy.lua")["result"])
        for attempt in range(round(scaled(25))):
            if self.visible("button_dismiss_results") != "-":
                break
            if attempt == round(scaled(8)):
                self.plain("bm:end_battle(); return 1", 5)
            time.sleep(3)
        self.log(self.click("button_dismiss_results"))
        self.wait_mode("campaign", 300)
        time.sleep(4)
        self.log("back on map", self.back_on_map())

    def ammo_ai_battle(self, spec):
        """Malakai under the AI with little ammunition: the battle must go on, the AI must not break."""
        label = spec["label"]
        self.log("=== ammo battle under the AI", label, spec.get("choice"))
        self.log("choice", self.choose(spec.get("choice", {}))["result"])
        self.current.update(spec.get("choice", {}))
        self.log("meet", self.script("crew_ai_meet.lua")["result"])
        time.sleep(3)
        for attempt in range(round(scaled(10))):
            if self.visible("button_attack") != "-":
                break
            self.log("blockers", self.script("dismiss_blockers.lua")["result"])
            self.log("meet", self.script("crew_ai_meet.lua")["result"])
            time.sleep(6)
        else:
            self.shot("no_panel")
            raise TimeoutError("the pre-battle panel did not open")
        self.log(self.click("button_attack"))
        self.wait_mode("battle", 300)
        time.sleep(4)
        self.ammo_note(label, "status after loading: " + str(self.plain("return tww3_mtb_ammo.status", 8)["result"]))
        self.ammo_note(label, "set: " + str(self.ammo_set(spec)))
        self.plain("bm:end_current_battle_phase(); bm:modify_battle_speed(3); return 1", 5)
        time.sleep(3)
        self.log(self.lua((TESTS / "ammo_fight.lua").read_text(encoding="utf-8"), 10)["result"])
        self.log(self.plain("return _G.mtb_ammo_t.push_player()", 10)["result"])
        started = time.time()
        sim_start = self.sim_ms()
        while time.time() - started < spec.get("watch", 240):
            time.sleep(10)
            self.check_time()
            self.ammo_note(label, self.lua("local p = C.lord_unit():position(); return _G.mtb_ammo_t.line() .. string.format(' at=%d,%d,%d', p:get_x(), p:get_y(), p:get_z())", 8)["result"])
        self.shot(f"{label}_end")
        final = self.plain("return _G.mtb_ammo_t.line()", 8)["result"]
        self.ammo_note(label, "LOG " + str(self.plain("return table.concat(tww3_mtb_ammo.log_lines, ' ; ')", 8)["result"]))
        self.save_result({"session": self.name, "label": label, "kind": "ammo_ai", "report": str(final), "sim_rate": self.sim_rate(sim_start, started)})

    def ai_battle(self, spec):
        """Malakai under the game's AI attacks the player's army; nobody orders his unit. Returns when the time is over."""
        label = spec["label"]
        self.log("=== AI battle", label, spec.get("choice"))
        self.log("choice", self.choose(spec.get("choice", {}))["result"])
        self.log("meet", self.script("crew_ai_meet.lua")["result"])
        time.sleep(3)
        for attempt in range(round(scaled(10))):
            if self.visible("button_attack") != "-":
                break
            self.log("blockers", self.script("dismiss_blockers.lua")["result"])
            self.log("meet", self.script("crew_ai_meet.lua")["result"])
            time.sleep(6)
        else:
            self.shot("no_panel")
            raise TimeoutError("the pre-battle panel did not open")
        self.shot(f"{label}_panel")
        self.log(self.click("button_attack"))
        self.wait_mode("battle", 300)
        time.sleep(4)
        men = self.lua("return C.men()", 20)
        (self.dir / f"men_{label}.txt").write_text(str(men["result"]), encoding="utf-8")
        self.current.update(spec.get("choice", {}))
        result = {"session": self.name, "label": label, "kind": "ai_battle", "choice": dict(self.current)}
        result["seats_ok"], result["seats_bad"] = self.seats_ok(men["result"], {})
        self.plain("bm:end_current_battle_phase(); bm:modify_battle_speed(3); return 1", 5)
        started = time.time()
        stats = []
        sim_start = self.sim_ms()
        while time.time() - started < scaled(spec.get("watch", 150)):
            time.sleep(10)
            r = self.lua("local p = C.lord_unit():position(); return C.stats() .. string.format(' at=%d,%d,%d', p:get_x(), p:get_y(), p:get_z())", 8)
            stats.append(str(r["result"]))
            self.log("stats", r["result"])
            if len(stats) == 6:
                self.lua("return C.camera(-45, -35, 35, 15, 0, 0, 50)", 8)
                time.sleep(1)
                self.shot(f"{label}_wide")
        (self.dir / f"stats_{label}.txt").write_text("\n".join(stats), encoding="utf-8")
        result["sim_rate"] = self.sim_rate(sim_start, started)
        self.shot(f"{label}_end")
        result["stats"] = [stats[0], stats[len(stats) // 2], stats[-1]] if stats else []
        self.save_result(result)

    # ---------------- the progression (docs/design/progression-proposal.md): real orders, the game's own panels ----------------
    def prog(self, code, wait=15):
        """Lua with tools/tests/prog_lib.lua first. Its result goes to the log."""
        lib = (TESTS / "prog_lib.lua").read_text(encoding="utf-8")
        return self.plain(lib + "\nlocal P = _G.mtb_prog\n" + code, wait)

    def prog_file(self, name, **values):
        code = "".join(f'{k} = "{v}"\n' for k, v in values.items()) + (TESTS / name).read_text(encoding="utf-8")
        return self.prog(code)

    def state(self, label, expect=None):
        """The campaign's state: a line of the log and of results.jsonl. expect: parts that must be in the line."""
        row = self.prog("return P.state()")
        text = str(row["result"])
        missing = [part for part in (expect or []) if part not in text]
        self.log("state", label, text)
        self.save_result({"session": self.name, "label": label, "kind": "state", "state": text, "ok": not missing, "missing": missing})
        if not row["ok"]:
            raise RuntimeError(text)
        return text

    def safe_end_turn(self, limit=300):
        """Ends the turn and waits for the player's next one. Another army's attack on the way is autoresolved."""
        begin = self.prog("return cm:turn_number()")["result"]
        self.log("turn", self.script("end_turn.lua")["result"])
        end = time.time() + scaled(limit)
        step = ('for _, n in ipairs({"button_autoresolve", "button_captive_option_kill", "button_dismiss", "button_set_win", "button_continue", "button_dismiss_results"}) do '
                'if mtb.find(n, true) then mtb.click(n); return "clicked " .. n end end '
                'local e = mtb.find("events", true); local a = e and (mtb.find("choice_button", true, e) or mtb.find("button_accept", true, e)); if a then a:SimulateLClick() end '
                'local b = mtb.find("button_end_turn", true); return cm:turn_number() .. " " .. (b and b:CurrentState() or "-")')
        ticks = 0
        while time.time() < end:
            self.check_time()
            row = self.plain(step, 8)
            text = str(row["result"])
            if text.startswith("clicked"):
                self.log(text)
            ticks += 1
            if ticks % 4 == 0:      # an offer of the AI's, for example, stops the turn with the end turn button hidden
                found = self.script("dismiss_blockers.lua")["result"]
                if found != "{}":
                    self.log("blockers", found)
            if text == f"{int(float(begin)) + 1} active":
                self.log("blockers", self.script("dismiss_blockers.lua")["result"])
                time.sleep(1)
                return
            if text == f"{int(float(begin))} active":      # still the same turn with the button free: something took the first order away
                self.log("blockers", self.script("dismiss_blockers.lua")["result"])
                time.sleep(4)
                if str(self.plain(step, 8)["result"]) == text:
                    self.log("turn again", self.script("end_turn.lua")["result"])
            time.sleep(3)
        self.shot("turn_stuck")
        raise TimeoutError("the next turn did not come")

    # ---------------- the crew panel: clicks inside the game, tools/tests/crew_panel.lua ----------------
    def panel(self, step):
        """step: panel: Lua after the helpers (Q), wait, shot_as, expect: parts that must be in the result, absent: parts that must not."""
        code = (TESTS / "crew_panel.lua").read_text(encoding="utf-8") + "\nlocal Q = _G.mtb_panel\n" + step["panel"]
        row = self.plain(code, 15)
        text = str(row["result"])
        time.sleep(step.get("wait", 0.5))
        if step.get("shot_as"):
            self.shot(step["shot_as"])
        missing = [part for part in step.get("expect", []) if part not in text] + ["NOT " + part for part in step.get("absent", []) if part in text]
        self.log("panel", step.get("label", ""), text)
        if step.get("label") or missing:
            self.save_result({"session": self.name, "label": step.get("label", step["panel"]), "kind": "panel", "state": text, "ok": not missing, "missing": missing})

    def open_character_panel(self):
        self.prog("return P.select_malakai()")
        time.sleep(2)
        self.log(self.click("button_general"))
        time.sleep(3)

    def mount(self, to, shot=None):
        """Steps off or back on through the game's Mount block, by clicks, as the player does."""
        self.open_character_panel()
        self.log(self.prog_file("prog_mount_ui.lua", mtb_step="open")["result"])
        time.sleep(1.5)
        if shot:
            self.shot(shot + "_list")
        self.log(self.prog_file("prog_mount_ui.lua", mtb_step=to)["result"])
        time.sleep(2)
        if shot:
            self.shot(shot)
        self.log(self.click("button_ok"))
        time.sleep(1)

    def order(self, spec):
        """Orders buildings with the game's own command; points and gold come from the script."""
        self.prog("return P.select_malakai()")      # right after a battle the selection is not there yet: an order then does nothing, silently
        time.sleep(3)
        values = {"mtb_build": spec["prog_build"]}
        if spec.get("dev"):
            values["mtb_dev"] = spec["dev"]
        self.prog(f"cm:treasury_mod(P.malakai():faction():name(), {spec.get('gold', 30000)}); return 1")
        self.log("order", self.prog_file("prog_build.lua", **values)["result"])

    def demolish(self, spec):
        """Dismantles one building, ends turns until it is gone. Returns how many turns it took."""
        self.log("dismantle", self.prog_file("prog_build.lua", mtb_dismantle=spec["prog_dismantle"])["result"])
        for turns in range(1, spec.get("max_turns", 8) + 1):
            self.safe_end_turn()
            slots = str(self.prog("return P.slots()")["result"])
            self.log("slots", turns, slots)
            if spec["prog_dismantle"] not in slots.split(","):
                return turns
        return None

    def sync_current(self):
        row = self.plain("return tww3_mtb_crew.get()", 8)
        for group, option in re.findall(r"(\w+)=(\w+)", str(row["result"])):
            self.current[group] = option

    def foot_battle(self, spec):
        """A battle on foot: his stock unit, no barge module, no summon on the ability bar."""
        label = spec["label"]
        self.log("=== battle on foot", label)
        self.log("spawn", self.script("spawn_fight.lua")["result"])
        self.open_panel()
        self.shot(f"{label}_panel")
        self.log(self.click("button_attack"))
        self.wait_mode("battle", 300)
        time.sleep(4)
        read = self.plain((TESTS / "battle_read.lua").read_text(encoding="utf-8"), 15)
        (self.dir / f"foot_{label}.txt").write_text(str(read["result"]), encoding="utf-8")
        self.plain("bm:end_current_battle_phase(); return 1", 5)
        time.sleep(3)
        buttons = self.plain((TESTS / "prog_ability_bar.lua").read_text(encoding="utf-8"), 10)
        self.log("ability bar", buttons["result"])
        self.shot(f"{label}_battle")
        status = self.plain("return tostring(tww3_mtb_ammo and tww3_mtb_ammo.status)", 5)["result"]
        result = {"session": self.name, "label": label, "kind": "foot", "stock_unit": "type=wh3_dlc25_dwf_cha_malakai_makaisson" in str(read["result"]),
                  "summon_button": "spirit_of_grungni" in str(buttons["result"]), "ability_bar": str(buttons["result"])[:400], "ammo_status": status}
        self.log(self.script("battle_kill_enemy.lua")["result"])
        for attempt in range(round(scaled(25))):
            if self.visible("button_dismiss_results") != "-":
                break
            if attempt == round(scaled(8)):
                self.plain("bm:end_battle(); return 1", 5)
            time.sleep(3)
        self.log(self.click("button_dismiss_results"))
        self.wait_mode("campaign", 300)
        time.sleep(4)
        result["back_on_map"] = self.back_on_map()
        self.save_result(result)

    def stress(self, spec):
        code = ("local n = %d; collectgarbage('collect'); local a = collectgarbage('count'); local t0 = os.clock()\n"
                "for i = 1, n do tww3_mtb_crew.apply() end\n"
                "collectgarbage('collect'); return string.format('%%d applies, lua %%.0f -> %%.0f KB, %%.1f s, writes %%d, %%s', n, a, collectgarbage('count'), os.clock() - t0, tww3_mtb_crew.writes, tww3_mtb_crew.status)") % spec["stress"]
        before = self.memory_mb()
        row = self.plain(code, 120)
        time.sleep(3)
        self.save_result({"session": self.name, "label": "stress", "kind": "stress", "memory_before_mb": before, "memory_after_mb": self.memory_mb(), "status": row["result"]})

    def save_result(self, result):
        OUT.mkdir(parents=True, exist_ok=True)
        with RESULTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
        self.log("result", json.dumps({k: v for k, v in result.items() if k not in ("choice", "status")}, ensure_ascii=False))

    def save_game(self, name):
        folder = rg.USER / "save_games"
        before = {p.name: p.stat().st_mtime for p in folder.glob("*.save")}
        self.log("save", self.plain("cm:save(); return 'asked'", 10)["result"])
        end = time.time() + scaled(120)
        last = None
        while time.time() < end:
            time.sleep(3)
            try:           # the game writes under a temporary name first, so files can vanish between the listing and the check
                changed = [(p.name, p.stat().st_size) for p in folder.glob("*.save") if before.get(p.name) != p.stat().st_mtime]
            except OSError:
                continue
            if changed and changed == last:
                self.saves = getattr(self, "saves", []) + [(changed[0][0], name)]
                self.log("saved as", changed[0][0], changed[0][1])
                return
            last = changed
        raise TimeoutError("no save file appeared")


def run_session(name):
    spec = dict(SPEC["sessions"][name])
    if spec.get("join"):        # several sessions in one launch of the game: it takes the focus once
        parts = [SPEC["sessions"][n] for n in spec["join"]]
        spec = dict(parts[0], steps=[step for part in parts for step in part["steps"]], limit=sum(part.get("limit", 1200) for part in parts))
    busy_end = time.time() + 45 * 60
    while crew_session.busy_without_docker():
        if time.time() > busy_end:
            raise SystemExit("still busy")
        time.sleep(60)
    limit = round(scaled(spec.get("limit", 1200)) * LIMIT_SCALE)
    started = time.time()
    session = Session(name, started + limit)
    session.current = {g: v["start"] for g, v in OPTIONS["groups"].items()}
    session.current.update(spec.get("assume", {}))
    cmd = [sys.executable, str(REPO / "tools" / "crew_session.py"), "--label", "cycle_" + name, "--timeout", str(limit + 120), "--packs", *spec.get("packs", ["harness", "campaign"])]
    if spec.get("mods_file"):       # the user's mods, as his used_mods.txt has them
        # faster_loading_script_cache looks only at the packs of used_mods.txt: a changed test pack would run from its old cache. The cache is made again by itself.
        for cached in rg.rb.GAME.glob("loadfast_cache_*.bin"):
            cached.unlink()
        cmd += ["--user-mods-file", str(REPO / spec["mods_file"])]
    elif spec.get("memreader", True):
        cmd += ["--user-mods", "memreader_plus.pack"]
    if spec.get("save"):
        cmd += ["--save", spec["save"], "--args", f"game_startup_mode campaign_load {spec['save']}"]
    if MINIMIZED and not spec.get("new_campaign"):     # minimized in the main menu the Lua timers stand still: no command is answered
        cmd.append("--minimized")
    if IGPU:
        cmd.append("--igpu")
    elif spec.get("high"):
        cmd.append("--high-graphics")
    if EXTRA_SETTINGS:
        cmd += ["--set", *EXTRA_SETTINGS]
    OUT.mkdir(parents=True, exist_ok=True)
    log = (OUT / f"session_{name}.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    outcome = "failed"
    try:
        time.sleep(2)       # another agent's session may have taken the game first: then run_game.py has refused, and its state file is not ours
        if proc.poll() is not None:
            raise RuntimeError("the session did not start, see " + str(OUT))
        end = time.time() + 60
        while not rg.STATE.exists():
            if proc.poll() is not None or time.time() > end:
                raise RuntimeError("the session did not start, see " + str(OUT))
            time.sleep(1)
        session.dir = Path(rc.state()["run"])
        session.log("run", session.dir)
        if spec.get("new_campaign"):
            session.wait_mode("frontend", 240)
            time.sleep(10)
            session.log(session.plain(f'frontend.start_campaign("wh3_main_combi", "wh3_main_combi", "{spec["new_campaign"]}"); return 1', 10)["result"])
        session.wait_mode("campaign", 900)
        time.sleep(8)
        if spec.get("wait_end_turn"):      # the intro video of a new campaign plays first
            end = time.time() + scaled(spec["wait_end_turn"])
            while time.time() < end and session.visible("button_end_turn") in ("-", "inactive"):
                time.sleep(3)
        session.shot("map")
        row = session.plain("return tostring(tww3_mtb_crew and tww3_mtb_crew.status) .. ' ' .. mtb.dump(tww3_mtb_crew and tww3_mtb_crew.get())", 15)
        session.log("loaded", row["result"])
        session.save_result({"session": name, "label": "loaded", "kind": "load", "status": row["result"], "memory_mb": session.memory_mb()})
        if spec.get("expect_after_load"):
            for g, o in spec["expect_after_load"].items():
                if f"{g}={o}" not in str(row["result"]):
                    session.log("MISMATCH after load", g, o)
        session.log("blockers", session.script("dismiss_blockers.lua")["result"])
        for step in spec["steps"]:
            session.check_time()
            if step.get("save"):
                session.save_game(step["save"])
            elif step.get("lua"):
                session.log("lua", session.plain(step["lua"], 15)["result"])
            elif step.get("end_turn"):
                session.log("turn", session.script("end_turn.lua")["result"])
                time.sleep(step["end_turn"])
                session.log("blockers", session.script("dismiss_blockers.lua")["result"])
            elif step.get("ammo_ai"):
                session.ammo_ai_battle(step)
            elif step.get("ammo") or step.get("ammo_plain"):
                session.ammo_battle(step)
            elif step.get("ai"):
                session.ai_battle(step)
            elif step.get("stress"):
                session.stress(step)
            elif step.get("prog_state"):
                session.state(step["prog_state"], step.get("expect"))
            elif step.get("panel"):
                session.panel(step)
            elif step.get("prog_lua"):
                session.log("lua", session.prog(step["prog_lua"])["result"])
            elif step.get("prog_build"):
                session.order(step)
            elif step.get("prog_turn"):
                session.safe_end_turn()
            elif step.get("prog_mount"):
                session.mount(step["prog_mount"], step.get("shot_as"))
            elif step.get("prog_dismantle"):
                session.save_result({"session": name, "label": "dismantle " + step["prog_dismantle"], "kind": "dismantle", "turns": session.demolish(step)})
            elif step.get("prog_foot"):
                session.foot_battle(step)
            elif step.get("prog_tree"):
                session.log("tree", session.prog_file("prog_tree.lua", mtb_tree=step["prog_tree"])["result"])
            elif step.get("hold") and not step.get("label"):
                session.hold(step["hold"])
            elif step.get("wait"):
                time.sleep(step["wait"])
            elif step.get("shot"):
                session.shot(step["shot"])
            else:
                session.battle(step)
        outcome = "done"
    except Exception as e:  # the game must be closed in every case
        session.log("ERROR", type(e).__name__, e)
    finally:
        if proc.poll() is None:     # the flag closes whatever session is running: only ours may get it
            rg.STOP.write_text("stop")
        try:
            proc.wait(180)
        except subprocess.TimeoutExpired:
            session.log("session did not end in 180 s")
        session.log("session", name, outcome, "seconds", round(time.time() - started))
        for source, target in getattr(session, "saves", []):
            moved = SAVES / source
            if moved.exists():
                shutil.move(str(moved), SAVES / target)
                session.log("kept save", target)
            else:
                session.log("SAVE MISSING", source)
    return outcome == "done"


def report():
    rows = [json.loads(line) for line in RESULTS.read_text(encoding="utf-8").splitlines()]
    for r in rows:
        print(json.dumps({k: r.get(k) for k in ("session", "label", "kind", "seats_ok", "fired", "ammo", "kills", "hp", "min_near", "back_on_map", "memory_after_mb", "memory_mb", "sim_rate")}, ensure_ascii=False))


def main():
    global SCALE, LIMIT_SCALE, IGPU, MINIMIZED, EXTRA_SETTINGS
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["all", "session", "report"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--igpu", action="store_true")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--limit-scale", type=float, default=1.0)
    ap.add_argument("--minimized", action="store_true")
    ap.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE")
    args = ap.parse_args()
    SCALE, LIMIT_SCALE, IGPU, MINIMIZED, EXTRA_SETTINGS = args.scale, args.limit_scale, args.igpu, args.minimized, args.set
    if args.what == "report":
        report()
    elif args.what == "session":
        return 0 if run_session(args.name) else 1
    else:
        for name in SPEC["order"]:
            if not run_session(name):
                print("stopped at", name)
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
