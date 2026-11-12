"""The crew of the barge in 3D for the web page (web/js/viewer3d.js): py -3.10 tools/web_crew3d.py [--check] [name ...]

What stands at the crew's places on the drawing stands on the 3D barge too: each kind of each group a glTF of its own, loaded by the page only when
that kind is wanted. The models and poses are the ones tools/crew_cards.py renders the crew cards with (its scene functions draw into a frame; here a
frame that only collects the triangles, so the posed men are baked as they stand in battle, not in the T pose).
  places   the attachment points of the hull's tech skeleton (thunderbarge_tech/dwf_thunderbarge.anim, the one the game uses: tools/modular_parts.py,
           docs/design/modular-parts.md): a seat's model q goes onto the hull as F (R q + t), F = diag(-1, 1, -1). One copy of the model, a node per seat.
  guns     the stock thundercannon (cannons_stock; the flaming shells are the same gun, the mod changes only its shell: no model of its own) and the
           mod's guns of build/weapons/models (tools/gun_models.py), on ap_cannon_left and ap_cannon_right, in the model's rest pose.
  men      posed by crew_cards.draw_fighter: the riflemen on the rail seats (eleven: Malakai takes the twelfth, his own model on his side), the nests'
           throwers in the throwing pose of their cards, the lookouts standing; the size of a man is the option's scale (data/crew_options.json).
  harpoon  the harpoon's model at the balloon's nose (crew_cards.HARPOON_AT).
  bombs    none: the stock barge shows a bomb only as it drops; stowed, nothing of it is on the model (see ALL).
Writes build/web/models/crew_<group>_<kind>.gltf + .bin and their textures in build/web/models/crew_tex (base colour only, at most 512 px, JPEG):
the game's models and textures stay in build/. Python 3.10 with numpy, Pillow, opencv (as tools/crew_cards.py).
--check: also a side view of the hull with every model rendered by crew_cards' renderer, build/crew_models/groups/check_3d_<name>.png.
"""
import hashlib
import io
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.dont_write_bytecode = True
_argv, sys.argv = sys.argv, sys.argv[:1]
import crew_cards as cc  # noqa: E402
sys.argv = _argv

OUT = REPO / "build" / "web" / "models"
TEX = OUT / "crew_tex"
REFS = REPO / "build" / "crew_models" / "groups"
CONFIG = json.loads((REPO / "data" / "crew_options.json").read_text(encoding="utf-8"))
F = np.diag([-1.0, 1.0, -1.0]).astype(np.float32)
TEX_MAX = 512


def tech_frames():
    """{attachment point: 4 x 4 matrix in the hull's space} of the tech skeleton (tools/modular_parts.py reads it; py -3.14 for the packs: cached)."""
    cache = REFS / "tech_frames.json"
    if not cache.exists():
        import subprocess
        code = ("import sys, json; sys.path.insert(0, 'tools'); import modular_parts as mp; f, n = mp.tech_frames(mp.game_file(mp.TECH)); "
                "json.dump({k: {'R': v[1], 't': v[2]} for k, v in f.items()}, open(sys.argv[1], 'w'))")
        REFS.mkdir(parents=True, exist_ok=True)
        subprocess.run(["py", "-3.14", "-c", code, str(cache)], check=True, cwd=REPO)
    out = {}
    for name, f in json.loads(cache.read_text()).items():
        M = np.eye(4, dtype=np.float32)
        M[:3, :3] = F @ np.array(f["R"], np.float32)
        M[:3, 3] = F @ np.array(f["t"], np.float32)
        out[name] = M
    return out


class Collect:
    """A frame of crew_cards that keeps the triangles instead of drawing them."""
    def __init__(self):
        self.parts = []

    def draw(self, pos, nor, uv, tan, bit, tris, textures, oid, alpha=False):
        if len(tris):
            self.parts.append({"pos": np.asarray(pos, np.float32), "nor": np.asarray(nor, np.float32), "uv": np.asarray(uv, np.float32),
                               "tris": np.asarray(tris, np.int32), "base": textures[0], "alpha": bool(alpha)})


