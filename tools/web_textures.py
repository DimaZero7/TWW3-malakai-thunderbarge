"""DDS of the game into PNG for the web page: py -3.10 tools/web_textures.py build/web/raw/jobs.json

Called by tools/web_export.py. A job [png, png, "round", box] cuts a square of a portrait round. Python 3.10 because Pillow is installed there (it decodes BC1 and BC3). A job: [dds, png, kind].
kind "normal": the game's packed normal map (x in alpha, y in green, red full, blue empty) becomes an ordinary RGB normal map with z rebuilt;
a map that is not packed that way is kept as it is. Writes only the PNG files named in the jobs (build/web/tex/).
"""
import io
import json
import struct
import sys

import numpy as np
from PIL import Image


# sRGB formats Pillow does not open: the same blocks under the plain format. The colour stays in file units, as the game's sRGB sampling would give on screen.
SRGB = {72: 71, 75: 74, 78: 77, 99: 98}


def open_dds(src):
    raw = bytearray(open(src, "rb").read())
    if raw[84:88] == b"DX10":
        fmt = struct.unpack_from("<I", raw, 128)[0]
        if fmt in SRGB:
            struct.pack_into("<I", raw, 128, SRGB[fmt])
    return Image.open(io.BytesIO(bytes(raw)))


def convert(src, dst, kind):
    im = open_dds(src)
    im.load()
    rgba = np.asarray(im.convert("RGBA"), dtype=np.float32) / 255.0
    note = ""
    if kind == "normal":
        mean = rgba.reshape(-1, 4).mean(0)
        if mean[0] > 0.8 and mean[2] < 0.25:
            x, y = rgba[..., 3] * 2 - 1, rgba[..., 1] * 2 - 1
            z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
            rgb = np.stack([x, y, z], -1) * 0.5 + 0.5
            Image.fromarray((rgb * 255 + 0.5).astype(np.uint8), "RGB").save(dst)
            note = "packed x in alpha, y in green"
        else:
            im.convert("RGB").save(dst)
            note = f"kept, mean {np.round(mean, 2).tolist()}"
    else:
        alpha = rgba[..., 3]
        if alpha.min() < 0.99:
            im.convert("RGBA").save(dst)
            note = f"with alpha, {float((alpha < 0.5).mean()) * 100:.1f} % cut"
        else:
            im.convert("RGB").save(dst)
    print(f"{dst}: {im.size[0]}x{im.size[1]} {im.mode} {note}", flush=True)


def round_face(src, dst, box):
    """A square of a portrait cut round, the outside transparent: the face for a round mark."""
    from PIL import ImageDraw
    im = Image.open(src).convert("RGBA").crop(tuple(box)).resize((160, 160), Image.LANCZOS)
    mask = Image.new("L", (640, 640), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 639, 639), fill=255)
    back = Image.new("RGBA", (160, 160), (43, 33, 24, 255))      # dark behind the portrait's own transparent parts
    back.alpha_composite(im)
    back.putalpha(mask.resize((160, 160), Image.LANCZOS))
    back.save(dst)
    print(f"{dst}: round face {box}", flush=True)


def main():
    for job in json.loads(open(sys.argv[1], encoding="utf-8").read()):
        if job[2] == "round":
            round_face(*job[:2], job[3])
        else:
            convert(*job)


if __name__ == "__main__":
    main()
