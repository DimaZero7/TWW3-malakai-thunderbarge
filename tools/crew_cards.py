"""Crew cards in the style of the game's unit cards: real models and textures, a small software renderer, then brush strokes.

    python tools/crew_cards.py                  all cards to data/ui/crew_cards, the sheet to docs/research/img/crew-cards-sheet.png
    python tools/crew_cards.py --only a,b --plain FILE     quick unpainted views
    python tools/crew_cards.py --only a,b --sheet FILE     painted, to a sheet only

Python 3.10+ with numpy, opencv-python, Pillow. Game files come through tools/crew_cards_fetch.py (py -3.14) into build/crew_cards_cache.
Our guns are read from build/weapons/models: run tools/gun_models.py first. Vanilla reference and the torn alpha: ui/units/infopics/wh_main_dwf_organ_gun.png.
A card: 120 x 260 RGBA (infopics) and <id>_small.png 60 x 130 opaque (icons). The id is <group>_<option> of data/crew_options.json, as stock repeats between groups.
"""
import argparse
import io
import math
import re
import struct
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.dont_write_bytecode = True
import card_anim  # noqa: E402
import rmv2  # noqa: E402

rmv2.STRIDE[0] = 32     # static props: 8 position, 4 uv, 4 second uv, normal, tangent, bitangent, colour; only read here, mesh_arrays knows the layout
CACHE = ROOT / "build" / "crew_cards_cache"
OUT = ROOT / "data" / "ui" / "crew_cards"
SHEET = ROOT / "docs" / "research" / "img" / "crew-cards-sheet.png"
OUR_GUNS = ROOT / "build" / "weapons" / "models" / "warmachines" / "aircraft" / "dwf_thunderbarge" / "cannon"
W, H = 480, 1040
SS = 2     # the render is this much bigger than the painting
HULL = "warmachines/aircraft/dwf_thunderbarge/dwf_thunderbarge_01.rigid_model_v2"
TEX = {}
MODELS = {}
PORT = [1.42, 1.28, 5.79]


# ---------------------------------------------------------------- game files
def game(path):
    key = path.lower().replace("/", "\\")
    out = CACHE / key.replace("\\", "__")
    if not out.exists():
        subprocess.run(["py", "-3.14", str(ROOT / "tools" / "crew_cards_fetch.py"), key], check=True)
    if not out.exists():
        raise SystemExit(f"not in the game's packs: {path}")
    return out.read_bytes()


def dds(path):
    key = path.lower().replace("/", "\\")
    if key in TEX:
        return TEX[key]
    npy = CACHE / (key.replace("\\", "__") + ".npy")
    if npy.exists():
        TEX[key] = np.load(npy, mmap_mode="r")
        return TEX[key]
    raw = bytearray(game(path))
    if raw[84:88] == b"DX10":
        fmt = struct.unpack_from("<I", raw, 128)[0]
        struct.pack_into("<I", raw, 128, {72: 71, 75: 74, 78: 77, 99: 98, 91: 87}.get(fmt, fmt))     # sRGB forms Pillow does not know
    im = Image.open(io.BytesIO(bytes(raw)))
    im.load()
    TEX[key] = np.asarray(im.convert("RGBA"), np.uint8)
    np.save(npy, TEX[key])
    return TEX[key]


def material_textures(material):
    """(base, normal, material map) of a .xml.material."""
    text = game(material).decode("utf-8", "ignore")
    found = re.findall(r"[\w/\\ .-]+\.dds", text, re.I)
    pick = lambda word: next((f for f in found if word in f.lower()), None)
    return pick("base_colour") or pick("diffuse"), pick("normal"), pick("material_map") or pick("gloss_map")


def load_model(path=None, blob=None):
    key = path or id(blob)
    if key not in MODELS:
        MODELS[key] = rmv2.load(blob if blob is not None else game(path))
    return MODELS[key]


def wsmodel(path):
    """[(mesh, material)] of a .wsmodel's first level."""
    if path.lower().endswith(".rigid_model_v2"):       # some variants name the geometry itself: its own texture records hold
        model = load_model(path)
        return [(mesh, None) for mesh in model["lods"][0]], model
    text = game(path).decode("utf-8", "ignore")
    found = re.search(r"<geometry>(.*?)</geometry>", text, re.I)
    if not found:
        raise SystemExit(f"no geometry in {path}: {text[:200]!r}")
    geo = found.group(1).strip()
    mats = {}
    for lod, part, m in re.findall(r'<material[^>]*?lod_index="(\d+)"[^>]*?part_index="(\d+)"[^>]*>(.*?)</material>', text) + \
            [(b, a, c) for a, b, c in re.findall(r'<material[^>]*?part_index="(\d+)"[^>]*?lod_index="(\d+)"[^>]*>(.*?)</material>', text)]:
        if lod == "0":
            mats[int(part)] = m.strip()
    model = load_model(geo)
    return [(mesh, mats.get(i, mats.get(0))) for i, mesh in enumerate(model["lods"][0])], model