def scaled(s):
    return np.diag([s, s, s, 1.0]).astype(np.float32)


# ---- what each kind is ----
GUNS = {"stock": None, "organ": "tww3_mtb_organ.rigid_model_v2", "clatter": "tww3_mtb_clatter2.rigid_model_v2", "flame": "tww3_mtb_flame.rigid_model_v2"}
RIFLE_SEATS = ["ap_crew_left_upper_0", "ap_crew_left_upper_1", "ap_crew_left_0", "ap_crew_left_1", "ap_crew_left_2", "ap_crew_left_3",
               "ap_crew_right_upper_0", "ap_crew_right_upper_1", "ap_crew_right_0", "ap_crew_right_1", "ap_crew_right_2", "ap_crew_right_3"]
MALAKAI_SEAT = {"left": "ap_crew_left_1", "right": "ap_crew_right_1"}     # the drawing's Malakai: the second place of the waist from the bow (web_art.MALAKAI_AT)
RIFLES = {"pirates": ("dwf_slayer_pirates", cc.PISTOL, 25, ("be_prop_3",)), "quarrellers": ("dwf_quarrellers", cc.CROSSBOW, 0, ("be_prop_3",)),
          "thunderers": ("dwf_thunderers", cc.RIFLE, 0, ("be_prop_3",)), "rakers": ("dwf_thunderers_grudge_rakers", cc.RIFLE, 0, ("be_prop_3",)),
          "torpedoes": ("local:torpedo_prop3.vmd", cc.DRAKE, 0, ("be_prop_3",))}
NEST = {"stock": ("dwf_thunderbarge_crew_pirates_grenade", cc.THROW, 8, ("be_prop_1",), "hand_right"),
        "axes": ("local:cupola_axes.vmd", cc.THROW, 8, ("be_prop_1",), "hand_right"),
        "lookout": ("dwf_thunderbarge_crew_lookout", "animations/battle/humanoid03/subset/zeppelin_crew/stand/hu3_zeppelin_crew_stand_idle_01.anim", 0, (), None)}
# a man's size in the hull's own units: the option's scale over the hull's (the hull's variant is 1.2, data/crew_options.json, scale of a crew)
HULL_SCALE = 1.2


def option_scale(group, kind, default=1.15):
    o = CONFIG["groups"].get(group, {}).get("options", {}).get(kind, {})
    return (o.get("scale") or default) / HULL_SCALE


def collect(name, frames):
    """(parts, [seat matrices]) of a model name: one copy of the model in its seat's own space and the seats it stands on."""
    c = Collect()
    group, _, kind = name.partition("_")
    if group == "cannons":
        if kind == "stock":
            for mesh in cc.load_model(cc.STOCK_GUN)["lods"][0]:
                cc.rigid(mesh, cc.STOCK_GUN_MAT, c, np.eye(4, dtype=np.float32), 2)
        else:
            import re
            import rmv2
            model = rmv2.load((cc.OUR_GUNS / GUNS[kind]).read_bytes())
            ws = (cc.OUR_GUNS / GUNS[kind].replace(".rigid_model_v2", ".wsmodel")).read_text(encoding="utf-8")
            mats = {int(p): m for p, l, m in re.findall(r'part_index="(\d+)" lod_index="(\d+)">(.*?)<', ws) if l == "0"}
            for i, mesh in enumerate(model["lods"][0]):
                cc.rigid(mesh, mats[i], c, np.eye(4, dtype=np.float32), 2)
        return c.parts, [(s, frames[s]) for s in ("ap_cannon_left", "ap_cannon_right")]
    if group == "harpoon":
        M = np.eye(4, dtype=np.float32)
        M[:3, 3] = cc.HARPOON_AT
        for mesh, mat in cc.wsmodel(cc.HARPOON)[0]:
            cc.rigid(mesh, mat, c, M, 2)
        return c.parts, [("nose", np.eye(4, dtype=np.float32))]
    if group == "bombs":
        cc.draw_doors(c, np.eye(4, dtype=np.float32))
        return c.parts, [(s, frames[s]) for s in ("ap_bomb_bay_left_front", "ap_bomb_bay_left_rear", "ap_bomb_bay_right_front", "ap_bomb_bay_right_rear")]
    if group in ("cupolas", "lookouts"):
        vmd, anim, frame, props, hold = NEST["lookout" if group == "lookouts" else kind]
        cc.draw_fighter(c, vmd, anim, frame, scaled(option_scale("cupolas", kind, 1.2) if group == "cupolas" else 1.2 / HULL_SCALE), seed=1, props=props, hold=hold)
        return c.parts, [(s, frames[s]) for s in ("ap_cupola_front", "ap_cupola_rear")]
    if group == "rifles":
        vmd, anim, frame, props = RIFLES[kind]
        cc.draw_fighter(c, vmd, anim, frame, scaled(option_scale("rifles", kind)), seed=3, props=props)
        return c.parts, [(s, frames[s]) for s in RIFLE_SEATS]
    if group == "malakai":
        cc.draw_fighter(c, "dwf_malakai_makaisson", cc.RIFLE, 0, scaled(1.15 / HULL_SCALE), seed=1, props=("be_prop_3", "be_prop_0", "be_prop_1"))
        return c.parts, [(MALAKAI_SEAT[kind], frames[MALAKAI_SEAT[kind]])]
    raise SystemExit(f"unknown model {name}")