def mesh_arrays(mesh):
    n = len(mesh.verts)
    pos = np.array([(v.x, v.y, v.z) for v in mesh.verts], np.float32)
    if mesh.vertex_type == 0:
        uv = np.frombuffer(b"".join(bytes((v.bone0, v.bone1, v.weight0, v.weight1)) for v in mesh.verts), "<f2").reshape(n, 2).astype(np.float32)
        rest = np.frombuffer(b"".join(v.rest[4:16] for v in mesh.verts), np.uint8).reshape(n, 12).astype(np.float32)
        return pos, rest[:, :3] / 127.5 - 1, uv, rest[:, 4:7] / 127.5 - 1, rest[:, 8:11] / 127.5 - 1, np.array(mesh.tris, np.int32).reshape(-1, 3)
    off = 4 if mesh.vertex_type == 4 else 0
    rest = np.frombuffer(b"".join(v.rest[off:off + 16] for v in mesh.verts), np.uint8).reshape(n, 16).astype(np.float32)
    nor = rest[:, :3] / 127.5 - 1
    uv = np.frombuffer(b"".join(v.rest[off + 4:off + 8] for v in mesh.verts), "<f2").reshape(n, 2).astype(np.float32)
    return pos, nor, uv, rest[:, 8:11] / 127.5 - 1, rest[:, 12:15] / 127.5 - 1, np.array(mesh.tris, np.int32).reshape(-1, 3)


def bone_weights(mesh):
    """(indices n x 4, weights n x 4)"""
    if mesh.vertex_type == 0:
        n = len(mesh.verts)
        return np.zeros((n, 4), np.int32), np.tile(np.array([1, 0, 0, 0], np.float32), (n, 1))
    if mesh.vertex_type == 4:
        idx = np.array([(v.bone0, v.bone1, v.weight0, v.weight1) for v in mesh.verts], np.int32)
        wt = np.array([tuple(v.rest[:4]) for v in mesh.verts], np.float32) / 255
    else:
        idx = np.array([(v.bone0, v.bone1, 0, 0) for v in mesh.verts], np.int32)
        wt = np.array([(v.weight0, v.weight1, 0, 0) for v in mesh.verts], np.float32) / 255
    return idx, wt / (wt.sum(1, keepdims=True) + 1e-6)


# ---------------------------------------------------------------- renderer
def norm(v):
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)


def look(eye, target, up=(0, 1, 0)):
    eye, target, up = [np.array(a, np.float32) for a in (eye, target, up)]
    f = norm(target - eye)
    r = norm(np.cross(f, up))
    return eye, r, np.cross(r, f), f


class Frame:
    def __init__(self, w, h, cam, focal):
        self.w, self.h, self.cam, self.focal = w, h, cam, focal * h
        self.z = np.full((h, w), 1e9, np.float32)
        self.alb = np.zeros((h, w, 3), np.float32)
        self.nor = np.zeros((h, w, 3), np.float32)
        self.mat = np.zeros((h, w, 3), np.float32)
        self.id = np.zeros((h, w), np.uint8)

    def project(self, p):
        eye, r, u, f = self.cam
        rel = np.array(p, np.float32) - eye
        d = rel @ f
        return self.w / 2 + (rel @ r) / d * self.focal, self.h / 2 - (rel @ u) / d * self.focal

    def draw(self, pos, nor, uv, tan, bit, tris, textures, oid, alpha=False):
        base, nmap, mmap = textures
        eye, r, u, f = self.cam
        rel = pos - eye
        x, y, d = rel @ r, rel @ u, rel @ f
        keep = d > .05
        safe = np.where(keep, d, 1)
        fx, fy = self.w / 2 + x / safe * self.focal, self.h / 2 - y / safe * self.focal
        th, tw = base.shape[:2]
        nh, nw = nmap.shape[:2]
        mh, mw = mmap.shape[:2]
        for a, b, c in tris:
            if not (keep[a] and keep[b] and keep[c]):
                continue
            x0, y0, x1, y1, x2, y2 = fx[a], fy[a], fx[b], fy[b], fx[c], fy[c]
            minx, maxx = int(max(min(x0, x1, x2), 0)), int(min(max(x0, x1, x2) + 1, self.w - 1))
            miny, maxy = int(max(min(y0, y1, y2), 0)), int(min(max(y0, y1, y2) + 1, self.h - 1))
            if minx > maxx or miny > maxy:
                continue
            den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(den) < 1e-9:
                continue
            xs, ys = np.meshgrid(np.arange(minx, maxx + 1) + .5, np.arange(miny, maxy + 1) + .5)
            l0 = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / den
            l1 = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / den
            l2 = 1 - l0 - l1
            m = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
            if not m.any():
                continue
            w0, w1, w2 = l0[m] / d[a], l1[m] / d[b], l2[m] / d[c]
            z = 1 / (w0 + w1 + w2)
            yy, xx = np.nonzero(m)
            yy, xx = yy + miny, xx + minx
            near = z < self.z[yy, xx]
            if not near.any():
                continue
            yy, xx, z = yy[near], xx[near], z[near]
            w0, w1, w2 = w0[near] * z, w1[near] * z, w2[near] * z
            tu = (w0 * uv[a, 0] + w1 * uv[b, 0] + w2 * uv[c, 0]) % 1
            tv = (w0 * uv[a, 1] + w1 * uv[b, 1] + w2 * uv[c, 1]) % 1
            tx, ty = (tu * tw).astype(np.int32).clip(0, tw - 1), (tv * th).astype(np.int32).clip(0, th - 1)
            texel = base[ty, tx]
            if alpha:
                solid = texel[:, 3] > 110
                if not solid.any():
                    continue
                yy, xx, z, w0, w1, w2, tu, tv, texel = yy[solid], xx[solid], z[solid], w0[solid], w1[solid], w2[solid], tu[solid], tv[solid], texel[solid]
            self.z[yy, xx] = z
            self.alb[yy, xx] = texel[:, :3]
            self.mat[yy, xx] = mmap[(tv * mh).astype(np.int32).clip(0, mh - 1), (tu * mw).astype(np.int32).clip(0, mw - 1), :3]
            nn = norm(w0[:, None] * nor[a] + w1[:, None] * nor[b] + w2[:, None] * nor[c])
            tt = w0[:, None] * tan[a] + w1[:, None] * tan[b] + w2[:, None] * tan[c]
            bb = w0[:, None] * bit[a] + w1[:, None] * bit[b] + w2[:, None] * bit[c]
            s = nmap[(tv * nh).astype(np.int32).clip(0, nh - 1), (tu * nw).astype(np.int32).clip(0, nw - 1)]
            nx, ny = s[:, 3].astype(np.float32) / 127.5 - 1, s[:, 1].astype(np.float32) / 127.5 - 1    # the game's normal maps: x in alpha, y in green
            nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
            self.nor[yy, xx] = norm(tt * nx[:, None] + bb * ny[:, None] + nn * nz[:, None])
            self.id[yy, xx] = oid


def textures_of(material, mesh=None):
    if material:
        b, n, m = material_textures(material)
    else:
        names = [t[4:260].split(b"\0")[0].decode("latin1") for t in mesh.textures]
        pick = lambda word: next((f for f in names if word in f.lower()), None)
        b, n, m = pick("base_colour") or pick("diffuse"), pick("normal"), pick("material_map") or pick("gloss")
    return dds(b), dds(n), dds(m or n)


def rigid(mesh, material, frame, M, oid, cull=None, alpha=None):
    """A mesh under one 4 x 4 matrix."""
    pos, nor, uv, tan, bit, tris = mesh_arrays(mesh)
    if cull is not None:
        tris = tris[cull(pos[tris])]
    R3 = M[:3, :3]
    scale = np.cbrt(abs(np.linalg.det(R3)))
    pos = pos @ R3.T + M[:3, 3]
    nor, tan, bit = nor @ R3.T / scale, tan @ R3.T / scale, bit @ R3.T / scale
    frame.draw(pos, nor, uv, tan, bit, tris, textures_of(material, mesh), oid, alpha=("alpha_on" in material) if alpha is None else alpha)


HULLMAT = "warmachines/materials/dwf_thunderbarge_grungni_01_weighted4_alpha_off.xml.material"
BALLOONMAT = "warmachines/materials/dwf_thunderbarge_grungni_01_weighted2_alpha_on.xml.material"


def draw_hull(frame, cull_y=None, balloon=False):
    hull = load_model(HULL)["lods"][0]
    cull = (lambda t: (t[:, :, 1] < cull_y).all(axis=1)) if cull_y is not None else None
    rigid(hull[0], HULLMAT, frame, np.eye(4, dtype=np.float32), 1, cull)
    if balloon:
        rigid(hull[1], BALLOONMAT, frame, np.eye(4, dtype=np.float32), 1, alpha=False)
        rigid(hull[2], BALLOONMAT, frame, np.eye(4, dtype=np.float32), 1, alpha=True)      # the balloon's skin and the rope net


def aim_matrix(port, aim, scale=1.0):
    d = norm(np.array(aim, np.float32))
    up = norm(np.array([0, 1, 0], np.float32) - d * d[1])
    side = np.cross(up, d)
    M = np.eye(4, dtype=np.float32)
    M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = side * scale, up * scale, d * scale, port
    return M


def seat_matrix(pos, yaw, scale):
    a = math.radians(yaw)
    M = np.eye(4, dtype=np.float32)
    M[:3, 0] = (math.cos(a) * scale, 0, -math.sin(a) * scale)
    M[:3, 1] = (0, scale, 0)
    M[:3, 2] = (math.sin(a) * scale, 0, math.cos(a) * scale)
    M[:3, 3] = pos
    return M


# ---------------------------------------------------------------- fighters
SK = {}


def skeleton():
    if not SK:
        a = card_anim.Anim(game("animations/skeletons/humanoid03.anim"))
        SK["anim"] = a
        SK["rest"] = a.local(0)
        SK["inv"] = [np.linalg.inv(m) for m in a.world(0)]
        SK["index"] = {n: i for i, n in enumerate(a.names)}
    return SK


def vmd_meshes(text, rng, attach=None):
    """[(wsmodel path, attach point)]: one pick per slot, following references."""
    out = []
    for attrs, inner in re.findall(r"<SLOT\b([^>]*?)(?:/>|>(.*?)</SLOT>)", text, re.S):
        point = re.search(r'attach_point="([^"]+)"', attrs)
        point = point.group(1) if point else attach
        options = re.findall(r'<VARIANT_MESH_REFERENCE\s+definition="([^"]+)"|<VARIANT_MESH\s+model="([^"]+)"', inner or "")
        if not options:
            continue
        ref, model = options[int(rng.integers(len(options)))]
        if ref:
            out += vmd_meshes(game(ref).decode("utf-8", "ignore"), rng, point)
        else:
            out.append((model, point))
    return out