# ---- glTF ----
def texture_file(base, alpha):
    """The base colour as a file of crew_tex, shared by every model that uses it: JPEG (PNG when it is cut by alpha), at most TEX_MAX px."""
    im = Image.fromarray(np.asarray(base))
    small = im.copy()
    small.thumbnail((TEX_MAX, TEX_MAX), Image.LANCZOS)
    key = hashlib.sha1(np.asarray(small).tobytes()).hexdigest()[:16]
    cut = alpha and np.asarray(small)[..., 3].min() < 250
    name = f"{key}.{'png' if cut else 'jpg'}"
    path = TEX / name
    if not path.exists():
        TEX.mkdir(parents=True, exist_ok=True)
        if cut:
            small.save(path, optimize=True)
        else:
            small.convert("RGB").save(path, quality=86, optimize=True)
    return name, cut


def write_gltf(name, parts, seats):
    """One mesh (a primitive a material) under a root that turns the game's axes into three.js's (x mirrored), a node per seat."""
    blob = bytearray()
    views, accessors, prims, materials, textures, images = [], [], [], [], [], []
    image_of = {}

    def view(data, target):
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), "target": target})
        blob.extend(data)
        return len(views) - 1
    tris_total = 0
    for p in parts:
        pos, nor, uv, tris = p["pos"], p["nor"], p["uv"], p["tris"]
        used = np.unique(tris)          # only the vertices the triangles use (a culled part keeps all its vertices)
        remap = np.full(len(pos), -1, np.int64)
        remap[used] = np.arange(len(used))
        pos, nor, uv, tris = pos[used], nor[used], uv[used], remap[tris].astype(np.uint32)
        nor = nor / np.maximum(np.linalg.norm(nor, axis=1, keepdims=True), 1e-6)
        tris_total += len(tris)
        tex, cut = texture_file(p["base"], p["alpha"])
        if tex not in image_of:
            images.append({"uri": "crew_tex/" + tex})
            textures.append({"source": len(images) - 1, "sampler": 0})
            materials.append({"name": tex, "pbrMetallicRoughness": {"baseColorTexture": {"index": len(textures) - 1}, "metallicFactor": 0.0, "roughnessFactor": 0.8},
                              "doubleSided": True, **({"alphaMode": "MASK", "alphaCutoff": 0.5} if cut else {})})
            image_of[tex] = len(materials) - 1
        a = len(accessors)
        accessors.append({"bufferView": view(pos.astype("<f4").tobytes(), 34962), "componentType": 5126, "count": len(pos), "type": "VEC3",
                          "min": pos.min(0).tolist(), "max": pos.max(0).tolist()})
        accessors.append({"bufferView": view(nor.astype("<f4").tobytes(), 34962), "componentType": 5126, "count": len(pos), "type": "VEC3"})
        accessors.append({"bufferView": view(uv.astype("<f4").tobytes(), 34962), "componentType": 5126, "count": len(pos), "type": "VEC2"})
        accessors.append({"bufferView": view(tris.astype("<u4").tobytes(), 34963), "componentType": 5125, "count": tris.size, "type": "SCALAR"})
        prims.append({"attributes": {"POSITION": a, "NORMAL": a + 1, "TEXCOORD_0": a + 2}, "indices": a + 3, "material": image_of[tex]})
    nodes = [{"name": name, "matrix": [-1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], "children": list(range(1, len(seats) + 1))}]
    for seat, M in seats:          # named by the seat: the page hides a copy whose seat another takes (Malakai's at the rail)
        nodes.append({"name": seat, "mesh": 0, "matrix": M.T.reshape(-1).astype(float).tolist()})
    gltf = {"asset": {"version": "2.0", "generator": "tools/web_crew3d.py"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes,
            "meshes": [{"name": name, "primitives": prims}], "materials": materials, "textures": textures, "images": images,
            "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
            "buffers": [{"uri": f"crew_{name}.bin", "byteLength": len(blob)}], "bufferViews": views, "accessors": accessors}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"crew_{name}.bin").write_bytes(bytes(blob))
    (OUT / f"crew_{name}.gltf").write_text(json.dumps(gltf), encoding="utf-8")
    return tris_total, len(blob)