def fighter_parts(vmd, seed):
    text = (ROOT / "data" / "vmd" / vmd[6:]).read_text(encoding="utf-8") if vmd.startswith("local:") else game(f"variantmeshes/variantmeshdefinitions/{vmd}.variantmeshdefinition").decode("utf-8", "ignore")
    return vmd_meshes(text, np.random.default_rng(seed))


def draw_fighter(frame, vmd, anim_path, anim_frame, M, seed=1, oid=4, props=("be_prop_3",), hold=None):
    """hold: the bone a weapon goes on instead of its prop bone: in a throwing pose the prop bone stays at the belt, the raised hand is empty."""
    sk = skeleton()
    pose = card_anim.Anim(game(anim_path)).world(anim_frame, sk["rest"]) if anim_path else sk["anim"].world(0)
    skin = [pose[i] @ sk["inv"][i] for i in range(len(pose))]
    parts = fighter_parts(vmd, seed)
    for model, point in parts:
        if point and point not in props:     # what hangs on the belt or the back stays out: the card shows the one weapon
            continue
        meshes, info = wsmodel(model.replace("\\", "/"))
        for mesh, material in meshes:
            if any(b"blood_pack" in t or b"stump" in t for t in mesh.textures) or (material and "stump" in material.lower()):
                continue      # the wound parts for dismemberment
            pos, nor, uv, tan, bit, tris = mesh_arrays(mesh)
            idx, wt = bone_weights(mesh)
            attached = point is not None and info["skeleton"] != "humanoid03"    # a weapon's own small rig is ignored, it hangs on the prop bone
            if attached:
                P = pose[sk["index"][hold or point]]
                mat = np.broadcast_to(P, (len(pos), 4, 4))
            else:
                stack = np.stack(skin)
                mat = (stack[idx.clip(0, len(skin) - 1)] * wt[..., None, None]).sum(1)
            full = M @ mat
            h = np.concatenate([pos, np.ones((len(pos), 1), np.float32)], 1)
            world = (full @ h[..., None])[..., :3, 0]
            rotn = full[:, :3, :3]
            n2 = norm((rotn @ nor[..., None])[..., 0])
            t2 = norm((rotn @ tan[..., None])[..., 0])
            b2 = norm((rotn @ bit[..., None])[..., 0])
            frame.draw(world.astype(np.float32), n2, uv, t2, b2, tris, textures_of(material, mesh), oid, alpha=not material or "alpha_on" in material)


# ---------------------------------------------------------------- lighting
def lit(fr):
    alb = (fr.alb / 255) ** 2.2
    nor, mat, z, oid = fr.nor, fr.mat / 255, fr.z, fr.id
    eye, r, u, f = fr.cam
    mask = oid > 0
    L = norm(-.30 * r + .78 * u - .55 * f)
    V = -f
    Hv = norm(L + V)
    NV = nor @ V
    nl = np.clip(nor @ L, 0, 1)
    wrap = np.clip((nor @ L + .25) / 1.25, 0, 1)
    up = np.clip(.5 + .5 * (nor @ u), 0, 1)[..., None]
    sky = np.array([.58, .72, .92], np.float32)
    ground = np.array([.20, .17, .17], np.float32)
    amb = ground + (sky - ground) * up
    gun = (oid >= 2).astype(np.float32)
    s = z.shape[0] / 1040
    M = np.float32([[1, 0, 8 * s], [0, 1, 26 * s]])
    drop = cv2.GaussianBlur(cv2.warpAffine(gun, M, (z.shape[1], z.shape[0])), (0, 0), 7 * s)
    shadow = 1 - .70 * drop * (oid == 1)
    zf = np.where(mask, z, np.median(z[mask]))
    ao = np.clip(1 - 3.2 * np.clip(zf - cv2.GaussianBlur(zf, (0, 0), 9 * s), 0, .5), .25, 1)
    sun = np.array([1.0, .94, .84], np.float32) * 1.05
    metal = np.clip((mat[..., 0] - .25) / .5, 0, 1) * (1 - np.clip((alb[..., 0] - alb[..., 2]) * 5, 0, .9))   # rope and brass keep their colour
    gloss = np.clip(1 - mat[..., 1], .05, 1)
    col = alb * (1 - metal[..., None] * .92) * (amb * .55 * ao[..., None] + sun * (wrap * shadow)[..., None])
    Rr = 2 * NV[..., None] * nor - V
    ry = Rr @ u
    env = .05 + .20 * np.clip(ry * 3 + .3, 0, 1) + .75 * np.clip((ry - .35) * 2.2, 0, 1) ** 2
    envc = env[..., None] * np.array([.74, .86, 1.08], np.float32)
    col = col + metal[..., None] * alb ** .55 * envc * (shadow * ao)[..., None]
    spec = np.clip(nor @ Hv, 0, 1) ** (10 + 120 * gloss) * nl * (.08 + .9 * metal)
    col += (spec * shadow)[..., None] * np.array([.95, 1.0, 1.1], np.float32)
    # dark lines where parts meet: stock cards outline their forms
    edge = np.clip(np.abs(cv2.Laplacian(cv2.GaussianBlur(zf, (0, 0), 1.2 * s), cv2.CV_32F)) * 60 * s, 0, 1)
    seams = cv2.morphologyEx(oid, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    col *= (1 - .55 * edge)[..., None] * (1 - .35 * (seams & mask))[..., None]
    col = np.clip(col * 1.10, 0, None)
    col = col * (1 + col * .35) / (1 + col)
    col = np.clip(col * 1.75, 0, 1) ** (1 / 2.2)
    col = np.clip(col + (col - .42) * .28, 0, 1)
    grey = col.mean(2, keepdims=True)
    return np.clip(grey + (col - grey) * 1.02, 0, 1), mask.astype(np.float32)


# ---------------------------------------------------------------- background and fire
def fbm(w, h, seed, base=4, octaves=6, stretch=1.0):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        gw, gh = base * 2 ** o + 2, max(int(base * 2 ** o * h / w / stretch), 1) + 2
        out += amp * cv2.resize(rng.random((gh, gw), np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
        tot += amp
        amp *= .55
    return np.clip(out / tot, 0, 1)


def background(seed=0):
    """Sky with big clouds, far ridges through haze; no ground: the barge flies."""
    w, h = W, H
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    top, mid = np.array([.54, .70, .82], np.float32), np.array([.86, .90, .92], np.float32)
    bg = (top + (mid - top) * np.clip(y * 1.35, 0, 1) ** 1.1)[:, None, :].repeat(w, 1).reshape(h, w, 3)
    yy = np.arange(h)[:, None]
    for level, col, sd, rough, a in ((.62, (.72, .78, .82), 3, 28, .75), (.70, (.62, .70, .76), 5, 20, .8)):
        n = fbm(w, 1, sd + seed, base=2, octaves=4)[0]
        ridge = (level + (n - .5) * rough * 2 / 100) * h
        rm = cv2.GaussianBlur((yy > ridge[None, :]).astype(np.float32), (0, 0), 4)[..., None] * a
        facet = (fbm(w, h, sd + 40, base=5, octaves=4)[..., None] - .5) * .18
        bg = bg * (1 - rm) + np.clip(np.array(col, np.float32) + facet, 0, 1) * rm
    c = fbm(w, h, 11 + seed, base=3, octaves=3, stretch=.55)
    bank = np.clip((y - .68) / .16, 0, 1)
    cm = np.clip((c - .62 + bank * .55) * 6, 0, 1)
    wisps = np.clip((fbm(w, h, 17 + seed, base=2, octaves=3, stretch=.3) - .58) * 4, 0, 1) * np.clip(.95 - y * 2.0, 0, 1)
    cm = np.clip(cm + wisps * .6, 0, 1)
    shade = np.clip((y - .55) / .45, 0, 1)[..., None] * (fbm(w, h, 23 + seed, base=4, octaves=3)[..., None] * 1.1)
    lite, dark = np.array([.97, .97, .95], np.float32), np.array([.68, .74, .80], np.float32)
    cloud = lite + (dark - lite) * np.clip(shade, 0, 1)
    return np.clip(bg * (1 - cm[..., None]) + cloud * cm[..., None], 0, 1)


def fire(src, x, y, dx, dy, length, width, seed=1):
    """A painted tongue of fire from (x, y) in painting pixels, along (dx, dy)."""
    h, w = src.shape[:2]
    rng = np.random.default_rng(seed)
    d = math.hypot(dx, dy)
    dx, dy = dx / d, dy / d
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    a = (xx - x) * dx + (yy - y) * dy
    b = (xx - x) * -dy + (yy - y) * dx
    noise = cv2.GaussianBlur(rng.random((h, w), np.float32), (0, 0), length * .05) - .5
    noise = noise / (np.abs(noise).max() + 1e-6)
    t = np.clip(a / length, 0, 1)
    prof = width * np.sqrt(np.clip(t * 6, 0, 1)) * (1 - t) ** .75
    v = 1 - np.abs(b + noise * width * .55) / (prof + 1e-3)
    v = np.where((a > 0) & (a < length), v, 0)
    v = np.clip(v, 0, 1)
    col = np.zeros((h, w, 3), np.float32)
    stops = [(0, (.75, .16, .04)), (.35, (.95, .38, .06)), (.65, (1.0, .72, .18)), (1, (1.0, .96, .72))]
    for ch in range(3):
        col[..., ch] = np.interp(v, [s[0] for s in stops], [s[1][ch] for s in stops])
    alpha = np.clip(v * 3.2, 0, 1)[..., None]
    return src * (1 - alpha) + col * alpha


def glow(src, x, y, r, strength=.8):
    h, w = src.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * r * r))[..., None] * strength
    return np.clip(src + g * np.array([1.0, .50, .14], np.float32), 0, 1)


# ---------------------------------------------------------------- painting
def strokes(src, layers, seed=1):
    """Layered brush strokes along the image's edges, coarse to fine, only where the canvas is still wrong."""
    h, w = src.shape[:2]
    rng = np.random.default_rng(seed)
    canvas = np.full_like(src, .85)
    lum = cv2.cvtColor((src * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    for radius, thresh, maxlen, jitter in layers:
        ref = cv2.GaussianBlur(src, (0, 0), radius * .5)
        gl = cv2.GaussianBlur(lum, (0, 0), radius * .6)
        gx, gy = cv2.Sobel(gl, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(gl, cv2.CV_32F, 0, 1, ksize=3)
        diff = np.linalg.norm(canvas - ref, axis=2)
        step = max(int(radius), 1)
        ys, xs = np.mgrid[0:h:step, 0:w:step]
        order = rng.permutation(ys.size)
        for y0, x0 in zip(ys.ravel()[order], xs.ravel()[order]):
            y1, x1 = min(y0 + step, h), min(x0 + step, w)
            cell = diff[y0:y1, x0:x1]
            if cell.mean() < thresh:
                continue
            j = np.unravel_index(cell.argmax(), cell.shape)
            x, y = float(x0 + j[1]), float(y0 + j[0])
            col = ref[int(y), int(x)] + rng.normal(0, jitter, 3)
            pts = [(x, y)]
            lastx, lasty = 0.0, 0.0
            for i in range(maxlen):
                ix, iy = int(np.clip(x, 0, w - 1)), int(np.clip(y, 0, h - 1))
                if i > 1 and np.linalg.norm(canvas[iy, ix] - ref[iy, ix]) < np.linalg.norm(ref[iy, ix] - col):
                    break
                dx, dy = -gy[iy, ix], gx[iy, ix]
                mag = (dx * dx + dy * dy) ** .5
                if mag < 1e-3:
                    dx, dy = (lastx, lasty) if i else (1.0, -.25)
                    mag = (dx * dx + dy * dy) ** .5 + 1e-6
                dx, dy = dx / mag, dy / mag
                if lastx * dx + lasty * dy < 0:
                    dx, dy = -dx, -dy
                x, y = x + dx * radius, y + dy * radius
                lastx, lasty = dx, dy
                if not (0 <= x < w and 0 <= y < h):
                    break
                pts.append((x, y))
            arr = (np.array(pts, np.float32) * 8).astype(np.int32)
            cv2.polylines(canvas, [arr.reshape(-1, 1, 2)], False, tuple(float(c) for c in np.clip(col, 0, 1)),
                          max(int(radius * 2 * rng.uniform(.8, 1.15)), 1), cv2.LINE_AA, 3)
    return np.clip(canvas, 0, 1)


LAYERS = [(22, .03, 10, .018), (11, .04, 10, .018), (5.5, .06, 8, .016), (2.6, .13, 6, .012), (1.3, .26, 5, .008)]


def paint(fr, seed=0, post=None):
    col, mask = lit(fr)
    col = cv2.resize(col, (W, H), interpolation=cv2.INTER_AREA)
    mask = cv2.resize(mask, (W, H), interpolation=cv2.INTER_AREA)[..., None]
    col8 = (np.clip(col, 0, 1) * 255).astype(np.uint8)
    flat = cv2.edgePreservingFilter(col8, flags=1, sigma_s=34, sigma_r=.34).astype(np.float32) / 255
    col = flat * .9 + col * .1
    src = background(seed) * (1 - mask) + col * mask
    if post:
        src = post(np.clip(src, 0, 1))
    return strokes(np.clip(src, 0, 1), LAYERS, seed + 1)


def finish(canvas, name):
    ref = Image.open(io.BytesIO(game("ui/units/infopics/wh_main_dwf_organ_gun.png"))).convert("RGBA")
    rgb = Image.fromarray((canvas * 255).astype(np.uint8))
    info = rgb.resize((120, 260), Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.2, 70, 2))
    small = rgb.resize((60, 130), Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.0, 70, 2)).convert("RGBA")     # opaque, RGBA like the game's icons
    return Image.fromarray(np.dstack([np.asarray(info), np.asarray(ref)[..., 3]]), "RGBA"), small


# ---------------------------------------------------------------- the cards
GUN_CAM = dict(eye=[10, -4.5, 7.5], target=[1.75, 1.15, 6.55], focal=1.10)
GUN_AIM = [.30, -.62, 1]
STOCK_GUN = "warmachines/aircraft/dwf_thunderbarge/cannon/dwf_thundercannon_01.rigid_model_v2"
STOCK_GUN_MAT = "warmachines/materials/dwf_thunderbarge_grungni_01_weighted2_alpha_off.xml.material"


def gun_card(model_file=None, stock=False, burning=False):
    def build(scale=SS):
        cam = look(GUN_CAM["eye"], GUN_CAM["target"])
        fr = Frame(W * scale, H * scale, cam, GUN_CAM["focal"])
        draw_hull(fr, cull_y=7.0)
        M = aim_matrix(PORT, GUN_AIM)
        if stock:
            for mesh in load_model(STOCK_GUN)["lods"][0]:
                rigid(mesh, STOCK_GUN_MAT, fr, M, 2)
        else:
            model = rmv2.load((OUR_GUNS / model_file).read_bytes())
            ws = (OUR_GUNS / model_file.replace(".rigid_model_v2", ".wsmodel")).read_text(encoding="utf-8")
            mats = {int(p): m for p, l, m in re.findall(r'part_index="(\d+)" lod_index="(\d+)">(.*?)<', ws) if l == "0"}
            for i, mesh in enumerate(model["lods"][0]):
                rigid(mesh, mats[i], fr, M, 2 if i == 0 else 3)
        fr.muzzle = M[:3, 3] + M[:3, 2] * 2.9
        fr.axis = M[:3, 2]
        return fr
    def post(fr):
        if not burning:
            return None
        a = fr.project(fr.muzzle)
        b = fr.project(fr.muzzle + fr.axis)
        k = W / fr.w
        ax, ay, dx, dy = a[0] * k, a[1] * k, (b[0] - a[0]) * k, (b[1] - a[1]) * k
        def apply(src):
            s = glow(src, ax, ay, 40, .7)
            return fire(s, ax - dx * .1, ay - dy * .1, dx, dy, 95, 30)
        return apply
    return build, post


HARPOON = "warmachines/aircraft/dwf_thunderbarge/harpoon/dwf_thunderbarge_harpoon_01.wsmodel"
HARPOON_AT = [0, 15.1, 11.5]


def harpoon_card():
    def build(scale=SS):
        cam = look([9, 9.5, 33], [.3, 15.3, 18.0])
        fr = Frame(W * scale, H * scale, cam, 1.28)
        draw_hull(fr, balloon=True)
        M = np.eye(4, dtype=np.float32)
        M[:3, 3] = HARPOON_AT
        for mesh, mat in wsmodel(HARPOON)[0]:
            rigid(mesh, mat, fr, M, 2)
        return fr
    return build, lambda fr: None


RIFLE = "animations/battle/humanoid03/subset/zeppelin_crew/missile_actions/hu3_zeppelin_crew_rifle_aim_fire_stand_01.anim"
CROSSBOW = "animations/battle/humanoid03/crossbow/missile_actions/hu3_aim_fire_stand_crossbow_01.anim"
DRAKE = "animations/battle/humanoid03/drakegun/missile_actions/hu3_dkg_aim_01.anim"
PISTOL = "animations/battle/humanoid03/sorcerer_prophet/missle/hu3_sorcerer_prophet_aim_level_01.anim"
DECK_Y = 3.3
CREW_CAM = dict(eye=[15, 3.3, 3.8], target=[2.6, 3.65, 2.1], focal=1.5)
CREW_SEATS = [(2.3, 2.6, 3.25), (2.3, 2.6, 2.1), (2.3, 2.6, .95)]


def crew_card(vmd, anim, frame_no=0, yaw=35, scale=1.15, props=("be_prop_3",)):
    def build(sc=SS):
        cam = look(CREW_CAM["eye"], CREW_CAM["target"])
        fr = Frame(W * sc, H * sc, cam, CREW_CAM["focal"])
        draw_hull(fr, cull_y=7.5)
        for i, seat in enumerate(CREW_SEATS):
            draw_fighter(fr, vmd, anim, frame_no + i, seat_matrix(seat, yaw, scale), seed=i + 3, oid=4 + i, props=props)
        return fr
    return build, lambda fr: None


CUPOLA_CAM = dict(eye=[2.4, 25.6, 13.5], target=[-.3, 20.5, -1.0], focal=2.1)
CUPOLA_SEATS = [(0, 20.75, 3.55), (0, 20.6, -5.0)]
THROW = "animations/battle/humanoid03/2handed/throwing_axe/hu3_2h_throwing_axe_aiming_01.anim"


def cupola_card(vmd, anim, frame_no, props):
    def build(sc=SS):
        cam = look(CUPOLA_CAM["eye"], CUPOLA_CAM["target"])
        fr = Frame(W * sc, H * sc, cam, CUPOLA_CAM["focal"])
        draw_hull(fr, balloon=True)
        for i, seat in enumerate(CUPOLA_SEATS):
            draw_fighter(fr, vmd, anim, frame_no, seat_matrix(seat, 75, 1.2), seed=i + 1, oid=4 + i, props=props, hold="hand_right")
        return fr
    return build, lambda fr: None


BOMB_CAM = dict(eye=[8.5, -6, 6.5], target=[1.3, -.9, 2.67], focal=1.95)
BOMB = "warmachines/aircraft/dwf_thunderbarge/doors_right/dwf_thunderbomb_grungni_01_rigid.wsmodel"


DOOR = "warmachines/aircraft/dwf_thunderbarge/doors_right/dwf_thunderbarge_doors_right_01.wsmodel"
DOOR_AT = (1.52, .55, 2.67)


def draw_doors(fr, M, oid=2):
    """The stock door model on its own rig, open."""
    sk = card_anim.Anim(game("animations/skeletons/zeppelin01_bomb_right.anim"))
    inv = [np.linalg.inv(m) for m in sk.world(0)]
    pose = sk.world(0)        # the model's bind pose is the open one
    skin = np.stack([pose[i] @ inv[i] for i in range(len(pose))])
    for mesh, material in wsmodel(DOOR)[0]:
        pos, nor, uv, tan, bit, tris = mesh_arrays(mesh)
        idx, wt = bone_weights(mesh)
        mat = M @ (skin[idx.clip(0, len(skin) - 1)] * wt[..., None, None]).sum(1)
        h = np.concatenate([pos, np.ones((len(pos), 1), np.float32)], 1)
        world = (mat @ h[..., None])[..., :3, 0]
        rn = mat[:, :3, :3]
        fr.draw(world.astype(np.float32), norm((rn @ nor[..., None])[..., 0]), uv, norm((rn @ tan[..., None])[..., 0]), norm((rn @ bit[..., None])[..., 0]), tris, textures_of(material, mesh), oid)


def bomb_card(burning=False):
    def build(sc=SS):
        cam = look(BOMB_CAM["eye"], BOMB_CAM["target"])
        fr = Frame(W * sc, H * sc, cam, BOMB_CAM["focal"])
        draw_hull(fr, cull_y=7.0)
        M = np.eye(4, dtype=np.float32)
        a = math.radians(30)     # the hull's slope under the bay
        M[:3, 0], M[:3, 1], M[:3, 2] = (math.cos(a), math.sin(a), 0), (0, 0, 1), (math.sin(a), -math.cos(a), 0)      # the rig's y runs along the ship, its z points away from the hull
        M[:3, 3] = DOOR_AT
        draw_doors(fr, M)
        fr.bomb_at = np.array([1.3, -2.1, 2.67], np.float32)
        B = np.eye(4, dtype=np.float32)
        B[:3, 3] = fr.bomb_at
        for mesh, mat in wsmodel(BOMB)[0]:
            rigid(mesh, mat, fr, B, 3)
        return fr
    def post(fr):
        if not burning:
            return None
        k = W / fr.w
        a = fr.project(fr.bomb_at + [0, -.2, 0])
        b = fr.project(fr.bomb_at + [0, 1, 0])
        ax, ay, dx, dy = a[0] * k, a[1] * k, (b[0] - a[0]) * k, (b[1] - a[1]) * k
        return lambda src: fire(glow(src, ax, ay, 46, .7), ax, ay, dx, dy, 170, 40)
    return build, post


CARDS = {
    "cannons_organ": gun_card("tww3_mtb_organ.rigid_model_v2"),
    "cannons_stock": gun_card(stock=True),
    "cannons_flaming": gun_card(stock=True, burning=True),
    "cannons_clatter": gun_card("tww3_mtb_clatter2.rigid_model_v2"),
    "cannons_flame": gun_card("tww3_mtb_flame.rigid_model_v2", burning=True),
    "harpoon_on": harpoon_card(),
    "rifles_thunderers": crew_card("dwf_thunderers", RIFLE),
    "rifles_rakers": crew_card("dwf_thunderers_grudge_rakers", RIFLE),
    "rifles_pirates": crew_card("dwf_slayer_pirates", PISTOL, frame_no=25),
    "rifles_quarrellers": crew_card("dwf_quarrellers", CROSSBOW),
    "rifles_torpedoes": crew_card("local:torpedo_prop3.vmd", DRAKE),
    "cupolas_stock": cupola_card("dwf_thunderbarge_crew_pirates_grenade", THROW, 8, ("be_prop_1",)),
    "cupolas_axes": cupola_card("local:cupola_axes.vmd", THROW, 8, ("be_prop_1",)),
    "bombs_stock": bomb_card(),
    "bombs_fire": bomb_card(burning=True),
}


def contact(items, path):
    f = ImageFont.truetype("arial.ttf", 14)
    ref = Image.open(io.BytesIO(game("ui/units/infopics/wh_main_dwf_organ_gun.png"))).convert("RGBA")
    paper = (232, 228, 218, 255)
    cols = 6
    cell_w, cell_h = 250, 590
    rows = math.ceil((len(items) + 1) / cols)
    sh = Image.new("RGBA", (cols * cell_w + 20, rows * cell_h + 20), paper)
    d = ImageDraw.Draw(sh)
    for i, (name, info, small) in enumerate([("игра: wh_main_dwf_organ_gun", ref, None)] + items):
        x, y = 10 + (i % cols) * cell_w, 10 + (i // cols) * cell_h
        d.text((x, y), name, font=f, fill=(40, 40, 40))
        sh.alpha_composite(info.resize((240, 520), Image.BICUBIC), (x, y + 22))
    sh.convert("RGB").save(path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--plain")
    ap.add_argument("--sheet")
    args = ap.parse_args()
    names = args.only.split(",") if args.only else list(CARDS)
    if args.plain:
        ims = []
        for n in names:
            build, _ = CARDS[n]
            fr = build(1)
            col, mask = lit(fr)
            ims.append(Image.fromarray((np.clip(col * mask[..., None] + .72 * (1 - mask[..., None]), 0, 1) * 255).astype(np.uint8)).resize((300, 650)))
        sh = Image.new("RGB", (len(ims) * 306, 650), (20, 20, 20))
        for i, im in enumerate(ims):
            sh.paste(im, (i * 306, 0))
        sh.save(args.plain)
        return
    items = []
    for i, n in enumerate(names):
        build, post = CARDS[n]
        fr = build()
        canvas = paint(fr, seed=i * 7, post=post(fr))
        info, small = finish(canvas, n)
        items.append((n, info, small))
        if not args.only:
            OUT.mkdir(parents=True, exist_ok=True)
            info.save(OUT / f"{n}.png", optimize=True)
            small.save(OUT / f"{n}_small.png", optimize=True)
        print(n)
    contact(items, args.sheet or SHEET)


if __name__ == "__main__":
    main()