# The bombs are not exported: the stock barge shows a bomb only as it falls (crew_cards.bomb_card), the bay's rig is its open doors, and in flight
# the doors are shut (the hatches' detail, part_bomb_hatches). Nothing of a stowed bomb is on the model to show.
ALL = (["cannons_" + k for k in GUNS] + ["harpoon_on", "cupolas_stock", "cupolas_axes", "lookouts_on"]
       + ["rifles_" + k for k in RIFLES] + ["malakai_left", "malakai_right"])


def check(name, parts, seats, view="side"):
    """The hull and this model through crew_cards' renderer: the places checked against the hull the game puts them on."""
    cams = {"side": ([30, 9.5, -1.0], [0, 9.5, -1.0], 30 / 30.0), "bow": ([9, 3.5, 12], [1.2, 1.6, 5.2], 1.6), "top": ([10, 30, 8], [0, 20.5, -1], 1.6),
            "waist": ([14, 4.5, 2], [1.5, 2.6, 1.0], 1.4), "below": ([6, -9, 2], [0.5, 0.6, 0], 1.3)}
    eye, target, focal = cams[view]
    fr = cc.Frame(900, 700, cc.look(eye, target), focal)
    cc.draw_hull(fr, balloon=view in ("side", "top"))
    for _, M in seats:
        for p in parts:
            pos = p["pos"] @ M[:3, :3].T + M[:3, 3]
            nor = p["nor"] @ M[:3, :3].T
            fr.draw(pos.astype(np.float32), nor.astype(np.float32), p["uv"], nor.astype(np.float32), nor.astype(np.float32), p["tris"], (p["base"], np.full((4, 4, 4), 128, np.uint8), np.zeros((4, 4, 4), np.uint8)), 3, p["alpha"])
    col, mask = cc.lit(fr)
    Image.fromarray((np.clip(col * mask[..., None] + .72 * (1 - mask[..., None]), 0, 1) * 255).astype(np.uint8)).save(REFS / f"check_3d_{name}_{view}.png")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    names = args or ALL
    frames = tech_frames()
    report = {}
    for name in names:
        parts, seats = collect(name, frames)
        tris, size = write_gltf(name, parts, seats)
        report[name] = {"triangles": tris, "copies": len(seats), "bytes": size}
        print(name, report[name])
        if "--check" in sys.argv:
            group = name.split("_")[0]
            check(name, parts, seats, {"cannons": "bow", "harpoon": "side", "bombs": "below", "cupolas": "top", "lookouts": "top"}.get(group, "waist"))
    old = json.loads((OUT / "crew_report.json").read_text()) if (OUT / "crew_report.json").exists() else {}
    (OUT / "crew_report.json").write_text(json.dumps(old | report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
